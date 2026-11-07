import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


class WaydroidApkTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / 'calls.jsonl'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_CALLS=str(self.log))
        self.write_command('waydroid', '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_CALLS'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
args = sys.argv[1:]
if args[:2] == ['prop', 'get']:
    values = {
        'ro.product.cpu.abilist': os.environ.get('TEST_ANDROID_ABIS', 'x86_64,x86'),
        'ro.product.cpu.abi': os.environ.get('TEST_ANDROID_PRIMARY_ABI', 'x86_64'),
        'ro.dalvik.vm.native.bridge': os.environ.get('TEST_NATIVE_BRIDGE', '0'),
    }
    print(values.get(args[2], ''))
elif args[:2] == ['app', 'install']:
    print(os.environ.get('TEST_INSTALL_OUTPUT', ''), file=sys.stderr)
    sys.exit(int(os.environ.get('TEST_INSTALL_EXIT', '0')))
elif args == ['app', 'list']:
    print('Name: Example\\npackageName: org.example.app')
    sys.exit(int(os.environ.get('TEST_LIST_EXIT', '0')))
''')

    def write_command(self, name, content):
        command = self.bin / name
        command.write_text(content)
        command.chmod(0o755)
        return command

    def prepare_installer(self, installed=False):
        destination = self.bin / ('install-waydroid-apk' if installed else 'install-waydroid-apk.sh')
        shutil.copy2(SCRIPTS / 'install-waydroid-apk.sh', destination)
        launcher = 'launch-waydroid' if installed else 'launch-waydroid.sh'
        self.write_command(launcher, '''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['TEST_CALLS'], 'a') as f:
    f.write(json.dumps(['launcher'] + sys.argv[1:]) + '\\n')
sys.exit(int(os.environ.get('TEST_READY_EXIT', '0')))
''')
        return destination

    def make_apk(self, name='应用 with spaces.apk', abi=None, manifest=True):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            if manifest:
                archive.writestr('AndroidManifest.xml', b'manifest fixture')
            if abi:
                archive.writestr(f'lib/{abi}/libexample.so', b'library fixture')
            archive.writestr('classes.dex', b'dex fixture')
        return path

    def run_installer(self, *args, installed=False, **overrides):
        script = self.prepare_installer(installed)
        return subprocess.run(['bash', str(script), *map(str, args)],
                              text=True, capture_output=True, timeout=5,
                              env=dict(self.env, **overrides))

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_help_and_argument_errors_do_not_start_android(self):
        result = self.run_installer('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        for args in [(), ('--unknown',), ('one.apk', 'two.apk'), (self.root / 'missing.apk',)]:
            with self.subTest(args=args):
                result = self.run_installer(*args)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_bad_archives_are_rejected_before_startup(self):
        invalid = self.root / 'invalid.apk'
        invalid.write_text('not a zip')
        for path in [invalid, self.make_apk('missing-manifest.apk', manifest=False), self.root]:
            with self.subTest(path=path):
                result = self.run_installer(path)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_valid_apk_path_is_preserved_in_both_locations(self):
        apk = self.make_apk(abi='x86_64')
        for installed in [False, True]:
            with self.subTest(installed=installed):
                self.log.unlink(missing_ok=True)
                result = self.run_installer(apk, installed=installed)
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = self.calls()
                self.assertEqual(calls[0], ['launcher', '--ensure-session'])
                self.assertIn(['app', 'install', str(apk)], calls)
                self.assertLess(calls.index(['app', 'install', str(apk)]), calls.index(['app', 'list']))
                self.assertIn('org.example.app', result.stdout)

    def test_readiness_failure_prevents_installation(self):
        result = self.run_installer(self.make_apk(), TEST_READY_EXIT='9')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [['launcher', '--ensure-session']])

    def test_arm_only_apk_prints_compatibility_guidance(self):
        result = self.run_installer(self.make_apk(abi='arm64-v8a'))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ARM', result.stdout + result.stderr)
        self.assertIn('translation', result.stdout + result.stderr)
        self.assertFalse(any(call[:2] == ['app', 'install'] for call in self.calls()))

    def test_unknown_abis_prevent_installation(self):
        result = self.run_installer(self.make_apk(abi='arm64-v8a'), TEST_ANDROID_ABIS='')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(call[:2] == ['app', 'install'] for call in self.calls()))

    def test_advertised_arm_abi_requires_bridge_on_x86_android(self):
        result = self.run_installer(self.make_apk(abi='arm64-v8a'),
                                    TEST_ANDROID_ABIS='x86_64,x86,arm64-v8a')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bridge', result.stderr)
        self.assertFalse(any(call[:2] == ['app', 'install'] for call in self.calls()))

    def test_arm_abi_with_bridge_is_installable(self):
        apk = self.make_apk(abi='arm64-v8a')
        result = self.run_installer(apk, TEST_ANDROID_ABIS='x86_64,x86,arm64-v8a',
                                    TEST_NATIVE_BRIDGE='libndk_translation.so')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['app', 'install', str(apk)], self.calls())

    def test_native_arm_android_does_not_need_translation(self):
        apk = self.make_apk(abi='arm64-v8a')
        result = self.run_installer(apk, TEST_ANDROID_ABIS='arm64-v8a,armeabi-v7a',
                                    TEST_ANDROID_PRIMARY_ABI='arm64-v8a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['app', 'install', str(apk)], self.calls())

    def test_native_abi_does_not_warn_about_translation(self):
        result = self.run_installer(self.make_apk(abi='x86_64'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('translation', result.stderr)

    def test_install_errors_are_not_reported_as_success(self):
        apk = self.make_apk()
        for status, output in [('7', 'install failed'), ('0', '[12:00:00] ERROR: Failed to access IPlatform service'),
                               ('0', 'Failure [INSTALL_FAILED_NO_MATCHING_ABIS]')]:
            with self.subTest(status=status, output=output):
                self.log.unlink(missing_ok=True)
                result = self.run_installer(apk, TEST_INSTALL_EXIT=status, TEST_INSTALL_OUTPUT=output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(output, result.stderr)
                self.assertNotIn(['app', 'list'], self.calls())

    def test_listing_error_is_visible(self):
        result = self.run_installer(self.make_apk(), TEST_LIST_EXIT='4')
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
