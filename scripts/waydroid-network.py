#!/usr/bin/env python3
"""Manage the user-owned Waydroid HTTP proxy and its Android settings."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

KEYS = ('http_proxy', 'global_http_proxy_host', 'global_http_proxy_port',
        'global_http_proxy_exclusion_list', 'global_proxy_pac_url')
MANAGED = dict(zip(KEYS, ('192.168.240.1:18080', '192.168.240.1', '18080', '', '')))
RULE = ['allow', 'in', 'on', 'waydroid0', 'to', '192.168.240.1', 'port', '18080', 'proto', 'tcp']
UNIT = 'waydroid-network-proxy.service'
HOME = Path.home()
STATE = HOME / '.local/state/cachyos-waydroid/network.json'
HELPER = Path(__file__).resolve().with_name('waydroid-network-settings.py')


def run(args, **kwargs):
    kwargs.setdefault('timeout', 10)
    kwargs.setdefault('capture_output', True)
    return subprocess.run(args, text=True, **kwargs)


def command(args, **kwargs):
    result = run(args, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]} {' '.join(args[1:3])}")
    return result.stdout


def settings(values=None):
    args = ['/usr/bin/python3', str(HELPER), 'get' if values is None else 'set']
    output = command(args, **({} if values is None else {'input': json.dumps(values)}))
    result = json.loads(output)
    if not isinstance(result, dict) or set(result) != set(KEYS) or any(v is not None and not isinstance(v, str) for v in result.values()):
        raise RuntimeError('Invalid settings returned by helper')
    return result


def normalized(values):
    return tuple(None if values[k] in (None, '', 'null') or (k == 'global_http_proxy_port' and values[k] == '0') else values[k] for k in KEYS)


def matches(a, b):
    return normalized(a) == normalized(b)


def empty(values):
    return all(v is None for v in normalized(values))


def migration(values):
    temporary = dict(zip(KEYS, ('127.0.0.1:18080', '127.0.0.1', '18080', '', '')))
    return matches(values, temporary)


def load():
    if not STATE.exists():
        return None
    return json.loads(STATE.read_text())


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE.parent, 0o700)
    fd, name = tempfile.mkstemp(dir=STATE.parent, prefix='.network-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f)
            f.write('\n')
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def running():
    result = run(['waydroid', 'status'])
    lines = result.stdout.lower().splitlines()
    return result.returncode == 0 and any('session:' in line and 'running' in line for line in lines) and any('container:' in line and 'running' in line for line in lines)


def ensure_session():
    if not running():
        command([str(HOME / '.local/bin/launch-waydroid'), '--ensure-session'], timeout=130)


def set_verified(values):
    if not matches(settings(values), values):
        raise RuntimeError('Android proxy settings did not match the requested values')


def apply(state, if_running=False):
    if if_running and not running():
        return
    if not if_running:
        ensure_session()
    current = settings()
    if not (empty(current) or matches(current, state['original']) or matches(current, MANAGED) or (state.get('migration') and migration(current))):
        raise RuntimeError('Android proxy settings were changed; leaving them untouched')
    set_verified(MANAGED)


def restore(state, if_running=False):
    if if_running and not running():
        return
    if not if_running:
        ensure_session()
    current = settings()
    if matches(current, MANAGED) or (state.get('migration') and migration(current)):
        set_verified(state['original'])
    elif not matches(current, state['original']):
        raise RuntimeError('Android proxy settings were changed; leaving them untouched')


def firewall_available():
    if run(['systemctl', 'is-active', '--quiet', 'firewalld']).returncode == 0:
        raise RuntimeError('Active firewalld is not supported; configure the Waydroid proxy rule manually')
    if not shutil.which('ufw'):
        return False
    result = run(['sudo', '-v'], capture_output=False, timeout=120)
    if result.returncode:
        raise RuntimeError('Could not authenticate for UFW')
    return True


def ufw_command(args):
    return command(['sudo', 'ufw'] + args, env={**os.environ, 'LC_ALL': 'C'})


def ufw_active():
    output = ufw_command(['status'])
    return 'status: active' in output.lower()


def ufw_has_rule():
    output = ufw_command(['show', 'added'])
    for line in output.splitlines():
        try:
            words = shlex.split(line.strip())
        except ValueError:
            continue
        if words[:1] == ['ufw']:
            words = words[1:]
        if words[:2] != ['allow', 'in']:
            continue
        words = words[2:]
        fields = {}
        while len(words) >= 2:
            key, value, *words = words
            if key in fields:
                break
            fields[key] = value
        else:
            if not words and fields in (
                {'on': 'waydroid0', 'to': '192.168.240.1', 'port': '18080', 'proto': 'tcp'},
                {'on': 'waydroid0', 'from': 'any', 'to': '192.168.240.1', 'port': '18080', 'proto': 'tcp'},
            ):
                return True
    return False


def wait_listener():
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('192.168.240.1', 18080), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError('Waydroid proxy listener did not become ready')


def enable(previous):
    ensure_session()
    current = settings()
    state = load()
    if state is None:
        original = current
        if previous:
            original = json.loads(Path(previous).read_text())
            if not isinstance(original, dict) or set(original) != set(KEYS) or any(v is not None and not isinstance(v, str) for v in original.values()):
                raise RuntimeError('Previous settings must contain the five proxy keys')
        if not (empty(current) or matches(current, MANAGED) or (previous and migration(current))):
            raise RuntimeError('Existing Android proxy is not managed; leaving it untouched')
        state = {'original': original, 'migration': bool(previous), 'enabled': False, 'ufw_owned': False}
    elif not (empty(current) or matches(current, state['original']) or matches(current, MANAGED) or (state.get('migration') and migration(current))):
        raise RuntimeError('Existing Android proxy is not managed; leaving it untouched')
    was_enabled = run(['systemctl', '--user', 'is-enabled', UNIT]).returncode == 0
    was_active = run(['systemctl', '--user', 'is-active', UNIT]).returncode == 0
    added_rule = False
    firewall = firewall_available()
    old_enabled = state.get('enabled', False)
    try:
        if firewall and ufw_active() and not ufw_has_rule():
            output = ufw_command(RULE)
            added_rule = 'skipping adding existing rule' not in output.lower()
            if added_rule:
                state['ufw_owned'] = True
        state['enabled'] = True
        save(state)
        command(['systemctl', '--user', 'enable', '--now', UNIT], timeout=40)
        wait_listener()
        apply(state)
    except Exception as error:
        try:
            set_verified(current)
        except Exception as rollback_error:
            service = run(['systemctl', '--user', 'enable', '--now', UNIT], timeout=40)
            state['enabled'] = True
            save(state)
            detail = 'proxy service and firewall rule were kept for retry' if service.returncode == 0 else 'firewall rule was kept, but the proxy service could not be started'
            raise RuntimeError(f'Enable failed and Android settings rollback failed; {detail}') from rollback_error
        if not was_active:
            run(['systemctl', '--user', 'stop', UNIT])
        if not was_enabled:
            run(['systemctl', '--user', 'disable', UNIT])
        if added_rule:
            ufw_command(['--force', 'delete'] + RULE)
            state['ufw_owned'] = False
        state['enabled'] = old_enabled
        save(state)
        raise


def disable(state):
    restore(state)
    command(['systemctl', '--user', 'disable', '--now', UNIT])
    if state.get('ufw_owned'):
        if not firewall_available():
            raise RuntimeError('UFW is unavailable; cannot remove owned firewall rule')
        if ufw_active() and ufw_has_rule():
            ufw_command(['--force', 'delete'] + RULE)
        state['ufw_owned'] = False
    state['enabled'] = False
    save(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('enable').add_argument('--previous-settings')
    sub.add_parser('disable')
    sub.add_parser('status')
    for action in ('apply', 'restore'):
        sub.add_parser(action).add_argument('--if-running', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'enable':
            enable(args.previous_settings)
        elif args.action == 'status':
            state = load()
            active = run(['systemctl', '--user', 'is-active', UNIT]).returncode == 0
            print(f"Enabled: {'yes' if state and state.get('enabled') else 'no'}; service: {'active' if active else 'inactive'}")
            if running():
                current = settings()
                print('Android proxy:', 'managed' if matches(current, MANAGED) else 'unset' if empty(current) else 'custom')
            else:
                print('Android proxy: unavailable')
        else:
            state = load()
            if state is None:
                if args.action in ('apply', 'restore') and args.if_running:
                    return
                raise RuntimeError('No saved Waydroid proxy state')
            if args.action == 'disable':
                disable(state)
            elif args.action == 'apply':
                if state.get('enabled'):
                    apply(state, args.if_running)
            else:
                restore(state, args.if_running)
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'waydroid-network: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
