#!/usr/bin/env python3
"""Read or write proxy settings through Waydroid's platform service."""

import argparse
import json
import sys


KEYS = ('http_proxy', 'global_http_proxy_host', 'global_http_proxy_port',
        'global_http_proxy_exclusion_list', 'global_proxy_pac_url')
GLOBAL = 2
GET_STRING = 10
PUT_STRING = 9


def request(platform, transaction, key, value=None):
    payload = platform.client.new_request()
    payload.append_int32(GLOBAL)
    payload.append_string16(key)
    if transaction == PUT_STRING:
        if value is None:
            # python-gbinder's string helpers crash on null; encode Parcel's null length.
            payload.append_int32(0xffffffff)
        else:
            payload.append_string16(value)
    reply, status = platform.client.transact_sync_reply(transaction, payload)
    if status or reply is None:
        raise RuntimeError('Waydroid settings transaction failed')
    reader = reply.init_reader()
    valid, exception = reader.read_int32()
    if not valid or exception:
        raise RuntimeError('Android rejected the proxy settings transaction')
    return reply


def get_string(platform, key):
    reply = request(platform, GET_STRING, key)
    reader = reply.init_reader()
    reader.read_int32()
    valid, length = reader.read_int32()
    if not valid or length < -1 or length > 16384:
        raise RuntimeError('Invalid settings response')
    if length == -1:
        return None
    reader = reply.init_reader()
    reader.read_int32()
    return reader.read_string16()


def read_settings(platform):
    return {key: get_string(platform, key) for key in KEYS}


def write_settings(platform, values):
    if not isinstance(values, dict) or not values or set(values) - set(KEYS):
        raise ValueError('Only Android proxy settings may be changed')
    for value in values.values():
        if value is not None and (not isinstance(value, str) or len(value) > 4096):
            raise ValueError('Proxy setting values must be strings or null')
    for key, value in values.items():
        request(platform, PUT_STRING, key, value)
    return read_settings(platform)


def connect():
    sys.path.insert(0, '/usr/lib/waydroid')
    import tools
    from tools.interfaces import IPlatform
    args = argparse.Namespace()
    tools.prep_args(args)
    platform = IPlatform.get_service(args)
    if platform is None:
        raise RuntimeError('Waydroid platform service is unavailable')
    return platform


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('get', 'set'))
    args = parser.parse_args()
    try:
        values = json.load(sys.stdin) if args.action == 'set' else None
        platform = connect()
        result = write_settings(platform, values) if args.action == 'set' else read_settings(platform)
        print(json.dumps(result))
    except (OSError, RuntimeError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
