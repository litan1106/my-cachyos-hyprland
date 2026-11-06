#!/usr/bin/env bash
# Portable Linux VS Code configuration snapshots. Requires Python 3 and the code CLI.
# Python's standard library handles profile JSON and validates ZIPs before restore.
set -euo pipefail

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2
  exit 1
fi

# Keep stdin available for confirmation while Python reads this embedded program.
python3 - "$@" 3<&0 <<'PY'
import argparse
import difflib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
import uuid
import zipfile


CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config'))
CONFIG = Path(os.environ.get('VSCODE_CONFIG_DIR', str(CONFIG_HOME / 'Code'))).absolute()
EXTENSIONS = Path(os.environ.get('VSCODE_EXTENSIONS_DIR', str(Path.home() / '.vscode/extensions'))).absolute()
BACKUPS = Path(os.environ.get('BACKUP_DIR', str(Path.home() / 'backups/vscode'))).absolute()
CODE = os.environ.get('CODE_BIN', 'code')
FILES = {'settings.json', 'keybindings.json', 'tasks.json'}
FLAGS = {'settings', 'keybindings', 'tasks', 'snippets', 'extensions', 'prompts', 'mcp', 'languageModels'}
# A profile's own copy of these is inactive while it inherits from Default.
INHERITED_FILES = {'settings.json': 'settings', 'keybindings.json': 'keybindings', 'tasks.json': 'tasks'}
ID = re.compile(r'[A-Za-z0-9_-]+\Z')
EXTENSION = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*\.[A-Za-z0-9][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.+_-]*\Z')
JSONC_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\r\n]*|/\*.*?\*/|[{}\[\]:,]|[^\s{}\[\]:,"/]+|/', re.DOTALL)
# These override explicit paths or redirect the launcher to a remote CLI.
CODE_ENV = {k: v for k, v in os.environ.items()
            if k not in {'VSCODE_PORTABLE', 'VSCODE_APPDATA', 'VSCODE_IPC_HOOK_CLI'}}


def fail(message):
    raise ValueError(message)


def read_storage():
    path = CONFIG / 'User/globalStorage/storage.json'
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        fail(f'Invalid profile registry: {path}')
    return data


def registered_profiles(storage):
    entries = storage.get('userDataProfiles', [])
    if not isinstance(entries, list):
        fail('Invalid userDataProfiles registry.')
    profiles, names, locations = [], set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            fail('Invalid profile registry entry.')
        location, name = entry.get('location'), entry.get('name')
        # VS Code manages this system profile; it inherits the user's defaults.
        if isinstance(location, str) and location.startswith('builtin/'):
            continue
        if not isinstance(location, str) or not ID.fullmatch(location) or location == 'default':
            fail(f'Unsupported profile location: {location!r}')
        if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 for c in name):
            fail('Invalid profile name.')
        if name in names or location in locations:
            fail('Duplicate profile names or locations in registry.')
        flags = entry.get('useDefaultFlags', {})
        if not isinstance(flags, dict) or any(type(v) is not bool for v in flags.values()):
            fail(f'Invalid inheritance flags for profile {name!r}')
        profiles.append(entry)
        names.add(name)
        locations.add(location)
    return profiles


def code_args(name):
    args = [CODE, '--user-data-dir', str(CONFIG), '--extensions-dir', str(EXTENSIONS)]
    if name is not None:
        args.append(f'--profile={name}')
    return args


