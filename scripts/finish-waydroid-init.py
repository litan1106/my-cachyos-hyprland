#!/usr/bin/env python3
"""Finish a partially downloaded default Waydroid initialization."""

import argparse
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

VENDOR_OTA = 'https://ota.waydro.id/vendor/waydroid_x86_64/MAINLINE.json'
SYSTEM_OTA = 'https://ota.waydro.id/system/lineage/waydroid_x86_64/'


def is_init_command(args):
    return any(os.path.basename(arg) == b'waydroid' and b'init' in args[i + 1:]
               for i, arg in enumerate(args))


def init_running():
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            args = (process / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if is_init_command(args):
            return True
    return False


def finish(work, archive):
    work = Path(work)
    images = work / 'images'
    cfg = work / 'waydroid.cfg'
    if init_running():
        raise RuntimeError('A waydroid init process is running; stop it first.')
    if (work / 'rootfs').exists() or (images / 'vendor.img').exists():
        raise ValueError('Waydroid rootfs or vendor.img already exists.')
    try:
        original = cfg.read_text()
        config = configparser.ConfigParser(interpolation=None, strict=True)
        config.read_string(original)
        settings = config['waydroid']
        if (settings['arch'] != 'x86_64' or settings['vendor_type'] != 'MAINLINE'
                or Path(settings['images_path']) != images
                or int(settings['vendor_datetime']) != 0
                or int(settings['system_datetime']) <= 0
                or settings['vendor_ota'] != VENDOR_OTA):
            raise ValueError('Unexpected Waydroid configuration.')
        system_ota = settings['system_ota']
        flavor = next((name for name in ('GAPPS', 'VANILLA')
                       if system_ota == SYSTEM_OTA + name + '.json'), None)
        if not flavor or not (images / 'system.img').is_file() or (images / 'system.img').stat().st_size == 0:
            raise ValueError('Missing system image or unsupported system OTA.')
    except (OSError, KeyError, configparser.Error, ValueError) as exc:
        raise ValueError(f'Invalid or incomplete Waydroid configuration: {exc}') from exc

    with urllib.request.urlopen(VENDOR_OTA, timeout=20) as response:
        metadata = json.load(response)
    with urllib.request.urlopen(system_ota, timeout=20) as response:
        system_metadata = json.load(response)
    try:
        system_latest = max(entry['datetime'] for entry in system_metadata['response'])
        vendor_latest = max(entry['datetime'] for entry in metadata['response'])
        if not isinstance(system_latest, int) or not isinstance(vendor_latest, int):
            raise ValueError('Invalid OTA timestamps.')
        if system_latest > int(settings['system_datetime']):
            raise ValueError('A newer system image is available; refusing to redownload it.')
    except (KeyError, TypeError) as exc:
        raise ValueError('Invalid official OTA metadata.') from exc
    with open(archive, 'rb') as source:
        size = os.fstat(source.fileno()).st_size
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
        matches = [entry for entry in metadata['response']
                   if entry.get('version') == '20.0' and entry.get('id') == digest
                   and entry.get('size') == size and isinstance(entry.get('datetime'), int)
                   and entry['datetime'] > 0]
        if len(matches) != 1 or matches[0]['datetime'] != vendor_latest:
            raise ValueError('Archive does not match the official vendor OTA metadata.')
        source.seek(0)
        temp_name = None
        try:
            with zipfile.ZipFile(source) as archive_zip:
                entries = [item for item in archive_zip.infolist() if item.filename == 'vendor.img']
                if len(entries) != 1 or entries[0].is_dir() or entries[0].file_size == 0:
                    raise ValueError('Archive must contain one nonempty vendor.img.')
                with tempfile.NamedTemporaryFile(dir=images, prefix='.vendor-', delete=False) as temp:
                    temp_name = temp.name
                    os.fchmod(temp.fileno(), 0o644)
                    with archive_zip.open(entries[0]) as vendor:
                        shutil.copyfileobj(vendor, temp)
                    temp.flush()
                    os.fsync(temp.fileno())
            if init_running() or cfg.read_text() != original or (work / 'rootfs').exists():
                raise RuntimeError('Waydroid state changed during validation; stop initialization before retrying.')
            os.link(temp_name, images / 'vendor.img')
        finally:
            if temp_name:
                os.unlink(temp_name)

    # Modify only the original vendor_datetime line, preserving the remaining configuration.
    lines = original.splitlines(keepends=True)
    section = None
    changed = 0
    for index, line in enumerate(lines):
        match = re.match(r'^\s*\[([^]]+)\]', line)
        if match:
            section = match.group(1)
        if section == 'waydroid' and re.match(r'^\s*vendor_datetime\s*[:=]', line, re.IGNORECASE):
            lines[index] = re.sub(r'([:=]\s*)[^\r\n]*', lambda m: m.group(1) + str(matches[0]['datetime']), line, count=1)
            changed += 1
    if changed != 1:
        raise ValueError('Cannot safely update vendor_datetime; vendor image was retained.')
    with tempfile.NamedTemporaryFile(dir=work, prefix='waydroid.cfg.backup.', delete=False) as backup:
        backup.write(original.encode())
        backup.flush()
        os.fsync(backup.fileno())
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=work, prefix='.waydroid.cfg-', delete=False) as temp:
            temp_name = temp.name
            os.fchmod(temp.fileno(), cfg.stat().st_mode & 0o7777)
            temp.writelines(lines)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, cfg)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
    command = ['waydroid', 'init', '-s', flavor]
    try:
        subprocess.run(command, check=True)
        if not (work / 'rootfs').is_dir():
            raise RuntimeError('Waydroid returned without creating its rootfs; initialization is incomplete.')
    except (subprocess.CalledProcessError, OSError, RuntimeError):
        print('Waydroid initialization failed. Retry: sudo ' + ' '.join(command), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('vendor_zip', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run this command with sudo.')
    try:
        finish(Path('/var/lib/waydroid'), args.vendor_zip)
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
