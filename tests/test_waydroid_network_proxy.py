import importlib.util
import ipaddress
import json
import socket
import threading
import unittest
from unittest import mock
from pathlib import Path

spec = importlib.util.spec_from_file_location('proxy', Path(__file__).parents[1] / 'scripts/waydroid-network-proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class ProxyTests(unittest.TestCase):
    def test_public_addresses_only(self):
        with mock.patch.object(proxy.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 0)), (2, 1, 6, '', ('8.8.8.8', 0))]):
            self.assertEqual(proxy.Resolver().addresses('example.com'), ['8.8.8.8'])

    def test_doh_cache_and_filter(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({'Answer': [{'type': 1, 'data': '8.8.8.8'}, {'type': 1, 'data': '192.168.1.1'}, {'type': 1, 'data': 'invalid'}]}).encode()
        with mock.patch.object(proxy.urllib.request, 'urlopen', return_value=response) as urlopen:
            resolver = proxy.Resolver()
            self.assertEqual(resolver.addresses('app.bytetos.com'), ['8.8.8.8'])
            self.assertEqual(resolver.addresses('app.bytetos.com'), ['8.8.8.8'])
            self.assertEqual(urlopen.call_count, 1)

    def test_freebind_enabled_before_bind(self):
        with mock.patch.object(proxy.socket.socket, 'setsockopt', autospec=True) as option:
            with proxy.Server(('127.0.0.2', 0), proxy.Handler, freebind=True):
                self.assertTrue(any(call.args[-3:] == (socket.SOL_IP, 15, 1) for call in option.call_args_list))

    def test_client_and_target_restrictions(self):
        self.assertTrue(proxy.allowed_client('127.0.0.1', ipaddress.ip_network('192.168.240.0/24')))
        self.assertFalse(proxy.allowed_client('10.0.0.1', ipaddress.ip_network('192.168.240.0/24')))
        for request in (b'CONNECT example.com:22 HTTP/1.1\r\n\r\n', b'bad\r\n\r\n', b'GET / HTTP/1.1\r\n\r\n'):
            with self.assertRaises(ValueError):
                proxy.parse_request(request)

    def test_connect_and_http_relay(self):
        for request, expected in [(b'CONNECT example.com:443 HTTP/1.1\r\n\r\n', b'opaque\x00tls'), (b'GET http://example.com/a?q=1 HTTP/1.1\r\nHost: example.com\r\n\r\n', b'GET /a?q=1 HTTP/1.1\r\nHost: example.com\r\n\r\n')]:
            with self.subTest(request=request):
                upstream, peer = socket.socketpair()
                with proxy.Server(('127.0.0.1', 0), proxy.Handler) as server:
                    server.connector = lambda host, port: upstream
                    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                    with socket.create_connection(server.server_address) as client:
                        client.settimeout(2); peer.settimeout(2)
                        client.sendall(request)
                        if request.startswith(b'CONNECT'):
                            self.assertIn(b'200', client.recv(1024)); client.sendall(expected)
                        self.assertEqual(peer.recv(4096), expected)
                        client.shutdown(socket.SHUT_WR)
                        self.assertEqual(peer.recv(1), b'')
                        peer.sendall(b'reply'); peer.shutdown(socket.SHUT_WR)
                        self.assertEqual(client.recv(1024), b'reply')
                    server.shutdown(); thread.join(); peer.close()

    def test_header_limit(self):
        with self.assertRaises(ValueError):
            proxy.parse_request(b'GET http://example.com/ HTTP/1.1\r\nX: ' + b'a' * 16384 + b'\r\n\r\n')


if __name__ == '__main__':
    unittest.main()