def list_extensions(name):
    result = subprocess.run(code_args(name) + ['--list-extensions', '--show-versions'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=CODE_ENV)
    if result.returncode:
        fail(f'Cannot list extensions for {name or "Default"}: {result.stderr.strip()}')
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if any(not EXTENSION.fullmatch(line) for line in lines):
        fail(f'Unexpected extension list for {name or "Default"}; backup aborted.')
    return sorted(set(lines), key=str.lower)


def no_symlink(path):
    for item in (path, *path.parents):
        if item.is_symlink():
            fail(f'Symlink paths are not supported: {item}')


def exclude_legacy_mcp(data, path):
    depth, candidate = 0, False
    for match in JSONC_TOKEN.finditer(data.decode('utf-8-sig')):
        token = match.group()
        if token.startswith(('//', '/*')):
            continue
        if depth == 1 and token == ':' and candidate:
            fail(f'Legacy inline MCP in {path}; migrate MCP servers from settings.json to mcp.json in VS Code first.')
        candidate = depth == 1 and token.startswith('"') and json.loads(token) == 'mcp'
        if token in ('{', '['):
            depth += 1
        elif token in ('}', ']'):
            depth -= 1


def snapshot():
    if not (CONFIG / 'User').is_dir():
        fail(f'VS Code User directory not found: {CONFIG / "User"}')
    no_symlink(CONFIG / 'User/globalStorage/storage.json')
    profiles = [{'id': 'default', 'name': None}]
    for entry in registered_profiles(read_storage()):
        profile = {'id': entry['location'], 'name': entry['name'],
                   'useDefaultFlags': {k: v for k, v in entry.get('useDefaultFlags', {}).items() if k in FLAGS}}
        if isinstance(entry.get('icon'), str):
            profile['icon'] = entry['icon']
        profiles.append(profile)
    payload = {}
    for profile in profiles:
        prefix = PurePosixPath('User')
        if profile['name'] is not None:
            prefix = prefix / 'profiles' / profile['id']
        root = CONFIG / str(prefix)
        inherited = {k for k, v in profile.get('useDefaultFlags', {}).items() if v}
        for filename in sorted(FILES):
            if INHERITED_FILES[filename] in inherited:
                continue
            path = root / filename
            no_symlink(path)
            if path.is_file():
                data = path.read_bytes()
                if filename == 'settings.json':
                    exclude_legacy_mcp(data, path)
                payload[str(prefix / filename)] = data
        snippets = root / 'snippets'
        no_symlink(snippets)
        if snippets.exists() and 'snippets' not in inherited:
            for path in sorted(snippets.rglob('*')):
                no_symlink(path)
                if path.is_file():
                    payload[str(prefix / 'snippets' / path.relative_to(snippets).as_posix())] = path.read_bytes()
        profile['extensions'] = list_extensions(profile['name'])
    manifest = {'format': 'vscode-config-backup', 'version': 1, 'profiles': profiles}
    return manifest, payload


def write_backup(manifest, payload, prefix='vscode-backup'):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output = BACKUPS / f'{prefix}-{timestamp}.zip'
    fd, temporary = tempfile.mkstemp(prefix='.vscode-', suffix='.zip', dir=BACKUPS)
    try:
        with os.fdopen(fd, 'w+b') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
            for name, data in sorted(payload.items()):
                archive.writestr(name, data)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f'Backup created: {output}')
    return output


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get('format') != 'vscode-config-backup' or manifest.get('version') != 1:
        fail('Not a supported VS Code configuration backup.')
    profiles = manifest.get('profiles')
    if not isinstance(profiles, list) or not profiles:
        fail('Backup has no profiles.')
    ids, names = set(), set()
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            fail('Invalid profile manifest.')
        allowed = {'id', 'name', 'extensions', 'useDefaultFlags', 'icon'}
        if set(profile) - allowed:
            fail('Unsupported profile manifest fields.')
        pid, name = profile.get('id'), profile.get('name')
        if index == 0:
            if pid != 'default' or name is not None:
                fail('Backup must start with the Default profile.')
        else:
            if not isinstance(pid, str) or not ID.fullmatch(pid) or pid == 'default':
                fail('Invalid profile ID.')
            if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 for c in name):
                fail('Invalid profile name.')
        if pid in ids or name in names:
            fail('Duplicate profiles in backup.')
        ids.add(pid)
        names.add(name)
        flags = profile.get('useDefaultFlags', {})
        if not isinstance(flags, dict) or set(flags) - FLAGS or any(type(v) is not bool for v in flags.values()):
            fail('Invalid profile inheritance flags.')
        if 'icon' in profile and not isinstance(profile['icon'], str):
            fail('Invalid profile icon.')
        extensions = profile.get('extensions')
        if not isinstance(extensions, list) or any(not isinstance(e, str) or not EXTENSION.fullmatch(e) for e in extensions):
            fail('Invalid extension IDs in backup.')
    return profiles


