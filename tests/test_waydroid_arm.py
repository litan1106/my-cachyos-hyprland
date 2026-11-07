import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install-waydroid-arm.sh'


class ArmTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'log'
        self.config = self.root / 'waydroid/waydroid.cfg'
        self.config.parent.mkdir()
        self.config.write_text('[waydroid]\nmount_overlays=True\n')
        self.env = dict(os.environ, HOME=str(self.root), PATH=f'{self.bin}:{os.environ["PATH"]}', TEST_LOG=str(self.log))
        mock = '''#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['TEST_LOG'], 'a') as f: f.write(json.dumps([name] + args) + '\\n')
if name == 'uname': print(os.getenv('ARCH', 'x86_64'))
elif name == 'launch-waydroid.sh': sys.exit(int(os.getenv('READY_FAIL', '0')))
elif name == 'waydroid' and args[:2] == ['prop', 'get']:
    prop = args[2]
    state = pathlib.Path(os.environ['HOME']) / 'installed'
    values = {'ro.build.version.sdk': os.getenv('SDK', '33'), 'ro.dalvik.vm.native.bridge': os.getenv('BRIDGE', '0'), 'ro.product.cpu.abilist': os.getenv('ABIS', 'x86_64,x86')}
    if state.exists() and prop == 'ro.dalvik.vm.native.bridge': values[prop] = os.getenv('POST_BRIDGE', 'libndk_translation.so')
    if state.exists() and prop == 'ro.product.cpu.abilist': values[prop] = os.getenv('POST_ABIS', 'x86_64,arm64-v8a')
    print(values[prop])
elif name == 'git':
    if args[0] == 'clone': (pathlib.Path(args[-1]) / '.git').mkdir(parents=True)
    elif 'rev-parse' in args: print(os.getenv('GIT_HEAD', '48dbfaf34a6ddbe78688c530f9ba1c26522aafb2'))
    elif 'status' in args: print(os.getenv('GIT_DIRTY', ''))
    elif 'remote' in args: print('https://github.com/casualsnek/waydroid_script.git')
elif name == 'uv' and args[0] == 'venv':
    p = pathlib.Path(args[1]) / 'bin/python'; p.parent.mkdir(parents=True); p.write_text(''); p.chmod(0o755)
elif name == 'sudo' and 'main.py' in args:
    if 'install' in args: (pathlib.Path(os.environ['HOME']) / 'installed').touch()
    sys.exit(int(os.getenv('TOOL_FAIL', '0')))
'''
        for name in ['uname', 'waydroid', 'launch-waydroid.sh', 'git', 'uv', 'sudo', 'systemctl']:
            p = self.bin / name
            p.write_text(mock)
            p.chmod(0o755)
        script = SCRIPT.read_text().replace('/var/lib/waydroid', str(self.config.parent))
        (self.bin / 'install-waydroid-arm.sh').write_text(script)

    def run_script(self, *args, **env):
        return subprocess.run(['bash', str(self.bin / 'install-waydroid-arm.sh'), *args], capture_output=True, text=True, env=dict(self.env, **env), timeout=5)

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_help_and_selection(self):
        self.assertEqual(self.run_script('--help').returncode, 0)
        for args in [(), ('libndk', 'libhoudini'), ('--remove',), ('unknown',)]:
            self.assertNotEqual(self.run_script(*args).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_invalid_platform_does_not_modify(self):
        for env in [dict(ARCH='aarch64'), dict(SDK='32'), dict(SDK='')]:
            self.log.unlink(missing_ok=True)
            self.assertNotEqual(self.run_script('libndk', **env).returncode, 0)
            self.assertFalse(any(c[0] in ('sudo', 'git', 'uv') for c in self.calls()))

    def test_conflicting_and_existing_translation(self):
        self.assertNotEqual(self.run_script('libndk', BRIDGE='libhoudini.so', ABIS='x86_64,arm64-v8a').returncode, 0)
        self.assertEqual(self.run_script('libndk', BRIDGE='libndk_translation.so', ABIS='x86_64,arm64-v8a').returncode, 0)
        self.assertFalse(any(c[0] in ('sudo', 'git', 'uv') for c in self.calls()))

    def test_install_and_postcheck(self):
        result = self.run_script('libndk')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[0] == 'sudo' and c[-4:] == ['--android-version', '13', 'install', 'libndk'] for c in self.calls()))
        (self.root / 'installed').unlink()
        result = self.run_script('libndk', POST_ABIS='x86_64')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('install-waydroid-arm --remove libndk', result.stderr)

    def test_unsupported_overlay_config_rejected_before_modifications(self):
        for config in ['[waydroid]\nmount_overlays=False\n', '[waydroid]\nmount_overlays=invalid\n',
                       '[waydroid]\n', None]:
            for args in [('libndk',), ('--remove', 'libndk')]:
                with self.subTest(config=config, args=args):
                    self.log.unlink(missing_ok=True)
                    if config is None:
                        self.config.unlink(missing_ok=True)
                    else:
                        self.config.write_text(config)
                    result = self.run_script(*args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('overlay', result.stderr.lower())
                    self.assertFalse(any(c[0] in ('sudo', 'git', 'uv') for c in self.calls()))

    def test_empty_stock_bridge_is_installable(self):
        result = self.run_script('libndk', BRIDGE='')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(c[0] == 'sudo' and 'PYTHONDONTWRITEBYTECODE=1' in c for c in self.calls()))
        self.assertTrue(any(c[0] == 'uv' and '-r' in c and c[-1].endswith('/requirements.txt') for c in self.calls()))

    def test_rejects_modified_or_wrong_checkout(self):
        checkout = self.root / '.cache/cachyos-waydroid/waydroid_script-48dbfaf34a6ddbe78688c530f9ba1c26522aafb2'
        (checkout / '.git').mkdir(parents=True)
        for env in [dict(GIT_DIRTY=' M main.py'), dict(GIT_HEAD='wrong')]:
            self.log.unlink(missing_ok=True)
            result = self.run_script('libndk', **env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('refusing', result.stderr)
            self.assertFalse(any(c[0] == 'uv' or 'main.py' in c for c in self.calls()))

    def test_upstream_failure_prints_rollback(self):
        result = self.run_script('libndk', TOOL_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('install-waydroid-arm --remove libndk', result.stderr)
        self.assertFalse(any('restart' in c for c in self.calls()))

    def test_remove_when_android_is_not_ready(self):
        result = self.run_script('--remove', 'libhoudini', READY_FAIL='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(c[0] == 'launch-waydroid.sh' for c in self.calls()))
        self.assertTrue(any(c[0] == 'sudo' and c[-4:] == ['--android-version', '13', 'remove', 'libhoudini'] for c in self.calls()))


if __name__ == '__main__':
    unittest.main()
