#!/usr/bin/env python3
"""Check pinned sources and launch the project-local ComfyUI server."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {
    'ComfyUI': 'https://github.com/Comfy-Org/ComfyUI.git',
    'ComfyUI-BFSNodes': 'https://github.com/alisson-anjos/ComfyUI-BFSNodes.git',
    'ComfyUI-KJNodes': 'https://github.com/kijai/ComfyUI-KJNodes.git',
    'ComfyUI-VideoHelperSuite': 'https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git',
    'ComfyUI-GGUF': 'https://github.com/city96/ComfyUI-GGUF.git',
}
PROTECTED = {'--listen', '--port', '--input-directory', '--output-directory',
             '--user-directory', '--temp-directory', '--base-directory',
             '--previews-directory', '--extra-model-paths-config'}


def build_command(root, profile, extra):
    profiles = json.loads((root / 'config/runtime-profiles.json').read_text())
    if profile not in profiles:
        raise ValueError(f'Unknown profile {profile!r}; choose: {", ".join(profiles)}')
    for arg in extra:
        option = arg.split('=', 1)[0]
        if option.startswith('--') and any(name.startswith(option) for name in PROTECTED):
            raise ValueError(f'Project launch setting cannot be overridden: {arg}')
    dynamic_vram = [] if '--enable-dynamic-vram' in extra else ['--disable-dynamic-vram']
    return [str(root / '.venv/bin/python'), str(root / 'ComfyUI/main.py'),
            '--listen', '127.0.0.1', '--port', '8189', '--max-upload-size', '4096',
            '--input-directory', str(root / 'input'), '--output-directory', str(root / 'output'),
            '--user-directory', str(root / 'user'), '--temp-directory', str(root / 'temp'),
            '--use-pytorch-cross-attention', *dynamic_vram,
            *profiles[profile], '--preview-method', 'none', *extra]


def check_port(port=8189):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('127.0.0.1', port))


def source_specs(root):
    version = json.loads((root / 'versions.json').read_text())['runtime']
    repos = [(root / 'ComfyUI', version['comfyui_revision'], REPOSITORIES['ComfyUI'])]
    repos += [(root / 'ComfyUI/custom_nodes' / name, rev, REPOSITORIES[name])
              for name, rev in version['node_revisions'].items()]
    if any(not re.fullmatch(r'[0-9a-f]{40}', rev) for _, rev, _ in repos):
        raise ValueError('Source revisions must be full 40-character Git commit IDs')
    return repos


def inspect_sources(root, allow_missing=False):
    good = True
    for path, expected, _ in source_specs(root):
        if not os.path.lexists(path):
            if not allow_missing:
                print(f'Missing checkout: {path}; expected revision {expected}', file=sys.stderr)
                good = False
            continue
        if not path.is_dir() or not (path / '.git').exists():
            print(f'Not a Git checkout; preserved: {path}', file=sys.stderr)
            good = False
            continue
        result = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True)
        actual = result.stdout.strip()
        if result.returncode or actual != expected:
            print(f'Checkout revision mismatch: {path}; expected {expected}, found {actual or "unavailable"}', file=sys.stderr)
            good = False
        else:
            print(f'Checkout verified: {path.relative_to(root)} {actual}')
        status = subprocess.run(['git', '-C', str(path), 'status', '--porcelain'],
                                capture_output=True, text=True)
        if status.returncode:
            good = False
            print(f'Cannot inspect checkout status: {path}', file=sys.stderr)
        elif status.stdout.strip():
            print(f'Checkout has local changes; preserved: {path}', file=sys.stderr)
            good = False
    return good


def check_sources(root):
    return inspect_sources(root)


def ensure_sources(root):
    if not inspect_sources(root, allow_missing=True):
        return False
    for path, revision, url in source_specs(root):
        if os.path.lexists(path):
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.bfs-clone-', dir=path.parent) as temporary:
            clone = Path(temporary) / 'checkout'
            subprocess.run(['git', 'clone', '--no-checkout', url, str(clone)], check=True)
            subprocess.run(['git', '-C', str(clone), 'checkout', '--detach', revision], check=True)
            if os.path.lexists(path):
                raise FileExistsError(f'Checkout destination appeared during clone: {path}')
            clone.rename(path)
    return check_sources(root)


def check_models(root):
    manifest = json.loads((root / 'models.json').read_text())
    good = True
    for model in (item for item in manifest['models'] if item['required']):
        try:
            path = (root / model['destination']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Model destination escapes project root')
            if path.stat().st_size != model['size']:
                raise ValueError('incorrect size')
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
                    digest.update(block)
            if digest.hexdigest() != model['sha256']:
                raise ValueError('SHA-256 mismatch')
            print(f"{model['id']}: size and SHA-256 verified")
        except (OSError, ValueError) as exc:
            print(f"{model['id']}: {exc}", file=sys.stderr)
            good = False
    return good


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check-sources')
    sub.add_parser('ensure-sources')
    sub.add_parser('check-models')
    validate = sub.add_parser('validate-profile')
    validate.add_argument('profile')
    launch = sub.add_parser('launch')
    launch.add_argument('--profile', default='legacy')
    launch.add_argument('--print-command', action='store_true')
    launch.add_argument('extra', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.action == 'check-sources':
            return 0 if check_sources(ROOT) else 1
        if args.action == 'ensure-sources':
            return 0 if ensure_sources(ROOT) else 1
        if args.action == 'check-models':
            return 0 if check_models(ROOT) else 1
        if args.action == 'validate-profile':
            build_command(ROOT, args.profile, [])
            return 0
        extra = args.extra[1:] if args.extra and args.extra[0] == '--' else args.extra
        command = build_command(ROOT, args.profile, extra)
        if args.print_command:
            print(json.dumps(command))
            return 0
        check_port()
        for path in ('input', 'output', 'user', 'temp', 'logs'):
            (ROOT / path).mkdir(parents=True, exist_ok=True)
        os.chdir(ROOT)
        env = os.environ.copy()
        env['HIP_VISIBLE_DEVICES'] = '0'
        rocm_path = env.setdefault('ROCM_PATH', str(Path.home() / '.local/opt/rocm-10.0.0-gfx120X-all'))
        env['HIP_PATH'] = rocm_path
        env['PATH'] = str(Path(rocm_path) / 'bin') + os.pathsep + env.get('PATH', '')
        os.execve(command[0], command, env)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f'BFS runtime: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