def read_backup(path):
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > 256 * 1024 * 1024:
            fail('Backup exceeds configuration archive limits (10,000 entries / 256 MiB).')
        names = set()
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not parts or name.startswith('/') or '\\' in name or any(p in ('.', '..') for p in name.split('/'))
                    or str(PurePosixPath(name)) != name or name in names or info.is_dir()):
                fail(f'Unsafe or duplicate archive path: {name!r}')
            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in (0, stat.S_IFREG):
                fail(f'Non-regular archive member: {name!r}')
            names.add(name)
        if 'manifest.json' not in names:
            fail('Backup manifest is missing.')
        manifest = json.loads(archive.read('manifest.json'))
        profiles = validate_manifest(manifest)
        payload = {}
        for info in infos:
            name = info.filename
            if name == 'manifest.json':
                continue
            relative = None
            for profile in profiles:
                prefix = 'User/' if profile['name'] is None else f'User/profiles/{profile["id"]}/'
                if name.startswith(prefix):
                    suffix = name[len(prefix):]
                    if suffix in FILES or suffix.startswith('snippets/'):
                        relative = suffix
                        break
            if relative is None:
                fail(f'Unexpected configuration path (MCP and state are excluded): {name!r}')
            if any(str(parent) in names for parent in PurePosixPath(name).parents):
                fail(f'File/directory conflict in archive: {name!r}')
            data = archive.read(info)
            if relative == 'settings.json':
                exclude_legacy_mcp(data, name)
            payload[name] = data
        return manifest, payload


def restore_plan(manifest, payload):
    no_symlink(CONFIG / 'User/globalStorage/storage.json')
    storage = read_storage()
    existing = registered_profiles(storage)
    by_name = {p['name']: p for p in existing}
    entries = list(storage.get('userDataProfiles', []))
    mapping = {'User/': 'User/'}
    for profile in manifest['profiles'][1:]:
        entry = by_name.get(profile['name'])
        if entry is None:
            entry = {'location': uuid.uuid4().hex, 'name': profile['name']}
            entries.append(entry)
        # Backup flags replace recorded ones; unlisted flags (e.g. globalState) are kept.
        flags = {k: v for k, v in entry.get('useDefaultFlags', {}).items() if k not in FLAGS}
        flags.update(profile.get('useDefaultFlags', {}))
        entry['useDefaultFlags'] = flags
        if 'icon' in profile:
            entry['icon'] = profile['icon']
        mapping[f'User/profiles/{profile["id"]}/'] = f'User/profiles/{entry["location"]}/'
    storage['userDataProfiles'] = entries
    writes = {}
    for name, data in payload.items():
        prefix = next((p for p in mapping if p != 'User/' and name.startswith(p)), 'User/')
        target = CONFIG / (mapping[prefix] + name[len(prefix):])
        writes[target] = data
    if manifest['profiles'][1:]:
        writes[CONFIG / 'User/globalStorage/storage.json'] = (json.dumps(storage, indent=2) + '\n').encode()
    for target in writes:
        no_symlink(target)
        if target.exists() and not target.is_file():
            fail(f'Restore target is not a file: {target}')
        if any(parent.exists() and not parent.is_dir() for parent in target.parents):
            fail(f'Restore target has a non-directory parent: {target}')
    return writes


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.vscode-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def restore(path):
    manifest, payload = read_backup(path)
    writes = restore_plan(manifest, payload)
    print(f'Restore into: {CONFIG}')
    for profile in manifest['profiles']:
        print(f'  {profile["name"] or "Default"}: {len(profile["extensions"])} extensions')
    for target in sorted(writes):
        print(f'  Write: {target.relative_to(CONFIG)}')
    print('Existing extra files and extensions are retained; matching files are overwritten.')
    print('Close VS Code and pause Settings Sync before restoring. Continue? [y/N] ', end='', flush=True)
    with os.fdopen(3) as confirmation:
        if confirmation.readline().strip().lower() != 'y':
            print('Restore cancelled.')
            return 0
    if shutil.which(CODE) is None:
        fail(f'VS Code CLI not found: {CODE}')
    if (CONFIG / 'User').exists():
        current_manifest, current_payload = snapshot()
        write_backup(current_manifest, current_payload, 'vscode-pre-restore')
    for target, data in writes.items():
        atomic_write(target, data)
    failures = []
    for profile in manifest['profiles']:
        if profile.get('useDefaultFlags', {}).get('extensions'):
            continue
        for extension in profile['extensions']:
            label = f'{profile["name"] or "Default"}: {extension}'
            print(f'Installing {label}', flush=True)
            result = subprocess.run(code_args(profile['name']) + ['--install-extension', extension],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=CODE_ENV)
            if result.returncode:
                failures.append(label)
                print(f'Extension failed: {label}\n{result.stdout}', file=sys.stderr)
    if failures:
        print(f'Configuration restored; {len(failures)} extension installation(s) failed. Retry the restore when available.', file=sys.stderr)
        return 1
    print('Restore complete. Start VS Code to use the restored configuration.')
    return 0


