#!/usr/bin/env python3
"""Capture isolated llama.cpp ROCm benchmark runs and their host context."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import subprocess
import threading
import time
import urllib.request

HERE = Path(__file__).resolve().parent
BIN = Path('/home/litan/Projects/llama_cpp/build-rocm10/bin')
SDK = Path('/home/litan/.local/opt/rocm-10.0.0-gfx120X-all')
MODEL = Path('/home/litan/.cache/huggingface/hub/models--deepreinforce-ai--Ornith-1.0-9B-GGUF/snapshots/3296bc7a404871a72ac3f1903f561459c09b5c17/ornith-1.0-9b-Q8_0.gguf')
SHA = 'd0e4bebaa8b3450c62090df1408f2ee5ccb2094f9c610ffde564a654483d4f37'
ENV = os.environ.copy()
ENV.update(ROCM_PATH=str(SDK), HIP_PATH=str(SDK), HIP_VISIBLE_DEVICES='0', PATH=f'{SDK}/bin:{SDK}/llvm/bin:' + ENV.get('PATH', ''))
ENV.pop('HSA_OVERRIDE_GFX_VERSION', None)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def snapshot():
    result = {'utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    for name in ['/proc/loadavg', '/proc/meminfo', '/proc/stat', '/proc/pressure/cpu', '/proc/pressure/memory', '/proc/pressure/io']:
        try:
            result[name] = Path(name).read_text()
        except OSError:
            pass
    for name in Path('/sys/class/drm').glob('card*/device/mem_info_*'):
        try:
            result[str(name)] = name.read_text().strip()
        except OSError:
            pass
    for name in Path('/sys/class/drm').glob('card*/device/gpu_busy_percent'):
        try:
            result[str(name)] = name.read_text().strip()
        except OSError:
            pass
    return result


def sample(stop, path, pid):
    with path.open('w') as f:
        while not stop.is_set():
            data = snapshot()
            try:
                status = Path(f'/proc/{pid}/status').read_text().splitlines()
                data['process_memory'] = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in status if line.startswith(('VmRSS:', 'VmSwap:'))}
            except OSError:
                data['process_memory'] = None
            f.write(json.dumps(data) + '\n')
            f.flush()
            stop.wait(2)


def capture_setup(out):
    records = {}
    for name in ['llama-bench', 'llama-completion', 'llama-server']:
        binary = BIN / name
        records[name] = {'path': str(binary), 'sha256': sha256(binary)}
        for kind, cmd in [('help', [str(binary), '--help']), ('ldd', ['ldd', str(binary)])]:
            result = subprocess.run(cmd, env=ENV, capture_output=True, timeout=60)
            (out / f'{name}-{kind}.stdout').write_bytes(result.stdout)
            (out / f'{name}-{kind}.stderr').write_bytes(result.stderr)
            records[name][kind + '_exit'] = result.returncode
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', choices=['baseline', 'translation', 'flash', 'microbatch', 'kv', 'completion', 'server'])
    parser.add_argument('--timeout', type=int, default=7200)
    args = parser.parse_args()
    if MODEL.stat().st_size != 9527500992:
        raise SystemExit('Unexpected model size')
    if args.timeout <= 0:
        raise SystemExit('Timeout must be positive')
    if args.case == 'server':
        with socket.socket() as sock:
            if sock.connect_ex(('127.0.0.1', 8190)) == 0:
                raise SystemExit('127.0.0.1:8190 is occupied')
    run_id = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + args.case
    out = HERE / run_id
    out.mkdir(exist_ok=False)
    binaries = capture_setup(out)
    model_hash = sha256(MODEL)
    if model_hash != SHA:
        raise SystemExit(f'Model hash mismatch: {model_hash}; evidence at {out}')
    base = [str(BIN / 'llama-bench'), '-m', str(MODEL), '-r', '3', '-ngl', '999', '-o', 'json']
    shaped = ['-p', '2048', '-n', '0', '-pg', '2048,1024']
    commands = {
        'baseline': base + ['-p', '128', '-n', '32'],
        'translation': base + shaped,
        'flash': base + shaped + ['-fa', 'off,on,auto'],
        'microbatch': base + shaped + ['-b', '2048', '-ub', '256,512,1024,2048'],
        'kv': base + shaped + ['-fa', 'on', '-ctk', 'f16,q8_0', '-ctv', 'f16,q8_0'],
        'completion': [str(BIN / 'llama-completion'), '-m', str(MODEL), '-ngl', '999', '-no-cnv', '-p', 'The capital of France is', '--seed', '42', '--temp', '0', '-n', '32'],
        'server': [str(BIN / 'llama-server'), '-m', str(MODEL), '-ngl', '999', '--host', '127.0.0.1', '--port', '8190', '-np', '1', '-c', '4096'],
    }
    command = commands[args.case]
    metadata = {'run_id': run_id, 'command': command, 'cwd': str(HERE), 'environment': {k: ENV.get(k) for k in ['ROCM_PATH', 'HIP_PATH', 'HIP_VISIBLE_DEVICES', 'HSA_OVERRIDE_GFX_VERSION', 'PATH', 'LD_LIBRARY_PATH']}, 'sdk_version': (SDK / '.info/version').read_text().strip(), 'model': str(MODEL), 'model_sha256': model_hash, 'binaries': binaries, 'source_revision': subprocess.check_output(['git', '-C', '/home/litan/Projects/llama_cpp', 'rev-parse', 'HEAD'], text=True).strip(), 'source_status': subprocess.check_output(['git', '-C', '/home/litan/Projects/llama_cpp', 'status', '--porcelain'], text=True), 'sampling_interval_seconds': 2, 'cache_definition': 'OS and model caches uncontrolled; process starts fresh', 'benchmark_warmup': 'normal default; --no-warmup not passed', 'timeout_seconds': args.timeout}
    metadata['status'] = 'prepared'
    (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (out / 'before.json').write_text(json.dumps(snapshot(), indent=2) + '\n')
    (out / 'before-ps.txt').write_text(subprocess.check_output(['ps', 'aux'], text=True))
    stop = threading.Event()
    sampler = None
    start = time.monotonic()
    try:
        with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
            proc = subprocess.Popen(command, cwd=HERE, env=ENV, stdout=stdout, stderr=stderr)
            metadata.update(status='running', pid=proc.pid)
            (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
            sampler = threading.Thread(target=sample, args=(stop, out / 'samples.jsonl', proc.pid))
            sampler.start()
            try:
                if args.case == 'server':
                    deadline = start + args.timeout
                    while time.monotonic() < deadline and proc.poll() is None:
                        try:
                            with urllib.request.urlopen('http://127.0.0.1:8190/health', timeout=2) as response:
                                body = response.read()
                                if response.status == 200:
                                    (out / 'health.json').write_bytes(body)
                                    metadata['health_ready_seconds'] = time.monotonic() - start
                                    break
                        except Exception:
                            time.sleep(1)
                    metadata['health_passed'] = 'health_ready_seconds' in metadata
                    if metadata['health_passed']:
                        request = urllib.request.Request('http://127.0.0.1:8190/completion', data=json.dumps({'prompt': 'The capital of France is', 'n_predict': 32, 'seed': 42, 'temperature': 0}).encode(), headers={'Content-Type': 'application/json'})
                        try:
                            with urllib.request.urlopen(request, timeout=max(1, deadline - time.monotonic())) as response:
                                body = response.read()
                                (out / 'server-completion.json').write_bytes(body)
                                metadata['completion_http_status'] = response.status
                                result = json.loads(body)
                                metadata['completion_valid'] = isinstance(result.get('content'), str) and 'paris' in result['content'].lower()
                        except Exception as exc:
                            metadata['completion_error'] = str(exc)
                    if proc.poll() is None:
                        proc.terminate()
                proc.wait(timeout=max(1, args.timeout - (time.monotonic() - start)))
            except subprocess.TimeoutExpired:
                metadata['timed_out'] = True
                proc.kill()
                proc.wait()
            metadata['exit_code'] = proc.returncode
    finally:
        metadata['wall_seconds'] = time.monotonic() - start
        stop.set()
        if sampler is not None:
            sampler.join()
        (out / 'after-ps.txt').write_text(subprocess.check_output(['ps', 'aux'], text=True))
        (out / 'after.json').write_text(json.dumps(snapshot(), indent=2) + '\n')
        (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if args.case in ('baseline', 'translation', 'flash', 'microbatch', 'kv'):
        expected = {'baseline': 2, 'translation': 2, 'flash': 6, 'microbatch': 8, 'kv': 8}[args.case]
        try:
            rows = json.loads((out / 'stdout.log').read_text())
            metadata['benchmark_rows'] = len(rows) if isinstance(rows, list) else None
            metadata['benchmark_valid'] = isinstance(rows, list) and len(rows) == expected
        except (OSError, ValueError):
            metadata['benchmark_valid'] = False
        success = metadata.get('exit_code') == 0 and metadata['benchmark_valid']
    elif args.case == 'server':
        success = metadata.get('health_passed', False) and metadata.get('completion_http_status') == 200 and metadata.get('completion_valid', False) and not metadata.get('timed_out', False)
    else:
        success = metadata.get('exit_code') == 0 and not metadata.get('timed_out', False)
    metadata['status'] = 'passed' if success else 'failed'
    (out / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(out)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
