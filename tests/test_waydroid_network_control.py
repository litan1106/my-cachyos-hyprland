import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('network_control', Path(__file__).parents[1] / 'scripts/waydroid-network.py')
network = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(network)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / 'state/network.json'
        self.original = dict.fromkeys(network.KEYS)
        self.current = self.original.copy()
        self.calls = []
        self.active = False
        self.enabled = False
        self.ufw_rule = False
        self.failure = None
        self.patches = [patch.object(network, 'STATE', self.state_path),
                        patch.object(network, 'HOME', Path(self.temp.name)),
                        patch.object(network, 'run', side_effect=self.run_command),
                        patch.object(network, 'settings', side_effect=self.settings),
                        patch.object(network, 'wait_listener'),
                        patch.object(network.shutil, 'which', return_value='/usr/bin/ufw')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        class Result:
            returncode = 0
            stdout = ''
        result = Result()
        if args[:4] == ['systemctl', 'is-active', '--quiet', 'firewalld']:
            result.returncode = 3
        elif args[:2] == ['waydroid', 'status']:
            result.stdout = 'Session: RUNNING\nContainer: RUNNING\n'
        elif 'is-enabled' in args:
            result.returncode = not self.enabled
        elif 'is-active' in args:
            result.returncode = not self.active
        elif args[:3] == ['sudo', 'ufw', 'status']:
            result.stdout = 'Status: active'
        elif args[:4] == ['sudo', 'ufw', 'show', 'added']:
            result.stdout = 'ufw ' + ' '.join(network.RULE) if self.ufw_rule else ''
        elif self.failure and self.failure in args:
            result.returncode = 1
        return result

    def settings(self, values=None):
        if values is not None:
            self.calls.append(['settings', 'set'])
            self.current = values.copy()
            if self.failure == 'readback':
                return self.original.copy()
            if self.failure == 'readback-once':
                self.failure = None
                return self.original.copy()
        return self.current.copy()

    def test_migration_snapshot_and_reenable(self):
        previous = Path(self.temp.name) / 'previous.json'
        previous.write_text(json.dumps(self.original))
        self.current = dict(zip(network.KEYS, ('127.0.0.1:18080', '127.0.0.1', '18080', '', '')))
        network.enable(str(previous))
        network.enable(None)
        self.assertEqual(network.load()['original'], self.original)
        self.assertEqual(self.current, network.MANAGED)
        self.assertEqual(self.state_path.stat().st_mode & 0o777, 0o600)

    def test_custom_proxy_refused(self):
        self.current['http_proxy'] = 'example:1234'
        with self.assertRaisesRegex(RuntimeError, 'not managed'):
            network.enable(None)
        self.assertFalse(self.state_path.exists())

    def test_disable_restores_before_stopping(self):
        network.enable(None)
        self.calls.clear()
        network.disable(network.load())
        self.assertLess(self.calls.index(['settings', 'set']), self.calls.index(['systemctl', '--user', 'disable', '--now', network.UNIT]))
        self.assertEqual(self.current, self.original)

    def test_failed_restore_keeps_service(self):
        network.enable(None)
        self.calls.clear()
        self.current['http_proxy'] = 'custom:12'
        with self.assertRaisesRegex(RuntimeError, 'changed'):
            network.disable(network.load())
        self.assertFalse(any('disable' in c or 'stop' in c for c in self.calls))

    def test_existing_ufw_rule_is_not_owned(self):
        self.ufw_rule = True
        network.enable(None)
        self.assertFalse(network.load()['ufw_owned'])
        network.disable(network.load())
        self.assertFalse(any(c[:4] == ['sudo', 'ufw', '--force', 'delete'] for c in self.calls))

    def test_unit_failure_rolls_back_added_resources(self):
        self.failure = '--now'
        with self.assertRaises(RuntimeError):
            network.enable(None)
        self.assertTrue(any(c[:4] == ['sudo', 'ufw', '--force', 'delete'] for c in self.calls))
        self.assertFalse(network.load()['enabled'])

    def test_readback_failure_rolls_back(self):
        self.failure = 'readback-once'
        with self.assertRaisesRegex(RuntimeError, 'did not match'):
            network.enable(None)
        self.assertEqual(self.current, self.original)
        self.assertFalse(network.load()['enabled'])


    def test_existing_rule_in_different_order(self):
        with patch.object(network, 'ufw_command', return_value='ufw allow in proto tcp to 192.168.240.1 port 18080 on waydroid0'):
            self.assertTrue(network.ufw_has_rule())

    def test_skipped_ufw_rule_is_not_owned(self):
        original_run = self.run_command
        def run(args, **kwargs):
            result = original_run(args, **kwargs)
            if args[:3] == ['sudo', 'ufw', 'allow']:
                result.stdout = 'Skipping adding existing rule'
            return result
        with patch.object(network, 'run', side_effect=run):
            network.enable(None)
        self.assertFalse(network.load()['ufw_owned'])

    def test_reenable_failure_restores_previous_managed_settings(self):
        network.enable(None)
        self.enabled = self.active = True
        self.failure = '--now'
        self.calls.clear()
        with self.assertRaises(RuntimeError):
            network.enable(None)
        self.assertEqual(self.current, network.MANAGED)
        self.assertFalse(any('stop' in c or 'disable' in c for c in self.calls))

    def test_rollback_failure_keeps_resources(self):
        self.failure = '--now'
        with patch.object(network, 'set_verified', side_effect=RuntimeError('write failed')), self.assertRaisesRegex(RuntimeError, 'rollback failed'):
            network.enable(None)
        self.assertTrue(network.load()['enabled'])
        self.assertFalse(any('stop' in c or 'disable' in c or '--force' in c for c in self.calls))

    def test_if_running_skips_settings(self):
        with patch.object(network, 'running', return_value=False), patch.object(network, 'settings') as get:
            network.apply({'original': self.original}, True)
            network.restore({'original': self.original}, True)
            get.assert_not_called()

    def test_no_adb(self):
        network.enable(None)
        network.disable(network.load())
        self.assertFalse(any('adb' in part for call in self.calls for part in call))


if __name__ == '__main__':
    unittest.main()
