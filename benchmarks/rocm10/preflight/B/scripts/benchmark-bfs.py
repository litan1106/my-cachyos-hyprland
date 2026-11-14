#!/usr/bin/env python3
"""Run fixed-input BFS comparisons in owned, fresh ComfyUI processes."""
import argparse
import asyncio
import contextlib
import copy
import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8189'


def load_smoke():
    spec = importlib.util.spec_from_file_location('bfs_smoke_benchmark', ROOT / 'scripts/smoke-bfs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = load_smoke()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def checked_input(spec, override):
    path = Path(override) if override is not None else ROOT / spec['path']
    actual = smoke.digest(path)
    matches = actual == spec['sha256']
    if override is None and not matches:
        raise ValueError(f'Frozen input hash differs: {path}; use --video/--reference explicitly for a different input')
    return {'path': str(path.resolve()), 'sha256': actual, 'matches_frozen_input': matches}


def check_required_models(config, names, root=ROOT):
    required = {config['cases'][name].get('requires_model') for name in names} - {None}
    if not required:
        return []
    spec = importlib.util.spec_from_file_location('bfs_benchmark_model_verification', ROOT / 'scripts/download-models.py')
    downloader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(downloader)
    models = {model['id']: model for model in json.loads((root / 'models.json').read_text())['models']}
    errors = []
    for model_id in sorted(required):
        try:
            if model_id not in models:
                raise ValueError(f'{model_id}: absent from pinned model manifest')
            downloader.verify(models[model_id], root)
        except (downloader.IntegrityError, OSError, ValueError) as exc:
            errors.append({'model': model_id, 'error': str(exc),
                           'download_command': f'.venv/bin/python scripts/download-models.py --model {model_id}',
                           'verify_command': f'.venv/bin/python scripts/download-models.py --verify --model {model_id}'})
    return errors


def prepare_graph(template, case):
    graph = copy.deepcopy(template)
    smoke.bind(graph, 'VHS_LoadVideo', 'frame_load_cap', 33, None)
    smoke.bind(graph, 'VHS_LoadVideo', 'force_rate', 24.0, None)
    smoke.bind(graph, 'CreateVideo', 'fps', 24.0, None)
    if case == 'native-fp8':
        graph['478']['class_type'] = 'UNETLoader'
        graph['478']['inputs'] = {'unet_name': 'ltx-2.3-22b-distilled_transformer_only_fp8_scaled.safetensors',
                                  'weight_dtype': 'default'}
    if case == 'compile':
        matches = [n for n in graph.values() if n.get('class_type') == 'CFGGuider']
        if len(matches) != 1:
            raise ValueError('Compilation requires exactly one CFGGuider')
        guider = matches[0]
        graph['bfs_bench_compile'] = {'class_type': 'TorchCompileModel', 'inputs': {
            'model': guider['inputs']['model'], 'backend': 'inductor'}}
        guider['inputs']['model'] = ['bfs_bench_compile', 0]
    return graph


def summarize_execution(events, prompt_id, history, graph):
    selected = [e for e in events if prompt_id and e.get('data', {}).get('prompt_id') == prompt_id]
    cached = set()
    for message in (history or {}).get('status', {}).get('messages', []):
        if len(message) > 1 and message[0] == 'execution_cached':
            cached.update(str(n) for n in message[1].get('nodes', []))
    for event in selected:
        if event['type'] == 'execution_cached':
            cached.update(str(n) for n in event['data'].get('nodes', []))
    nodes = {}
    current = None
    started = None
    for event in selected:
        if event['type'] != 'executing':
            continue
        now = event['elapsed_seconds']
        if current is not None:
            row = nodes.setdefault(current, {'class_type': graph.get(current, {}).get('class_type'), 'seconds': 0})
            row['seconds'] += max(0, now - started)
        current = event['data'].get('node')
        current = str(current) if current is not None else None
        started = now
    samplers = {i for i, n in graph.items() if n.get('class_type') == 'SamplerCustomAdvanced'} or {'382'}
    return {'method': 'client-observed WebSocket node boundaries; asynchronous GPU work is not separately timed',
            'events': selected, 'node_wall_seconds': nodes, 'cached_nodes': sorted(cached),
            'sampler_cached': bool(samplers & cached), 'sampling_observed': bool(samplers & nodes.keys()),
            'gpu_kernel_seconds': None}


class EventMonitor:
    def __init__(self, client_id):
        self.client_id = client_id
        self.events = []
        self.error = None
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            asyncio.run(self.listen())
        except Exception as exc:
            self.error = str(exc)
            self.ready.set()

    async def listen(self):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(URL.replace('http:', 'ws:') + '/ws?clientId=' + self.client_id) as ws:
                start = time.monotonic()
                self.ready.set()
                while not self.stop.is_set():
                    try:
                        message = await ws.receive(timeout=0.25)
                    except asyncio.TimeoutError:
                        continue
                    if message.type == aiohttp.WSMsgType.TEXT:
                        value = json.loads(message.data)
                        if value.get('type') in {'executing', 'execution_start', 'execution_cached', 'execution_success', 'execution_error', 'progress', 'progress_state'}:
                            self.events.append({'elapsed_seconds': time.monotonic() - start, **value})
                    elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                        break

    def __enter__(self):
        self.thread.start()
        if not self.ready.wait(10):
            self.error = 'WebSocket connection timed out'
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=3)