def normalized(manifest, payload):
    result = {}
    for profile in manifest['profiles']:
        key = profile['name'] or 'Default'
        prefix = 'User/' if profile['name'] is None else f'User/profiles/{profile["id"]}/'
        result[(key, '(extensions)')] = ('\n'.join(sorted(profile['extensions'])) + '\n').encode()
        result[(key, '(metadata)')] = json.dumps({k: v for k, v in profile.items() if k not in {'id', 'name', 'extensions'}}, sort_keys=True).encode()
        for name, data in payload.items():
            if name.startswith(prefix) and not (profile['name'] is None and name.startswith('User/profiles/')):
                result[(key, name[len(prefix):])] = data
    return result


def diff(path):
    archived = normalized(*read_backup(path))
    current = normalized(*snapshot()) if (CONFIG / 'User').is_dir() else {}
    changes = 0
    for key in sorted(archived.keys() | current.keys()):
        old, new = current.get(key), archived.get(key)
        if old == new:
            continue
        changes += 1
        label = '/'.join(key)
        if old is None:
            print(f'Only in backup: {label}')
        elif new is None:
            print(f'Only on this machine (retained): {label}')
        else:
            print(''.join(difflib.unified_diff(old.decode(errors='replace').splitlines(keepends=True),
                                             new.decode(errors='replace').splitlines(keepends=True),
                                             fromfile=f'current/{label}', tofile=f'backup/{label}')), end='\n')
    if not changes:
        print('No differences in portable configuration or extension versions.')
    return int(bool(changes))


def main():
    parser = argparse.ArgumentParser(prog='backup-vscode.sh', description='Back up and restore Linux VS Code configuration, excluding MCP.',
        epilog='Requires Python 3 and code. Close VS Code and pause Settings Sync for restore. '
               'Environment: VSCODE_CONFIG_DIR (data root, default $XDG_CONFIG_HOME/Code or ~/.config/Code), '
               'VSCODE_EXTENSIONS_DIR (default ~/.vscode/extensions), CODE_BIN (default code), '
               'BACKUP_DIR (default ~/backups/vscode). No authentication, workspace state, '
               'extension binaries, or MCP files are copied. Legacy MCP in settings.json must be migrated first. '
               'Extension reinstall needs network access.')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--zip', '-z', action='store_true', help='create a timestamped ZIP backup (default)')
    group.add_argument('--restore', '-r', metavar='ZIP', help='preview, confirm, safety backup, then restore')
    group.add_argument('--diff', '-d', metavar='ZIP', help='compare current config with backup (exit 1 if different)')
    group.add_argument('--list', '-l', action='store_true', help='list backups, newest first')
    args = parser.parse_args()
    if args.restore:
        return restore(args.restore)
    if args.diff:
        return diff(args.diff)
    if args.list:
        backups = sorted(BACKUPS.glob('vscode-*.zip'), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in backups:
            print(f'{path.stat().st_size:>10} bytes  {path}')
        if not backups:
            print(f'No backups in {BACKUPS}')
        return 0
    manifest, payload = snapshot()
    validate_manifest(manifest)
    write_backup(manifest, payload)
    print(f'{len(payload)} configuration files; {len(manifest["profiles"])} profiles. MCP excluded.')
    return 0


try:
    sys.exit(main())
except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
    print(f'Error: {exc}', file=sys.stderr)
    sys.exit(2)
PY
