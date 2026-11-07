#!/usr/bin/env python3
"""Restricted HTTP proxy for Waydroid's Hongguo network traffic."""
import argparse
from collections import OrderedDict
import ipaddress
import json
import logging
import select
import signal
import socket
import socketserver
import threading
import time
import urllib.parse
import urllib.request

DOMAINS = ('fqnovel.com', 'snssdk.com', 'bytedance.com', 'byteimg.com',
           'fqnovelpic.com', 'fqnovelstatic.com', 'hongguoduanju.com',
           'novelquickapp.com', 'zijieapi.com', 'bytedance.net', 'bytegecko.com',
           'bytetos.com')
HEADER_LIMIT = 16384
BUFFER_LIMIT = 1024 * 1024
LOG = logging.getLogger('waydroid-proxy')


def public_ip(value):
    try:
        address = ipaddress.ip_address(value)
        return address.is_global
    except ValueError:
        return False


class Resolver:
    def __init__(self):
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def addresses(self, host):
        if any(host == domain or host.endswith('.' + domain) for domain in DOMAINS):
            with self.lock:
                entry = self.cache.get(host)
                if entry and entry[0] > time.monotonic():
                    self.cache.move_to_end(host)
                    return entry[1][:]
            query = urllib.parse.urlencode({'name': host, 'type': 'A', 'edns_client_subnet': '114.114.114.0/24'})
            with urllib.request.urlopen('https://dns.google/resolve?' + query, timeout=6) as response:
                result = json.load(response)
            ips = []
            for answer in result.get('Answer', []):
                value = answer.get('data', '')
                try:
                    if answer.get('type') == 1 and isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address) and public_ip(value):
                        ips.append(value)
                except ValueError:
                    continue
            with self.lock:
                self.cache[host] = (time.monotonic() + 60, ips)
                self.cache.move_to_end(host)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
            return ips[:]
        return list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM) if public_ip(item[4][0])))


def allowed_client(address, network):
    peer = ipaddress.ip_address(address)
    return peer.is_loopback or peer in network


def parse_request(data):
    end = data.find(b'\r\n\r\n')
    if end < 0 or end + 4 > HEADER_LIMIT:
        raise ValueError('invalid header')
    lines = data[:end].split(b'\r\n')
    try:
        method, target, version = lines[0].decode('ascii').split(' ')
        if not method or version not in ('HTTP/1.0', 'HTTP/1.1') or any(b':' not in line or line[:1] in b' \t' for line in lines[1:]):
            raise ValueError('invalid request')
        if method == 'CONNECT':
            parsed = urllib.parse.urlsplit('//' + target)
            host, port = parsed.hostname, parsed.port
            if parsed.path or parsed.query or parsed.fragment:
                raise ValueError('invalid authority')
            initial = data[end + 4:]
        else:
            parsed = urllib.parse.urlsplit(target)
            if parsed.scheme.lower() != 'http' or parsed.fragment:
                raise ValueError('invalid URL')
            host, port = parsed.hostname, parsed.port or 80
            path = urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            initial = (method + ' ' + path + ' ' + version).encode('ascii') + b'\r\n' + b''.join(line + b'\r\n' for line in lines[1:]) + b'\r\n' + data[end + 4:]
        if not host or port not in (80, 443) or parsed.username is not None or parsed.password is not None:
            raise ValueError('invalid destination')
        return method, host, port, initial
    except (UnicodeError, ValueError) as exc:
        raise ValueError('invalid request') from exc


def relay(client, upstream, initial=b''):
    sockets = (client, upstream)
    pending = {client: bytearray(), upstream: bytearray(initial)}
    reading = set(sockets)
    for sock in sockets:
        sock.setblocking(False)
    while reading or any(pending.values()):
        readable = [src for src in reading if len(pending[upstream if src is client else client]) < BUFFER_LIMIT]
        ready, writable, _ = select.select(readable, [sock for sock in sockets if pending[sock]], [], 60)
        if not ready and not writable:
            return
        for src in ready:
            dst = upstream if src is client else client
            data = src.recv(min(65536, BUFFER_LIMIT - len(pending[dst])))
            if data:
                pending[dst].extend(data)
            else:
                reading.remove(src)
                if not pending[dst]:
                    dst.shutdown(socket.SHUT_WR)
        for dst in writable:
            sent = dst.send(pending[dst])
            del pending[dst][:sent]
            src = upstream if dst is client else client
            if not pending[dst] and src not in reading:
                dst.shutdown(socket.SHUT_WR)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        host = None
        try:
            if not allowed_client(self.client_address[0], self.server.allow_network):
                return
            client = self.request
            client.settimeout(60)
            data = b''
            while b'\r\n\r\n' not in data:
                chunk = client.recv(min(4096, HEADER_LIMIT + 1 - len(data)))
                if not chunk:
                    return
                data += chunk
                if len(data) > HEADER_LIMIT and b'\r\n\r\n' not in data[:HEADER_LIMIT]:
                    return
            method, host, port, initial = parse_request(data)
            with self.server.connector(host, port) as upstream:
                if method == 'CONNECT':
                    client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                relay(client, upstream, initial)
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            if host:
                LOG.warning('Connection failed: %s', host)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, handler, freebind=None):
        self.allow_network = ipaddress.ip_network('192.168.240.0/24')
        self.resolver = Resolver()
        self.slots = threading.BoundedSemaphore(64)
        self.freebind = not ipaddress.ip_address(address[0]).is_loopback if freebind is None else freebind
        super().__init__(address, handler)

    def server_bind(self):
        if self.freebind:
            self.socket.setsockopt(socket.SOL_IP, 15, 1)
        super().server_bind()

    def connector(self, host, port):
        for address in self.resolver.addresses(host):
            try:
                upstream = socket.create_connection((address, port), timeout=4)
                LOG.debug('Connected %s %s', host, address)
                return upstream
            except OSError:
                continue
        raise OSError('connection failed')

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        LOG.debug('Request failed', exc_info=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='192.168.240.1')
    parser.add_argument('--port', type=int, default=18080)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    with Server((args.bind, args.port), Handler) as server:
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        LOG.info('Listening on %s:%s', args.bind, args.port)
        server.serve_forever()


if __name__ == '__main__':
    main()