def port_busy():
    with socket.socket() as sock:
        return sock.connect_ex(('127.0.0.1', 8189)) == 0


def rocm_prefix():
    return Path(os.environ.get('ROCM_PATH') or Path.home() / '.local/opt/rocm-10.0.0-gfx120X-all')


def server_command(profile, trace_dir=None, session='fresh'):
    command = [str(ROOT / 'run-bfs.sh'), '--profile', profile]
    if trace_dir is not None:
        command = [str(rocm_prefix() / 'bin/rocprofv3'), '--kernel-trace', '--hip-runtime-trace', '--memory-copy-trace',
                   '--summary', '--output-format', 'pftrace', '--output-directory', str(trace_dir), '--', *command]
    return command


def start_server(profile, logfile, timeout, trace_dir=None, session='fresh'):
    if port_busy():
        raise RuntimeError('Port 8189 is occupied. Stop your project server or explicitly use --external-server --pid PID; no process was changed.')
    process = subprocess.Popen(server_command(profile, trace_dir, session), cwd=ROOT, stdout=logfile, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'Server exited with status {process.returncode}; inspect server.log')
            try:
                json.loads(smoke.request(URL + '/system_stats'))
                return process
            except (OSError, ValueError):
                time.sleep(0.5)
        raise RuntimeError('Server startup timed out; inspect server.log')
    except BaseException:
        finish_server(process, {'status': 'startup_error'})
        raise


def safe_to_stop(record):
    history_status = record.get('history', {}).get('status', {}) if record.get('history') else {}
    terminal = (history_status.get('completed') or history_status.get('status_str') in {'success', 'error'}
                or any(m and m[0] == 'execution_error' for m in history_status.get('messages', [])))
    if (record.get('status') in {'timeout', 'interrupted'} or record.get('stage') == 'submit'
            or (record.get('prompt_id') and not terminal and record.get('status') != 'success')):
        return False
    return True


def finish_server(process, record):
    if process is None or process.poll() is not None:
        return True
    if not safe_to_stop(record):
        return False
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return True


def execute_smoke(graph_path, inputs, run_id, pid, case, timeout, interval, launch_settings, baseline_id, logfile):
    client_id = uuid.uuid4().hex
    original_request = smoke.request
    original_argv = sys.argv

    def request(url, data=None, content_type=None):
        if url == URL + '/prompt' and data:
            payload = json.loads(data)
            payload['client_id'] = client_id
            data = json.dumps(payload).encode()
        return original_request(url, data, content_type)

    args = ['smoke-bfs', '--video', inputs['video']['path'], '--reference', inputs['reference']['path'],
            '--workflow', str(graph_path), '--run-id', run_id, '--candidate', case, '--timeout', str(timeout),
            '--interval', str(interval), '--launch-settings', launch_settings, '--source-range', 'prepared 33-frame shot; frames 0-32 at 24 FPS']
    if pid:
        args += ['--pid', str(pid)]
    if baseline_id:
        args += ['--baseline-run-id', baseline_id]
    with EventMonitor(client_id) as monitor:
        try:
            smoke.request = request
            sys.argv = args
            with contextlib.redirect_stdout(logfile), contextlib.redirect_stderr(logfile):
                smoke.main()
        finally:
            smoke.request = original_request
            sys.argv = original_argv
    result = json.loads((ROOT / 'benchmarks/runs' / run_id / 'result.json').read_text())
    timeline = summarize_execution(monitor.events, result.get('prompt_id'), result.get('history'), json.loads(graph_path.read_text()))
    timeline['connection_error'] = monitor.error
    return result, timeline


