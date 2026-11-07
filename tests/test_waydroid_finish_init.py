import configparser
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

spec = importlib.util.spec_from_file_location('finish_init', Path(__file__).parents[1] / 'scripts/finish-waydroid-init.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FinishInitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name) / 'waydroid'
        self.images = self.work / 'images'
        self.images.mkdir(parents=True)
        (self.images / 'system.img').write_bytes(b'system')
        self.cfg = self.work / 'waydroid.cfg'
        self.cfg.write_text('[waydroid]\narch = x86_64\nimages_path = ' + str(self.images) + '\nsystem_datetime = 1790512621\nvendor_datetime = 0\nvendor_type = MAINLINE\nsystem_ota = https://ota.waydro.id/system/lineage/waydroid_x86_64/GAPPS.json\nvendor_ota = https://ota.waydro.id/vendor/waydroid_x86_64/MAINLINE.json\n[properties]\nexample = value\n')
        self.archive = Path(self.tmp.name) / 'vendor.zip'
        with zipfile.ZipFile(self.archive, 'w') as z:
            z.writestr('vendor.img', b'vendor')
        data = self.archive.read_bytes()
        self.metadata = {'response': [{'version': '20.0', 'id': hashlib.sha256(data).hexdigest(), 'size': len(data), 'datetime': 1792667170}]}
        self.system_metadata = {'response': [{'datetime': 1790512621}]}
        def response(url, timeout):
            result = mock.MagicMock()
            metadata = self.metadata if url == module.VENDOR_OTA else self.system_metadata
            result.__enter__.return_value.read.return_value = json.dumps(metadata).encode()
            return result
        self.fetch = mock.patch.object(module.urllib.request, 'urlopen', side_effect=response)
        self.run = mock.patch.object(module.subprocess, 'run')
        self.active = mock.patch.object(module, 'init_running', return_value=False)
        self.fetch.start(); self.run_mock = self.run.start(); self.active_mock = self.active.start()
        self.run_mock.side_effect = lambda *args, **kwargs: (self.work / 'rootfs').mkdir()
        self.addCleanup(mock.patch.stopall)

    def test_completes_and_preserves_configuration(self):
        before = self.cfg.read_text()
        module.finish(self.work, self.archive)
        self.assertEqual((self.images / 'vendor.img').read_bytes(), b'vendor')
        self.assertEqual((self.images / 'system.img').read_bytes(), b'system')
        config = configparser.ConfigParser()
        config.read(self.cfg)
        self.assertEqual(config['waydroid']['vendor_datetime'], '1792667170')
        self.assertEqual(config['waydroid']['system_ota'].split('/')[-1], 'GAPPS.json')
        self.assertEqual(config['properties']['example'], 'value')
        self.assertEqual([p.read_text() for p in self.work.glob('waydroid.cfg.backup*')], [before])
        self.run_mock.assert_called_once_with(['waydroid', 'init', '-s', 'GAPPS'], check=True)

    def test_bad_hash_and_active_init_do_not_change_state(self):
        for active in (False, True):
            with self.subTest(active=active):
                self.active_mock.return_value = active
                self.metadata['response'][0]['id'] = '0' * 64
                before = self.cfg.read_bytes()
                with self.assertRaises((ValueError, RuntimeError)):
                    module.finish(self.work, self.archive)
                self.assertEqual(self.cfg.read_bytes(), before)
                self.assertEqual((self.images / 'system.img').read_bytes(), b'system')
                self.assertFalse((self.images / 'vendor.img').exists())

    def test_preserves_vanilla_flavor(self):
        self.cfg.write_text(self.cfg.read_text().replace('GAPPS.json', 'VANILLA.json'))
        module.finish(self.work, self.archive)
        self.run_mock.assert_called_once_with(['waydroid', 'init', '-s', 'VANILLA'], check=True)
        self.assertIn('VANILLA.json', self.cfg.read_text())

    def test_process_guard_handles_global_flags(self):
        for args in ([b'waydroid', b'init'], [b'sudo', b'/usr/bin/waydroid', b'--details-to-stdout', b'init'],
                     [b'/usr/bin/python3', b'/usr/bin/waydroid', b'--work', b'/var/lib/waydroid', b'init']):
            self.assertTrue(module.is_init_command(args))
        self.assertFalse(module.is_init_command([b'waydroid', b'app', b'list']))

    def test_concurrent_init_during_validation_prevents_publish(self):
        self.active_mock.side_effect = [False, True]
        before = self.cfg.read_bytes()
        with self.assertRaises(RuntimeError):
            module.finish(self.work, self.archive)
        self.assertEqual(self.cfg.read_bytes(), before)
        self.assertFalse((self.images / 'vendor.img').exists())

    def test_zero_exit_without_rootfs_is_not_success(self):
        self.run_mock.side_effect = None
        with self.assertRaises(RuntimeError):
            module.finish(self.work, self.archive)

    def test_failed_native_init_retains_verified_images_and_backup(self):
        self.run_mock.side_effect = module.subprocess.CalledProcessError(1, ['waydroid', 'init'])
        with self.assertRaises(module.subprocess.CalledProcessError):
            module.finish(self.work, self.archive)
        self.assertEqual((self.images / 'vendor.img').read_bytes(), b'vendor')
        self.assertTrue(list(self.work.glob('waydroid.cfg.backup*')))

    def test_refuses_stale_official_vendor(self):
        self.metadata['response'].append({'version': '20.0', 'id': 'f' * 64, 'size': 1, 'datetime': 1792667171})
        with self.assertRaises(ValueError):
            module.finish(self.work, self.archive)
        self.assertFalse((self.images / 'vendor.img').exists())

    def test_refuses_newer_official_system(self):
        self.system_metadata['response'][0]['datetime'] += 1
        with self.assertRaises(ValueError):
            module.finish(self.work, self.archive)
        self.assertFalse((self.images / 'vendor.img').exists())

    def test_refuses_unsafe_or_incomplete_state(self):
        for state in ('rootfs', 'vendor', 'config'):
            with self.subTest(state=state):
                original = self.cfg.read_bytes()
                if state == 'rootfs': (self.work / 'rootfs').mkdir()
                if state == 'vendor': (self.images / 'vendor.img').write_bytes(b'existing')
                if state == 'config': self.cfg.write_text('[waydroid]\n')
                with self.assertRaises((ValueError, RuntimeError)):
                    module.finish(self.work, self.archive)
                if state == 'rootfs': (self.work / 'rootfs').rmdir()
                if state == 'vendor': (self.images / 'vendor.img').unlink()
                self.cfg.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
