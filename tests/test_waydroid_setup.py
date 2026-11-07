import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class WaydroidSetupTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.state = self.root / 'state'
        self.log = self.root / 'calls.jsonl'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.repo = self.root / 'repo'
        (self.repo / 'scripts').mkdir(parents=True)
        (self.repo / 'applications').mkdir()
        for name in ['install-android-waydroid.sh', 'remove-android-waydroid.sh',
                     'launch-waydroid.sh', 'install-waydroid-apk.sh', 'install-waydroid-arm.sh',
                     'setup-local-bin-path.sh']:
            source = REPO / 'scripts' / name
            destination = self.repo / 'scripts' / name
            shutil.copy2(source, destination)
            if name in ['install-android-waydroid.sh', 'remove-android-waydroid.sh']:
                # Redirect system paths too, so cleanup can only touch temporary data.
                destination.write_text(destination.read_text().replace('/var/lib/waydroid', str(self.state)))
        shutil.copy2(REPO / 'applications/waydroid.desktop', self.repo / 'applications')
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_CALLS=str(self.log), TEST_STATE=str(self.state))
        self.write_command('sudo', '#!/bin/bash\nexec "$@"\n')
        mock = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['TEST_CALLS'], 'a') as f:
    f.write(json.dumps([name] + args) + '\\n')
if name == 'systemctl' and args[:1] == ['is-active']:
    sys.exit(0 if os.environ.get('TEST_SERVICE_ACTIVE') == '1' else 3)
if name == 'waydroid' and args[:1] == ['init']:
    state = Path(os.environ['TEST_STATE'])
    (state / 'images').mkdir(parents=True, exist_ok=True)
    (state / 'rootfs').mkdir(exist_ok=True)
    for image in ('system.img', 'vendor.img'):
        (state / 'images' / image).write_bytes(b'image')
    (state / 'waydroid.cfg').write_text('[waydroid]\\nimages_path = ' + str(state / 'images') + '\\n')
'''
        for name in ['pacman', 'systemctl', 'waydroid', 'update-desktop-database']:
            self.write_command(name, mock)

    def write_command(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_script(self, name, answers='n\n', **overrides):
        return subprocess.run(['bash', str(self.repo / 'scripts' / name)],
                              input=answers, text=True, capture_output=True,
                              env=dict(self.env, **overrides), timeout=5)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def make_initialized(self, custom_images=False):
        images = self.root / 'custom images' if custom_images else self.state / 'images'
        images.mkdir(parents=True)
        (self.state / 'rootfs').mkdir(parents=True, exist_ok=True)
        for image in ['system.img', 'vendor.img']:
            (images / image).write_bytes(b'image')
        (self.state / 'waydroid.cfg').write_text(f'[waydroid]\nimages_path = {images}\n')

    def test_stale_user_directory_does_not_skip_init(self):
        (self.home / '.local/share/waydroid').mkdir(parents=True)
        result = self.run_script('install-android-waydroid.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        init = calls.index(['waydroid', 'init', '-s', 'VANILLA'])
        start = calls.index(['systemctl', 'enable', '--now', 'waydroid-container.service'])
        self.assertLess(init, start)
        for command in ['launch-waydroid', 'install-waydroid-apk', 'install-waydroid-arm']:
            self.assertTrue((self.home / '.local/bin' / command).is_file())

    def test_initialized_setup_refreshes_helpers_without_restart(self):
        self.make_initialized(custom_images=True)
        result = self.run_script('install-android-waydroid.sh', TEST_SERVICE_ACTIVE='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.home / '.local/bin/install-waydroid-apk'
        installed.write_text('old command')
        result = self.run_script('install-android-waydroid.sh', TEST_SERVICE_ACTIVE='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(installed.read_text(), (REPO / 'scripts/install-waydroid-apk.sh').read_text())
        calls = self.calls()
        self.assertFalse(any(call[:2] == ['waydroid', 'init'] for call in calls))
        self.assertFalse(any(call[:2] == ['systemctl', 'restart'] for call in calls))
        self.assertFalse(any(call[:3] == ['systemctl', 'enable', '--now'] for call in calls))

    def test_incomplete_system_is_not_started_or_reset(self):
        self.state.mkdir()
        config = self.state / 'waydroid.cfg'
        config.write_text('[waydroid]\nimages_path = /missing/images\n')
        result = self.run_script('install-android-waydroid.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('incomplete', result.stderr.lower())
        self.assertEqual(config.read_text(), '[waydroid]\nimages_path = /missing/images\n')
        calls = self.calls()
        self.assertFalse(any(call[:2] == ['waydroid', 'init'] for call in calls))
        self.assertFalse(any(call[0] == 'systemctl' for call in calls))

    def test_cleanup_preserves_downloads_and_declined_app_data(self):
        self.make_initialized()
        result = self.run_script('install-android-waydroid.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        profile = self.home / '.local/share/waydroid'
        profile.mkdir(parents=True)
        (profile / 'app-data').write_text('keep')
        apk = self.home / 'download.apk'
        apk.write_text('keep')
        result = self.run_script('remove-android-waydroid.sh', answers='n\nn\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.home / '.local/bin/install-waydroid-apk').exists())
        self.assertFalse((self.home / '.local/bin/install-waydroid-arm').exists())
        self.assertFalse((self.home / '.local/bin/launch-waydroid').exists())
        self.assertEqual((profile / 'app-data').read_text(), 'keep')
        self.assertTrue((self.state / 'waydroid.cfg').exists())
        self.assertEqual(apk.read_text(), 'keep')
        self.assertFalse(any(call[:2] == ['pacman', '-Rns'] for call in self.calls()))


if __name__ == '__main__':
    unittest.main()
