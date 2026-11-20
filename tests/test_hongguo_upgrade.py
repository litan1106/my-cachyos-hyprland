import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'hongguo-upgrade.py'
spec = importlib.util.spec_from_file_location('hongguo_upgrade', SCRIPT)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)

class UpgradeTests(unittest.TestCase):
    def test_local_check_does_not_mutate_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installer = root / 'setup.exe'
            installer.write_bytes(b'installer')
            home = root / 'home'
            self.assertEqual(upgrade.main(['--home', str(home), '--scripts-dir', str(root), '--installer', str(installer), '--check']), 0)
            self.assertFalse(home.exists())

    def setUp(self):
        import zipfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.scripts = Path(__file__).resolve().parents[1] / 'scripts'
        self.make_backend(self.home / 'backend', 'old')
        (self.home / 'launcher').mkdir()
        (self.home / 'launcher' / 'marker').write_text('old')
        import shutil
        shutil.copy2(self.scripts / 'hongguo-common.sh', self.home / 'launcher/hongguo-common.sh')
        for name in ('data', 'hls', 'venv'):
            (self.home / name).mkdir()
            (self.home / name / 'marker').write_text(name)
        (self.home / 'backend' / 'config.json').write_text('state')
        self.installer = self.root / 'setup.exe'
        new = self.root / 'new'
        self.make_backend(new / 'backend', 'new')
        with zipfile.ZipFile(self.installer, 'w') as z:
            for file in (new / 'backend').rglob('*'):
                if file.is_file():
                    z.write(file, file.relative_to(new))

    def make_backend(self, backend, marker):
        import zipfile
        (backend / 'frida').mkdir(parents=True)
        (backend / 'sign').mkdir()
        for name in upgrade.REQUIRED:
            (backend / name).write_text('marker = ' + repr(marker) + '\n')
        (backend / 'guest-config.json').write_text(json.dumps({'api_host': 'https://example.com', 'base_query': {}, 'session_headers': {}}))
        with zipfile.ZipFile(backend / 'sign' / 'unidbg-sign.jar', 'w') as z:
            z.writestr('x', 'x')

    def invoke(self, *args):
        with mock.patch.dict('os.environ', {'HOME': str(self.root)}):
            return upgrade.main(['--home', str(self.home), '--scripts-dir', str(self.scripts), *args])

    def test_upgrade_and_rollback_preserve_state(self):
        self.assertEqual(self.invoke('--installer', str(self.installer)), 0)
        self.assertIn('new', (self.home / 'backend/server.py').read_text())
        (self.home / 'backend/config.json').write_text('new state')
        self.assertEqual(self.invoke('--rollback'), 0)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())
        self.assertEqual((self.home / 'backend/config.json').read_text(), 'new state')
        for name in ('data', 'hls', 'venv'):
            self.assertEqual((self.home / name / 'marker').read_text(), name)

    def test_invalid_archive_keeps_old_backend(self):
        self.installer.write_bytes(b'invalid')
        self.assertEqual(self.invoke('--installer', str(self.installer)), 1)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())

    def test_apply_failure_restores_old_directories(self):
        original = Path.rename
        def fail_once(path, target):
            if path.name == 'launcher' and path.parent.name.startswith('.upgrade-'):
                raise OSError('simulated failure')
            return original(path, target)
        with mock.patch.object(Path, 'rename', fail_once):
            self.assertEqual(self.invoke('--installer', str(self.installer)), 1)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())
        self.assertEqual((self.home / 'launcher/marker').read_text(), 'old')

    def test_locked_home_refused(self):
        import fcntl
        with (self.home / '.maintenance.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.invoke('--installer', str(self.installer)), 1)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())

    def test_interrupted_swap_restores_old_directories(self):
        original = Path.rename
        def interrupt(path, target):
            if path.name == 'launcher' and path.parent.name.startswith('.upgrade-'):
                raise KeyboardInterrupt()
            return original(path, target)
        with mock.patch.object(Path, 'rename', interrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.invoke('--installer', str(self.installer))
        self.assertIn('old', (self.home / 'backend/server.py').read_text())
        self.assertEqual((self.home / 'launcher/marker').read_text(), 'old')

    def test_termination_waits_for_a_complete_swap(self):
        import os
        import signal
        observations = []
        def observe(signum, frame):
            observations.append(
                'new' in (self.home / 'backend/server.py').read_text()
                and (self.home / 'launcher/upgrade-hongguo').is_file()
                and (self.home / 'native-release.json').is_file())
        previous = signal.signal(signal.SIGTERM, observe)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        original = Path.rename
        def stop_during_swap(path, target):
            if path == self.home / 'backend':
                os.kill(os.getpid(), signal.SIGTERM)
            return original(path, target)
        with mock.patch.object(Path, 'rename', stop_during_swap):
            self.assertEqual(self.invoke('--installer', str(self.installer)), 0)
        self.assertEqual(observations, [True])

    def test_launcher_refuses_maintenance_lock(self):
        import fcntl
        import os
        import subprocess
        app = self.root / '.local/share/hongguo-native'
        app.mkdir(parents=True)
        with (app / '.maintenance.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = subprocess.run(
                [str(self.scripts / 'launch-hongguo.sh'), '--no-open'],
                env=dict(os.environ, HOME=str(self.root)), capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('being upgraded', result.stderr)

    def test_remote_checksum_failure_keeps_old_backend(self):
        asset = 'hongguo-1.2.3-windows-x86_64-setup.exe'
        data = json.dumps({'tag_name': 'v1.2.3', 'assets': [{'name': asset, 'browser_download_url': 'https://example.com/exe'}, {'name': 'SHA256SUMS.txt', 'browser_download_url': 'https://example.com/sums'}]}).encode()
        import io
        with mock.patch.object(upgrade, 'fetch', side_effect=lambda url: data if 'api.github.com' in url else (('0' * 64) + '  ' + asset).encode()), mock.patch.object(upgrade.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
            self.assertEqual(self.invoke(), 1)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())

    def test_remote_latest_check(self):
        asset = 'hongguo-1.2.3-windows-x86_64-setup.exe'
        data = json.dumps({'tag_name': 'v1.2.3', 'assets': [{'name': asset, 'browser_download_url': 'https://example.com/exe'}, {'name': 'SHA256SUMS.txt', 'browser_download_url': 'https://example.com/sums'}]}).encode()
        with mock.patch.object(upgrade, 'fetch', return_value=data) as fetch:
            self.assertEqual(self.invoke('--check'), 0)
        self.assertTrue(fetch.call_args.args[0].endswith('/latest'))
        self.assertFalse((self.home / '.maintenance.lock').exists())

    def test_legacy_backend_running_is_refused(self):
        import subprocess
        process = subprocess.Popen(['python3', '-c', 'import time; time.sleep(30)', 'standalone_server.py'], cwd=self.home / 'backend')
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        self.assertEqual(self.invoke('--installer', str(self.installer)), 1)
        self.assertIn('old', (self.home / 'backend/server.py').read_text())

    def test_installed_upgrade_link_supports_check(self):
        import os
        import subprocess
        self.assertEqual(self.invoke('--installer', str(self.installer)), 0)
        env = dict(os.environ, HOME=str(self.root))
        result = subprocess.run([str(self.root / '.local/bin/upgrade-hongguo'), '--installer', str(self.installer), '--check'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invoke('--rollback'), 0)
        result = subprocess.run([str(self.root / '.local/bin/upgrade-hongguo'), '--installer', str(self.installer), '--check'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
