#!/usr/bin/env python3
"""Stage and transactionally replace the native Hongguo application."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

REPO = 'waligoraamodio288-rgb/hongguo-desktop-releases'
STATE = ('downloads', 'config.json', 'devices.json', '.env')
REQUIRED = ('server.py', 'hongguo.py', 'offline_dl.py', 'frida/offline_decrypt.py')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fetch(url):
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'hongguo-native-upgrade'})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def release(version):
    endpoint = 'latest' if version is None else 'tags/v' + version
    data = json.loads(fetch(f'https://api.github.com/repos/{REPO}/releases/{endpoint}'))
    tag = data.get('tag_name', '').removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+', tag) or (version and version != tag):
        raise ValueError('Invalid release version')
    assets = {a['name']: a['browser_download_url'] for a in data['assets']}
    name = f'hongguo-{tag}-windows-x86_64-setup.exe'
    if name not in assets or 'SHA256SUMS.txt' not in assets:
        raise ValueError('Release is missing installer or SHA256SUMS.txt')
    return tag, name, assets[name], assets['SHA256SUMS.txt']


def copy_item(src, dst):
    if src.is_symlink():
        dst.symlink_to(os.readlink(src), target_is_directory=src.is_dir())
    elif src.is_dir():
        shutil.copytree(src, dst, symlinks=True)
    else:
        shutil.copy2(src, dst, follow_symlinks=False)


def overlay_state(source, target):
    for name in STATE:
        src, dst = source / name, target / name
        if src.exists() or src.is_symlink():
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            elif dst.exists():
                shutil.rmtree(dst)
            copy_item(src, dst)


def validate(backend):
    if backend.is_symlink():
        raise ValueError('Backend must not be a symlink')
    for name in (*REQUIRED, 'guest-config.json', 'sign/unidbg-sign.jar'):
        path = backend / name
        if any(part.is_symlink() for part in (path, *path.parents) if part != backend.parent):
            raise ValueError(f'Symlink in required path: {name}')
    for name in REQUIRED:
        path = backend / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing required file: {name}')
        compile(path.read_bytes(), str(path), 'exec')
    config = json.loads((backend / 'guest-config.json').read_text())
    if not isinstance(config, dict) or not isinstance(config.get('api_host'), str) or not config['api_host'].strip() or not isinstance(config.get('base_query'), dict) or not isinstance(config.get('session_headers'), dict):
        raise ValueError('Invalid guest-config.json')
    jar = backend / 'sign/unidbg-sign.jar'
    with zipfile.ZipFile(jar) as archive:
        if archive.testzip() is not None:
            raise ValueError('Invalid signer jar')


def launcher_stage(source, target):
    target.mkdir()
    for name in ('launch-hongguo', 'upgrade-hongguo'):
        src = source / name
        if not src.is_file():
            src = source / (name + '.sh')
        shutil.copy2(src, target / name)
    for name in ('hongguo-common.sh', 'hongguo-upgrade.py'):
        shutil.copy2(source / name, target / name)
    (target / 'hongguo-web').mkdir()
    for name in ('index.html', 'standalone_server.py'):
        shutil.copy2(source / 'hongguo-web' / name, target / 'hongguo-web' / name)


def backup(home):
    root = home / 'backups'
    root.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-'), dir=root))
    try:
        for name in ('backend', 'launcher', 'native-release.json'):
            src = home / name
            if src.exists() or src.is_symlink():
                copy_item(src, path / name)
        if not (path / 'backend').is_dir() or not (path / 'launcher').is_dir():
            raise ValueError('Existing backend and launcher are required')
        (path / '.complete').touch()
        return path
    except Exception:
        shutil.rmtree(path)
        raise


def refuse_legacy(home):
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if b'standalone_server.py' in (proc / 'cmdline').read_bytes() and (proc / 'cwd').resolve() == (home / 'backend').resolve():
                raise RuntimeError('Hongguo backend is running; stop it before upgrading')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue


def apply(home, staged, metadata):
    previous = backup(home)
    overlay_state(home / 'backend', staged / 'backend')
    moved = []
    installed = []
    # A pending stop must wait until the live directories are consistent.
    prior_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
    try:
        try:
            for name in ('backend', 'launcher', 'native-release.json'):
                live = home / name
                if live.exists() or live.is_symlink():
                    live.rename(staged / ('old-' + name))
                    moved.append(name)
            (staged / 'native-release.json').write_text(json.dumps(metadata | {'backup': str(previous)}, indent=2) + '\n')
            for name in ('backend', 'launcher', 'native-release.json'):
                (staged / name).rename(home / name)
                installed.append(name)
        except BaseException:
            for name in reversed(installed):
                path = home / name
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            for name in reversed(moved):
                (staged / ('old-' + name)).rename(home / name)
            raise
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, prior_mask)
    return previous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, required=True, help=argparse.SUPPRESS)
    parser.add_argument('--scripts-dir', type=Path, required=True, help=argparse.SUPPRESS)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--version')
    group.add_argument('--installer', type=Path)
    group.add_argument('--rollback', action='store_true')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    if args.version:
        args.version = args.version.removeprefix('v')
        if not re.fullmatch(r'\d+\.\d+\.\d+', args.version):
            parser.error('version must be X.Y.Z, optionally prefixed by v')
    if args.rollback and args.check:
        parser.error('--check cannot be combined with --rollback')
    try:
        home = args.home.expanduser().resolve()
        if args.installer:
            installer = args.installer.expanduser().resolve(strict=True)
            sha = digest(installer)
            match = re.fullmatch(r'hongguo-(\d+\.\d+\.\d+)-windows-x86_64-setup\.exe', installer.name)
            version = match.group(1) if match else None
            print(f'Local installer: {installer} (SHA256 {sha}; not release-verified)')
        elif not args.rollback:
            version, name, url, sums_url = release(args.version)
            print(f'Release {version}: {name}')
        if args.check:
            current = home / 'native-release.json'
            try:
                current_version = json.loads(current.read_text()).get('version') or 'unknown'
            except (OSError, ValueError, AttributeError):
                current_version = 'unknown'
            print(f'Current version: {current_version}; target: {version or "local"}')
            print('Preserve: data/, hls/, venv/, backend runtime state')
            if not args.installer:
                print('Checksum source: release SHA256SUMS.txt (verified during install)')
            return 0
        if not (home / 'backend').is_dir() or not (home / 'launcher').is_dir():
            raise ValueError('Hongguo is not installed; run install-hongguo.sh first')
        with (home / '.maintenance.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Hongguo is running or maintenance is already in progress')
            refuse_legacy(home)
            with tempfile.TemporaryDirectory(prefix='.upgrade-', dir=home) as tmp:
                staged = Path(tmp)
                if args.rollback:
                    backups = home / 'backups'
                    candidates = sorted((p for p in backups.iterdir() if p.is_dir() and (p / '.complete').is_file() and (p / 'backend').is_dir() and (p / 'launcher').is_dir()), key=lambda p: p.stat().st_mtime_ns, reverse=True) if backups.is_dir() else []
                    if not candidates:
                        raise ValueError('No complete backup available')
                    chosen = None
                    for candidate in candidates:
                        try:
                            validate(candidate / 'backend')
                            metadata = json.loads((candidate / 'native-release.json').read_text()) if (candidate / 'native-release.json').is_file() else {'version': None, 'digest': None}
                            if not isinstance(metadata, dict):
                                continue
                            chosen = candidate
                            break
                        except (OSError, ValueError, SyntaxError, zipfile.BadZipFile):
                            continue
                    if chosen is None:
                        raise ValueError('No valid backup available')
                    copy_item(chosen / 'backend', staged / 'backend')
                    copy_item(chosen / 'launcher', staged / 'launcher')
                    source = args.scripts_dir / 'upgrade-hongguo'
                    if not source.is_file():
                        source = args.scripts_dir / 'upgrade-hongguo.sh'
                    shutil.copy2(source, staged / 'launcher/upgrade-hongguo')
                    shutil.copy2(args.scripts_dir / 'hongguo-upgrade.py', staged / 'launcher/hongguo-upgrade.py')
                else:
                    if not args.installer:
                        installer = staged / name
                        req = urllib.request.Request(url, headers={'User-Agent': 'hongguo-native-upgrade'})
                        with urllib.request.urlopen(req, timeout=60) as response, installer.open('wb') as output:
                            shutil.copyfileobj(response, output, length=1024 * 1024)
                        sha = digest(installer)
                        lines = fetch(sums_url).decode('utf-8').splitlines()
                        matches = [m.group(1).lower() for line in lines if (m := re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(.+)', line.strip())) and m.group(2) == name]
                        if len(matches) != 1 or matches[0] != sha:
                            raise ValueError('Installer SHA256 verification failed')
                    subprocess.run(['7z', 'x', '-y', '-o' + str(staged), str(installer), 'backend/*'], check=True, stdout=subprocess.DEVNULL)
                    for name in ('python', 'jre'):
                        path = staged / 'backend' / name
                        if path.is_symlink():
                            path.unlink()
                        elif path.exists():
                            shutil.rmtree(path)
                    validate(staged / 'backend')
                    launcher_stage(args.scripts_dir, staged / 'launcher')
                    metadata = {'version': version, 'digest': sha}
                refuse_legacy(home)
                previous = apply(home, staged, metadata)
                print(f'Installed successfully; backup: {previous}')
                bin_dir = Path.home() / '.local/bin'
                try:
                    bin_dir.mkdir(parents=True, exist_ok=True)
                    for name in ('launch-hongguo', 'upgrade-hongguo'):
                        link = bin_dir / name
                        if not link.exists() and not link.is_symlink():
                            link.symlink_to(home / 'launcher' / name)
                        elif not link.is_symlink() or link.resolve() != (home / 'launcher' / name).resolve():
                            print(f'Warning: existing {link} was not replaced', file=sys.stderr)
                except OSError as exc:
                    print(f'Warning: could not create upgrade launcher link: {exc}', file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile, SyntaxError) as exc:
        print(f'Upgrade failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