def prepare_run_inputs(inputs, run_id, directory, session):
    run_inputs = copy.deepcopy(inputs)
    if session != 'warm':
        return run_inputs
    source = Path(inputs['video']['path'])
    target = directory / ('video-' + run_id + source.suffix)
    with source.open('rb') as original, target.open('xb') as copied:
        shutil.copyfileobj(original, copied)
    actual_hash = smoke.digest(target)
    if actual_hash != inputs['video']['sha256']:
        raise ValueError('Warm-session video copy hash differs from recorded source hash')
    run_inputs['video'].update(path=str(target.resolve()), sha256=actual_hash)
    return run_inputs


def run_case(case_name, case, repeat, args, directory, inputs, template, baseline_id, shared_process=None, defer_cleanup=False):
    run_id = f'{directory.name}-{case_name}-{repeat}'
    case_dir = directory / f'{case_name}-{repeat}'
    case_dir.mkdir()
    graph = prepare_graph(template, case_name)
    graph_path = case_dir / 'workflow-api.json'
    save(graph_path, graph)
    session = getattr(args, 'session', 'fresh')
    row = {'case': case_name, 'repeat': repeat, 'run_id': run_id, 'status': 'error', 'profile': case['profile'], 'session': session,
           'cache_condition': 'external process; prior cache unknown' if args.external_server else 'fresh server process; OS disk cache uncontrolled',
           'diagnostic_trace': args.trace, 'eligible_for_performance_comparison': False,
           'server_log': str(case_dir / 'server.log'), 'graph_sha256': smoke.digest(graph_path), 'original_inputs': inputs}
    if session == 'warm':
        row['cache_condition'] = 'same owned server process; selected profile node-cache policy retained; byte-identical video uploaded with a unique filename each run to recompute video-dependent nodes; cached sampler results excluded; model/text cache reuse must be observed in timeline and server log; OS disk cache uncontrolled'
        row['server_log'] = str(directory / (case_name + '-session-server.log'))
        row['warmup'] = repeat == 1
    process = None
    record = {}
    try:
        run_inputs = prepare_run_inputs(inputs, run_id, case_dir, session)
        row['submitted_inputs'] = run_inputs
        with (case_dir / 'server.log').open('w') as server_log:
            server_start = time.monotonic()
            process = shared_process if shared_process is not None else (None if args.external_server else start_server(case['profile'], server_log, args.startup_timeout, case_dir / 'trace' if args.trace else None))
            row['server_startup_seconds'] = None if args.external_server or shared_process is not None else time.monotonic() - server_start
            pid = args.pid if args.external_server else process.pid
            row['server_pid'] = pid
            row['launch_configuration'] = 'observed external process; requested profile was not applied' if args.external_server else 'owned launch with selected profile'
            try:
                row['observed_server_command'] = (Path('/proc') / str(pid) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0') if pid else None
            except OSError:
                row['observed_server_command'] = None
            stats = json.loads(smoke.request(URL + '/system_stats'))
            schemas = json.loads(smoke.request(URL + '/object_info'))
            save(case_dir / 'system_stats.json', stats)
            queue = json.loads(smoke.request(URL + '/queue'))
            if queue.get('queue_running') or queue.get('queue_pending'):
                raise RuntimeError('Server queue is not empty; benchmark will not submit alongside other jobs')
            missing = sorted({n['class_type'] for n in graph.values()} - schemas.keys())
            if missing:
                raise RuntimeError('Active graph classes not registered: ' + ', '.join(missing))
            with (case_dir / 'runner.log').open('w') as runner_log:
                record, timeline = execute_smoke(graph_path, run_inputs, run_id, pid, case_name, args.timeout, args.interval,
                                                 json.dumps({'requested_command': server_command(case['profile'], session=session), 'observed_command': row['observed_server_command'], 'external': args.external_server, 'trace': args.trace, 'session': session}), baseline_id, runner_log)
            save(case_dir / 'timeline.json', timeline)
            row.update({'status': record['status'], 'prompt_id': record.get('prompt_id'), 'wall_seconds': record['wall_seconds'],
                        'result': str(ROOT / 'benchmarks/runs' / run_id / 'result.json'), 'timeline': str(case_dir / 'timeline.json'),
                        'sampling': {k: v for k, v in record.get('sampling', {}).items() if k != 'samples'},
                        'sampler_cached': timeline['sampler_cached'], 'sampling_observed': timeline['sampling_observed']})
            if record['status'] != 'success':
                row['error'] = record.get('error', 'Run did not complete')
            elif timeline['sampler_cached']:
                row['status'] = 'cached_output'
                row['error'] = 'Sampler was cached; this is not an inference benchmark'
            else:
                with (case_dir / 'review.log').open('w') as review_log:
                    review = subprocess.run([sys.executable, str(ROOT / 'scripts/review-video.py'), '--run-id', run_id],
                                            cwd=ROOT, stdout=review_log, stderr=subprocess.STDOUT)
                row['artifact_checks'] = 'passed' if review.returncode == 0 else 'failed'
                row['visual_quality'] = 'pending frame and temporal review; no quality preset selected'
                if review.returncode:
                    row['status'] = 'artifact_error'
                row['eligible_for_performance_comparison'] = bool(not args.trace and not args.external_server and timeline['sampling_observed'] and review.returncode == 0 and not row.get('warmup'))
    except KeyboardInterrupt:
        row.update(status='interrupted', error='Observation interrupted; retain prompt/server evidence before continuing')
        record['status'] = 'interrupted'
    except Exception as exc:
        row['error'] = str(exc)
        result_path = ROOT / 'benchmarks/runs' / run_id / 'result.json'
        if result_path.exists():
            record = json.loads(result_path.read_text())
    finally:
        row['safe_to_stop_owned_server'] = safe_to_stop(record)
        stopped = False if defer_cleanup and process and row['safe_to_stop_owned_server'] else finish_server(process, record)
        row['owned_server_stopped'] = stopped if process else None
        if not stopped and not (defer_cleanup and row['safe_to_stop_owned_server']):
            row['retained_server_pid'] = process.pid
            row['warning'] = 'Server may still own an active or ambiguously submitted job; it was left running. Inspect queue/history before stopping it.'
        save(case_dir / 'summary.json', row)
    return row


def run_repeats(case_name, case, args, directory, inputs, template, baseline_id, on_row=None):
    rows = []
    process = None
    session_log = None
    interrupted = False
    try:
        if args.session == 'warm':
            session_log = (directory / (case_name + '-session-server.log')).open('w')
            process = start_server(case['profile'], session_log, args.startup_timeout, session='warm')
        for repeat in range(1, args.repeats + 1):
            print(f'Running {case_name} {repeat}/{args.repeats}; evidence: {directory}', flush=True)
            row = run_case(case_name, case, repeat, args, directory, inputs, template, baseline_id,
                           shared_process=process, defer_cleanup=args.session == 'warm')
            if args.session == 'warm':
                row['warmup'] = repeat == 1
                if row['warmup']:
                    row['eligible_for_performance_comparison'] = False
                summary_path = directory / f'{case_name}-{repeat}' / 'summary.json'
                if summary_path.parent.exists():
                    save(summary_path, row)
            rows.append(row)
            if case_name == 'baseline' and row['status'] == 'success' and baseline_id is None:
                baseline_id = row['run_id']
            if on_row:
                on_row(row)
            if (row['status'] == 'interrupted' or row.get('retained_server_pid')
                    or (args.session == 'warm' and row['status'] != 'success')):
                break
    except BaseException:
        interrupted = True
        raise
    finally:
        if process is not None:
            safe = not interrupted and (not rows or rows[-1].get('safe_to_stop_owned_server', False))
            stopped = finish_server(process, {'status': 'success' if safe else 'interrupted'})
            if rows:
                rows[-1]['owned_server_stopped'] = stopped
                if not stopped:
                    rows[-1]['retained_server_pid'] = process.pid
                    rows[-1]['warning'] = 'Warm session stopped observation with an unresolved job; owned server was left running.'
                path = directory / f'{case_name}-{rows[-1]["repeat"]}' / 'summary.json'
                if path.parent.exists():
                    save(path, rows[-1])
            elif not stopped:
                save(directory / 'retained-server.json', {'pid': process.pid, 'reason': 'Warm session interrupted before a terminal result was recorded'})
        if session_log:
            session_log.close()
    return rows


def main(argv=None):
    rocm_path = str(rocm_prefix())
    os.environ['ROCM_PATH'] = rocm_path
    os.environ['HIP_PATH'] = rocm_path
    os.environ['PATH'] = str(Path(rocm_path) / 'bin') + os.pathsep + os.environ.get('PATH', '')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['baseline', 'memory', 'kernels', 'formats'], default='baseline')
    parser.add_argument('--case', action='append', help='Select a case within the suite; repeat to select several')
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--session', choices=['fresh', 'warm'], default='fresh', help='Fresh process per run, or one process with unique byte-identical video uploads and first run excluded as warmup')
    parser.add_argument('--config', type=Path, default=ROOT / 'benchmarks/optimization/config.json')
    parser.add_argument('--video', type=Path)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--run-id-prefix')
    parser.add_argument('--baseline-run-id', help='Explicit comparison parent when executing a candidate separately')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--external-server', action='store_true', help='Explicitly attach to an idle existing server; cannot establish fresh-process comparisons')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('--startup-timeout', type=float, default=120)
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--trace', action='store_true', help='Run owned server through rocprofv3; diagnostic overhead excludes timings from comparisons')
    args = parser.parse_args(argv)
    if args.repeats < 1 or min(args.timeout, args.startup_timeout, args.interval) <= 0:
        parser.error('repeats and timing arguments must be positive')
    if args.pid is not None and (args.pid <= 0 or not args.external_server):
        parser.error('--pid requires --external-server and must be positive')
    if args.external_server and args.trace:
        parser.error('--trace requires an owned server')
    if args.external_server and args.repeats != 1:
        parser.error('--external-server supports one observed run per invocation')
    if args.session == 'warm' and (args.external_server or args.trace):
        parser.error('--session warm requires an owned server without --trace')
    prefix = args.run_id_prefix or dt.datetime.now(dt.timezone.utc).strftime('opt-%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    if not re.fullmatch(r'[A-Za-z0-9_-]+', prefix):
        parser.error('--run-id-prefix must contain only letters, digits, underscores and hyphens')
    try:
        config = json.loads(args.config.read_text())
        names = args.case or config['suites'][args.suite]
        if len(names) != len(set(names)):
            parser.error('duplicate --case values are not supported; use --repeats')
        if not names:
            print(json.dumps({'status': 'blocked', 'suite': args.suite, 'reason': config['blocked_suites'][args.suite]}))
            return 2
        if any(name not in config['suites'][args.suite] for name in names):
            parser.error('--case must belong to the selected suite')
        if args.session == 'warm' and len(names) != 1:
            parser.error('--session warm requires exactly one --case')
        model_errors = check_required_models(config, names)
        if model_errors:
            print(json.dumps({'status': 'blocked', 'suite': args.suite, 'reason': 'Required candidate model is missing or fails integrity verification; no server was started and no model was downloaded.', 'models': model_errors}, indent=2))
            return 2
        inputs = {key: checked_input(config['inputs'][key], getattr(args, key)) for key in ('video', 'reference')}
        workflow_path = ROOT / config['workflow']['path']
        if smoke.digest(workflow_path) != config['workflow']['sha256']:
            raise ValueError('Frozen workflow hash differs; inspect and update benchmark config deliberately')
        upstream_path = ROOT / config['upstream']['path']
        if smoke.digest(upstream_path) != config['upstream']['sha256']:
            raise ValueError('Pinned upstream workflow hash differs')
        template = json.loads(workflow_path.read_text())
        if args.trace and (len(names) != 1 or args.repeats != 1):
            parser.error('--trace requires one --case and --repeats 1')
        profiler = rocm_prefix() / 'bin/rocprofv3'
        if args.trace and not profiler.is_file():
            raise ValueError(f'rocprofv3 is unavailable at {profiler}')
        plan = {'suite': args.suite, 'cases': names, 'repeats': args.repeats, 'inputs': inputs,
                'workflow': config['workflow'], 'benchmark_frames': 33, 'fps': 24,
                'trace': args.trace, 'session': args.session,
                'warmup_runs_excluded': 1 if args.session == 'warm' else 0,
                'commands': {name: server_command(config['cases'][name]['profile'], Path('TRACE_DIRECTORY') if args.trace else None, args.session) for name in names}}
        if args.dry_run:
            print(json.dumps({'status': 'dry_run', **plan}, indent=2))
            return 0
        if port_busy() and not args.external_server:
            raise RuntimeError('Port 8189 is occupied; no server was started or changed. Stop the project server or use --external-server explicitly.')
        if args.external_server and not port_busy():
            raise RuntimeError('--external-server requires a running server on 127.0.0.1:8189')
        if args.external_server and len(names) != 1:
            raise ValueError('--external-server requires exactly one --case; its active launch settings are not changed')
        directory = ROOT / 'benchmarks/optimization' / prefix
        directory.mkdir(exist_ok=False)
        save(directory / 'plan.json', plan)
        shutil.copy2(args.config, directory / 'config.json')
        for name in ['uv.lock', 'versions.json', 'models.json', 'config/runtime-profiles.json']:
            source = ROOT / name
            if source.is_file():
                destination = directory / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        report = {'suite': args.suite, 'run_id_prefix': prefix, 'runs': [], 'status': 'running',
                  'comparison_scope': config.get('comparison_scope', '33 frames, fixed seed/prompt and 640x320 composition; public sample quality remains unaccepted'),
                  'inputs': inputs, 'diagnostic_trace': args.trace, 'session': args.session,
                  'warmup_runs_excluded': 1 if args.session == 'warm' else 0}
        save(directory / 'report.json', report)
        baseline_id = args.baseline_run_id
        with (ROOT / 'benchmarks/optimization/.benchmark.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            for name in names:
                def on_row(row):
                    report['runs'].append(row)
                    save(directory / 'report.json', report)
                    print(json.dumps({key: row.get(key) for key in ['case', 'run_id', 'status', 'wall_seconds', 'error', 'retained_server_pid']}), flush=True)
                try:
                    rows = run_repeats(name, config['cases'][name], args, directory, inputs, template, baseline_id, on_row)
                except BaseException as exc:
                    report.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'error', error=str(exc))
                    retained = directory / 'retained-server.json'
                    if retained.exists():
                        report['retained_server'] = json.loads(retained.read_text())
                    save(directory / 'report.json', report)
                    raise
                if name == 'baseline' and baseline_id is None:
                    baseline_id = next((row['run_id'] for row in rows if row['status'] == 'success'), None)
                if report['runs'][-1]['status'] == 'interrupted' or report['runs'][-1].get('retained_server_pid'):
                    break
        report['medians_seconds'] = {name: statistics.median(values) for name in names
                                     if (values := [r['wall_seconds'] for r in report['runs'] if r['case'] == name and r['eligible_for_performance_comparison']])}
        report['status'] = 'success' if all(r['status'] == 'success' for r in report['runs']) else 'incomplete'
        save(directory / 'report.json', report)
        print(json.dumps({'status': report['status'], 'report': str(directory / 'report.json'), 'medians_seconds': report['medians_seconds']}))
        return 0 if report['status'] == 'success' else 1
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'Benchmark failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
