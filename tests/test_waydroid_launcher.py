import os
import signal
from pathlib import Path
import subprocess
import tempfile
import unittest


LAUNCHER = Path(__file__).resolve().parents[1] / 'scripts/launch-waydroid.sh'


class WaydroidLauncherTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        binary = root / 'waydroid'
        binary.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  status)
    if [[ "${PERSIST:-}" == 1 && -f "$STARTED" && "${PERSIST_READY:-}" == 1 ]]; then
      printf 'Session: RUNNING\\nContainer: RUNNING\\n'
      exit
    fi
    if [[ "${HANG_STATUS:-}" == 1 ]]; then /bin/sleep 10; fi
    if [[ "${DELAYED:-}" == 1 && -f "$STARTED" ]]; then
      count=$(cat "$COUNT" 2>/dev/null || printf 0)
      count=$((count + 1))
      printf '%s' "$count" > "$COUNT"
      if ((count >= 3)); then
        printf 'Session: RUNNING\\nContainer: RUNNING\\n'
        exit
      fi
    fi
    printf 'Session: %s\\nContainer: %s\\n' "${SESSION:-RUNNING}" "${CONTAINER:-RUNNING}"
    ;;
  'prop get sys.boot_completed')
    if [[ "${HANG_PROP:-}" == 1 ]]; then /bin/sleep 10; fi
    printf '%s\\n' "${BOOT:-1}"
    ;;
  'session start')
    if [[ "${PERSIST:-}" == 1 ]]; then
      touch "$STARTED"
      printf '%s' "$$" > "$PIDFILE"
      printf 'starter output\\n'
      exec /bin/sleep 10
    fi
    if [[ "${DELAYED:-}" == 1 ]]; then touch "$STARTED"; exit 0; fi
    printf 'start failed\\n' >&2; exit 7
    ;;
esac
''')
        binary.chmod(0o755)
        sleep = root / 'sleep'
        sleep.write_text('#!/bin/bash\n/bin/sleep 0.02\n')
        sleep.chmod(0o755)
        self.calls = root / 'calls'
        self.env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}",
                        CALLS=str(self.calls), STARTED=str(root / 'started'),
                        COUNT=str(root / 'count'), PIDFILE=str(root / 'pid'), WAYDROID_START_TIMEOUT='1')
        self.pidfile = root / 'pid'

    def run_launcher(self, *args, **overrides):
        self.calls.unlink(missing_ok=True)
        result = subprocess.run([str(LAUNCHER), *args], env=dict(self.env, **overrides),
                                text=True, capture_output=True, timeout=3)
        return result, self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_ensure_ready_does_not_open_ui(self):
        result, calls = self.run_launcher('--ensure-session')
        self.assertEqual(result.returncode, 0)
        self.assertIn('prop get sys.boot_completed', calls)
        self.assertNotIn('show-full-ui', calls)
        self.assertNotIn('session start', calls)

    def test_frozen_session_can_be_probed(self):
        result, calls = self.run_launcher('--ensure-session', CONTAINER='FROZEN')
        self.assertEqual(result.returncode, 0)
        self.assertIn('prop get sys.boot_completed', calls)
        self.assertNotIn('session start', calls)

    def test_unfinished_boot_times_out(self):
        result, calls = self.run_launcher('--ensure-session', BOOT='0')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr.lower())
        self.assertNotIn('show-full-ui', calls)

    def test_hung_status_probe_times_out(self):
        result, calls = self.run_launcher('--ensure-session', HANG_STATUS='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr.lower())
        self.assertEqual(calls, ['status'])

    def test_hung_property_probe_times_out(self):
        result, calls = self.run_launcher('--ensure-session', HANG_PROP='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('timed out', result.stderr.lower())
        self.assertIn('prop get sys.boot_completed', calls)
        self.assertNotIn('show-full-ui', calls)

    def test_persistent_starter_does_not_hold_output_open(self):
        for ready in ('1', '0'):
            with self.subTest(ready=ready):
                Path(self.env['STARTED']).unlink(missing_ok=True)
                self.pidfile.unlink(missing_ok=True)
                try:
                    result, calls = self.run_launcher('--ensure-session', SESSION='STOPPED',
                                                      CONTAINER='STOPPED', PERSIST='1',
                                                      PERSIST_READY=ready)
                    self.assertEqual(result.returncode == 0, ready == '1')
                    self.assertIn('session start', calls)
                    if ready == '0':
                        self.assertIn('starter output', result.stderr)
                finally:
                    if self.pidfile.exists():
                        try:
                            os.kill(int(self.pidfile.read_text()), signal.SIGTERM)
                        except ProcessLookupError:
                            pass

    def test_failed_session_start_is_reported(self):
        result, calls = self.run_launcher('--ensure-session', SESSION='STOPPED', CONTAINER='STOPPED')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('start failed', result.stderr)
        self.assertIn('session start', calls)

    def test_successful_start_waits_for_readiness(self):
        result, calls = self.run_launcher(SESSION='STOPPED', CONTAINER='STOPPED', DELAYED='1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('session start', calls)
        self.assertGreaterEqual(calls.count('status'), 4)
        self.assertLess(calls.index('prop get sys.boot_completed'), calls.index('show-full-ui'))

    def test_argument_validation(self):
        for args in [('--app',), ('--app', '--ensure-session'),
                     ('--ensure-session', '--app', 'org.example'),
                     ('--app', 'org.example', '--ensure-session')]:
            with self.subTest(args=args):
                result, calls = self.run_launcher(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])

    def test_timeout_validation(self):
        for value in ('', '0', '-1', 'invalid'):
            with self.subTest(value=value):
                result, calls = self.run_launcher('--ensure-session', WAYDROID_START_TIMEOUT=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('positive integer', result.stderr)
                self.assertEqual(calls, [])

    def test_launch_after_ready(self):
        for args, command in [((), 'show-full-ui'), (('--app', 'org.example'), 'app launch org.example')]:
            with self.subTest(args=args):
                result, calls = self.run_launcher(*args)
                self.assertEqual(result.returncode, 0)
                self.assertLess(calls.index('prop get sys.boot_completed'), calls.index(command))
