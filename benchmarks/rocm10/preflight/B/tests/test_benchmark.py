import importlib.util
import io
import json
import os
from pathlib import Path
import signal
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location('benchmark', ROOT / 'scripts/benchmark-bfs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_copy_caps_frames_without_changing_template(self):
        benchmark = load()
        source = json.loads((ROOT / 'workflows/bfs-v3-sintel-baseline-api.json').read_text())
        original = json.loads(json.dumps(source))
        result = benchmark.prepare_graph(source, 'baseline')
        self.assertEqual(source, original)
        self.assertEqual(result['345']['inputs']['frame_load_cap'], 33)
        self.assertEqual(result['345']['inputs']['force_rate'], 24)
        self.assertEqual(result['573']['inputs']['strength_model'], 1)
        self.assertEqual(result['575'], original['575'])
        self.assertEqual(result['408']['inputs']['audio'], original['408']['inputs']['audio'])

    def test_compile_changes_only_sampler_model_path(self):
        benchmark = load()
        source = json.loads((ROOT / 'workflows/bfs-v3-sintel-baseline-api.json').read_text())
        result = benchmark.prepare_graph(source, 'compile')
        self.assertEqual(result['396']['inputs']['model'], ['bfs_bench_compile', 0])
        self.assertEqual(result['bfs_bench_compile']['inputs']['model'], ['573', 0])
        self.assertNotIn('bfs_bench_compile', source)

    def test_native_fp8_changes_only_loader_and_benchmark_frame_cap(self):
        benchmark = load()
        source = json.loads((ROOT / 'workflows/bfs-v3-sintel-baseline-api.json').read_text())
        result = benchmark.prepare_graph(source, 'native-fp8')
        self.assertEqual(result['478']['class_type'], 'UNETLoader')
        self.assertEqual(result['478']['inputs'], {'unet_name': 'ltx-2.3-22b-distilled_transformer_only_fp8_scaled.safetensors', 'weight_dtype': 'default'})
        for node_id in source.keys() - {'345', '478'}:
            self.assertEqual(result[node_id], source[node_id])
        self.assertEqual(source['478']['class_type'], 'UnetLoaderGGUF')

    def test_missing_and_corrupt_optional_model_block_before_server_start(self):
        benchmark = load()
        config = {'cases': {'native-fp8': {'requires_model': 'transformer_fp8'}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = {'id': 'transformer_fp8', 'destination': 'model.safetensors', 'size': 4, 'sha256': '0' * 64}
            (root / 'models.json').write_text(json.dumps({'models': [model]}))
            errors = benchmark.check_required_models(config, ['native-fp8'], root)
            self.assertIn('missing', errors[0]['error'])
            self.assertIn('--model transformer_fp8', errors[0]['download_command'])
            (root / 'model.safetensors').write_bytes(b'bad!')
            errors = benchmark.check_required_models(config, ['native-fp8'], root)
            self.assertIn('SHA-256', errors[0]['error'])
            with patch.object(benchmark, 'check_required_models', return_value=errors), patch.object(benchmark, 'start_server') as start, patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(benchmark.main(['--suite', 'formats', '--case', 'native-fp8']), 2)
            start.assert_not_called()

    def test_timeline_filters_other_prompts_and_records_cache(self):
        benchmark = load()
        events = [
            {'elapsed_seconds': 0, 'type': 'executing', 'data': {'prompt_id': 'other', 'node': '1'}},
            {'elapsed_seconds': 1, 'type': 'executing', 'data': {'prompt_id': 'ours', 'node': '382'}},
            {'elapsed_seconds': 3, 'type': 'progress', 'data': {'prompt_id': 'ours', 'node': '382', 'value': 1, 'max': 8}},
            {'elapsed_seconds': 5, 'type': 'executing', 'data': {'prompt_id': 'ours', 'node': '545'}},
            {'elapsed_seconds': 7, 'type': 'executing', 'data': {'prompt_id': 'ours', 'node': None}},
        ]
        history = {'status': {'messages': [['execution_cached', {'nodes': ['477']}]]}}
        result = benchmark.summarize_execution(events, 'ours', history, {'382': {'class_type': 'SamplerCustomAdvanced'}, '545': {'class_type': 'VAEDecodeTiled'}})
        self.assertEqual(len(result['events']), 4)
        self.assertEqual(result['node_wall_seconds']['382']['seconds'], 4)
        self.assertEqual(result['cached_nodes'], ['477'])
        self.assertTrue(result['sampling_observed'])
        self.assertFalse(result['sampler_cached'])
        history['status']['messages'][0][1]['nodes'].append('382')
        self.assertTrue(benchmark.summarize_execution(events, 'ours', history, {})['sampler_cached'])

    def test_changed_inputs_require_explicit_override(self):
        benchmark = load()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input'; path.write_text('changed')
            spec = {'path': str(path), 'sha256': '0' * 64}
            with self.assertRaisesRegex(ValueError, 'hash'):
                benchmark.checked_input(spec, None)
            self.assertFalse(benchmark.checked_input(spec, path)['matches_frozen_input'])

    def test_timeout_preserves_owned_server(self):
        benchmark = load()
        process = Mock()
        process.pid = 1234
        process.poll.return_value = None
        self.assertFalse(benchmark.finish_server(process, {'status': 'timeout', 'prompt_id': 'p'}))
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        self.assertTrue(benchmark.finish_server(process, {'status': 'success'}))
        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_lost_history_with_known_prompt_preserves_server(self):
        benchmark = load()
        process = Mock()
        process.poll.return_value = None
        self.assertFalse(benchmark.finish_server(process, {'status': 'error', 'stage': 'history', 'prompt_id': 'p', 'error': 'connection lost'}))
        process.send_signal.assert_not_called()
        self.assertFalse(benchmark.finish_server(process, {'status': 'error', 'stage': 'submit'}))
        process.send_signal.assert_not_called()
        self.assertTrue(benchmark.finish_server(process, {'status': 'error', 'prompt_id': 'p', 'history': {'status': {'status_str': 'error'}}}))
        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_occupied_port_never_spawns_or_changes_process(self):
        benchmark = load()
        with patch.object(benchmark, 'port_busy', return_value=True), patch.object(benchmark.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                benchmark.start_server('legacy', Mock(), 1)
        spawn.assert_not_called()

    def test_trace_is_labeled_and_wraps_only_owned_launch(self):
        benchmark = load()
        with patch.dict(os.environ, {'ROCM_PATH': '/custom/sdk'}):
            command = benchmark.server_command('legacy', Path('/tmp/bfs-trace'))
        self.assertEqual(command[0], '/custom/sdk/bin/rocprofv3')
        self.assertIn('--memory-copy-trace', command)
        self.assertEqual(command[-3:], [str(ROOT / 'run-bfs.sh'), '--profile', 'legacy'])

    def test_benchmark_default_sdk_environment_reaches_smoke(self):
        benchmark = load()
        with patch.dict(os.environ, {'PATH': '/usr/bin', 'HIP_PATH': '/opt/rocm'}, clear=True), \
             patch.object(benchmark, 'check_required_models', return_value=[{'error': 'missing'}]), \
             patch('sys.stdout', new_callable=io.StringIO):
            benchmark.main(['--suite', 'formats'])
            sdk = str(Path.home() / '.local/opt/rocm-10.0.0-gfx120X-all')
            self.assertEqual(os.environ['ROCM_PATH'], sdk)
            self.assertEqual(os.environ['HIP_PATH'], sdk)
            self.assertEqual(os.environ['PATH'], sdk + '/bin:/usr/bin')

    def test_dry_run_never_starts_server(self):
        benchmark = load()
        with patch.object(benchmark, 'start_server') as start, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(benchmark.main(['--suite', 'baseline', '--dry-run']), 0)
        start.assert_not_called()

    def test_external_pid_requires_explicit_external_mode(self):
        benchmark = load()
        with self.assertRaises(SystemExit), patch('sys.stderr', new_callable=io.StringIO):
            benchmark.main(['--pid', '12', '--dry-run'])

    def test_cached_sampler_is_excluded_even_if_output_passes(self):
        benchmark = load()
        graph = json.loads((ROOT / 'workflows/bfs-v3-sintel-baseline-api.json').read_text())
        record = {'status': 'success', 'prompt_id': 'p', 'wall_seconds': 0.2, 'sampling': {}}
        timeline = {'sampler_cached': True, 'sampling_observed': False}
        args = SimpleNamespace(external_server=True, pid=None, trace=False, startup_timeout=1, timeout=1, interval=1)
        schemas = {node['class_type']: {} for node in graph.values()}
        with tempfile.TemporaryDirectory(prefix='bench-test-') as tmp:
            directory = Path(tmp)
            def request(url):
                return json.dumps(schemas if url.endswith('/object_info') else {}).encode()
            with patch.object(benchmark.smoke, 'request', side_effect=request), patch.object(benchmark, 'execute_smoke', return_value=(record, timeline)), patch.object(benchmark.subprocess, 'run') as review:
                row = benchmark.run_case('baseline', {'profile': 'legacy'}, 1, args, directory, {}, graph, None)
            self.assertEqual(row['status'], 'cached_output')
            self.assertFalse(row['eligible_for_performance_comparison'])
            self.assertIsNone(row['owned_server_stopped'])
            review.assert_not_called()

    def test_formats_are_explicitly_blocked_before_server_start(self):
        benchmark = load()
        with patch.object(benchmark, 'check_required_models', return_value=[{'error': 'missing artifact'}]), patch.object(benchmark, 'start_server') as start, patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(benchmark.main(['--suite', 'formats']), 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked')
        start.assert_not_called()

    def test_warm_repeats_share_server_and_exclude_first_result(self):
        benchmark = load()
        args = SimpleNamespace(session='warm', repeats=3, startup_timeout=1)
        process = Mock(pid=1234)
        process.poll.return_value = None
        rows = []
        def run_case(name, case, repeat, *rest, **kwargs):
            self.assertIs(kwargs['shared_process'], process)
            self.assertTrue(kwargs['defer_cleanup'])
            row = {'case': name, 'repeat': repeat, 'run_id': f'run-{repeat}', 'status': 'success', 'wall_seconds': repeat,
                   'eligible_for_performance_comparison': True, 'safe_to_stop_owned_server': True}
            case_dir = rest[1] / f'{name}-{repeat}'
            case_dir.mkdir()
            (case_dir / 'summary.json').write_text(json.dumps(row))
            return row
        with tempfile.TemporaryDirectory() as tmp, patch.object(benchmark, 'start_server', return_value=process) as start, patch.object(benchmark, 'run_case', side_effect=run_case):
            rows = benchmark.run_repeats('baseline', {'profile': 'legacy'}, args, Path(tmp), {}, {}, None)
            first_summary = json.loads((Path(tmp) / 'baseline-1/summary.json').read_text())
            self.assertFalse(first_summary['eligible_for_performance_comparison'])
            self.assertTrue(first_summary['warmup'])
        start.assert_called_once()
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]['warmup'])
        self.assertFalse(rows[0]['eligible_for_performance_comparison'])
        self.assertTrue(all(row['eligible_for_performance_comparison'] for row in rows[1:]))
        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_warm_ambiguous_job_stops_repetition_and_retains_process(self):
        benchmark = load()
        args = SimpleNamespace(session='warm', repeats=3, startup_timeout=1)
        process = Mock(pid=1234)
        process.poll.return_value = None
        row = {'case': 'baseline', 'repeat': 1, 'status': 'timeout', 'run_id': 'p', 'eligible_for_performance_comparison': False,
               'safe_to_stop_owned_server': False, 'retained_server_pid': 1234}
        with tempfile.TemporaryDirectory() as tmp, patch.object(benchmark, 'start_server', return_value=process), patch.object(benchmark, 'run_case', return_value=row) as run:
            rows = benchmark.run_repeats('baseline', {'profile': 'legacy'}, args, Path(tmp), {}, {}, None)
        self.assertEqual(len(rows), 1)
        run.assert_called_once()
        process.send_signal.assert_not_called()
        self.assertEqual(rows[0]['retained_server_pid'], 1234)

    def test_warm_launch_preserves_selected_node_cache_policy(self):
        benchmark = load()
        for profile in ['legacy', 'no-cache']:
            command = benchmark.server_command(profile, session='warm')
            runtime = json.loads((ROOT / 'config/runtime-profiles.json').read_text())
            effective_count = command.count('--cache-none') + runtime[profile].count('--cache-none')
            self.assertEqual(effective_count, 1 if profile == 'no-cache' else 0)

    def test_warm_video_upload_names_change_without_changing_bytes(self):
        benchmark = load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'; source.write_bytes(b'identical source video')
            inputs = {'video': {'path': str(source), 'sha256': benchmark.smoke.digest(source)},
                      'reference': {'path': str(root / 'reference.png'), 'sha256': 'reference'}}
            original = json.loads(json.dumps(inputs))
            first = benchmark.prepare_run_inputs(inputs, 'first', root, 'warm')
            second = benchmark.prepare_run_inputs(inputs, 'second', root, 'warm')
            self.assertEqual(inputs, original)
            self.assertNotEqual(Path(first['video']['path']).name, Path(second['video']['path']).name)
            self.assertEqual(Path(first['video']['path']).suffix, '.mp4')
            self.assertEqual(Path(first['video']['path']).read_bytes(), source.read_bytes())
            self.assertEqual(first['video']['sha256'], original['video']['sha256'])
            self.assertEqual(second['video']['sha256'], original['video']['sha256'])
            self.assertEqual(first['reference'], original['reference'])
            self.assertEqual(benchmark.prepare_run_inputs(inputs, 'fresh', root, 'fresh'), original)

    def test_warm_copy_detects_changed_source(self):
        benchmark = load()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.mp4'; source.write_bytes(b'changed video')
            inputs = {'video': {'path': str(source), 'sha256': '0' * 64}}
            with self.assertRaisesRegex(ValueError, 'hash'):
                benchmark.prepare_run_inputs(inputs, 'changed', root, 'warm')

    def test_warm_rejects_external_and_trace_modes(self):
        benchmark = load()
        for extra in [['--external-server'], ['--trace']]:
            with self.assertRaises(SystemExit), patch('sys.stderr', new_callable=io.StringIO):
                benchmark.main(['--session', 'warm', '--dry-run', *extra])


if __name__ == '__main__':
    unittest.main()
