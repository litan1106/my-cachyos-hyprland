import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock


spec = importlib.util.spec_from_file_location('network_settings',
    Path(__file__).resolve().parents[1] / 'scripts/waydroid-network-settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class SettingsTests(unittest.TestCase):
    def platform(self, value=None, exception=0):
        platform = Mock()
        payload = platform.client.new_request.return_value
        def reader():
            result = Mock()
            result.read_int32.side_effect = [(True, exception), (True, -1 if value is None else len(value))]
            result.read_string16.return_value = value
            readers.append(result)
            return result
        readers = []
        reply = Mock()
        reply.readers = readers
        reply.init_reader.side_effect = reader
        platform.client.transact_sync_reply.return_value = (reply, 0)
        return platform, payload, reply

    def test_null_read_avoids_native_string_reader(self):
        platform, payload, reply = self.platform()
        self.assertIsNone(settings.get_string(platform, 'http_proxy'))
        self.assertTrue(all(not reader.read_string16.called for reader in reply.readers))
        self.assertEqual(payload.append_int32.call_args.args, (2,))

    def test_nonempty_and_empty_strings_are_preserved(self):
        for value in ('', '192.168.240.1:18080'):
            with self.subTest(value=value):
                platform, _, reply = self.platform(value)
                self.assertEqual(settings.get_string(platform, 'http_proxy'), value)

    def test_null_write_uses_parcel_null_marker(self):
        platform, payload, _ = self.platform()
        settings.request(platform, settings.PUT_STRING, 'http_proxy', None)
        self.assertEqual([call.args for call in payload.append_int32.call_args_list], [(2,), (0xffffffff,)])
        self.assertEqual([call.args for call in payload.append_string16.call_args_list], [('http_proxy',)])

    def test_service_errors_are_not_reported_as_success(self):
        platform, _, _ = self.platform(exception=1)
        with self.assertRaises(RuntimeError):
            settings.get_string(platform, 'http_proxy')

    def test_rejects_unrelated_or_invalid_settings_before_any_write(self):
        for values in ({'adb_enabled': '1'}, {'http_proxy': 3}, [], {'http_proxy': 'x' * 4097}):
            with self.subTest(values=str(values)[:80]):
                platform, payload, _ = self.platform()
                with self.assertRaises(ValueError):
                    settings.write_settings(platform, values)
                payload.append_string16.assert_not_called()


if __name__ == '__main__':
    unittest.main()
