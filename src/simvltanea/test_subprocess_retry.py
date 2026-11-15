import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from simvltanea import subprocess_retry as retry

# Dies of SIGTERM the first time it runs (a marker file records the first run), then behaves.
KILLED_ONCE = '''
import os, signal, sys
marker = sys.argv[1]
if not os.path.exists(marker):
    open(marker, "w").close()
    os.kill(os.getpid(), signal.SIGTERM)
print("verdict")
'''


POSIX = unittest.skipUnless(os.name == 'posix', 'a killed child reports -SIGTERM only on POSIX; Windows reports exit code 15')


class SubprocessRetryTests(unittest.TestCase):
    def test_injected_runner_killed_once_is_run_again_on_every_platform(self):
        codes = [-signal.SIGTERM, 0]
        seen = []

        def runner(command, **kwargs):
            seen.append(kwargs)
            return SimpleNamespace(returncode=codes.pop(0), stderr='')

        done = retry.run(['x'], runner=runner, cwd='here')
        self.assertEqual((done.returncode, len(seen), seen[0]), (0, 2, {'cwd': 'here'}))

    def test_injected_runner_signalled_every_time_names_the_signal(self):
        runner = lambda command, **kwargs: SimpleNamespace(returncode=-signal.SIGTERM, stderr=b'')
        done = retry.run(['x'], runner=runner, attempts=3)
        self.assertTrue(done.stderr.startswith(b'child terminated by SIGTERM on all 3 attempts'))

    def test_injected_check_true_runner_raises_with_the_note_after_the_last_attempt(self):
        def runner(command, **kwargs):
            raise subprocess.CalledProcessError(-signal.SIGTERM, command, stderr='')

        with self.assertRaises(subprocess.CalledProcessError) as caught:
            retry.run(['x'], runner=runner)
        self.assertIn('SIGTERM on all 2 attempts', caught.exception.stderr)

    def test_injected_check_true_runner_reraises_other_failures_at_once(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(1)
            raise subprocess.CalledProcessError(1, command, stderr='real')

        with self.assertRaises(subprocess.CalledProcessError) as caught:
            retry.run(['x'], runner=runner)
        self.assertEqual((len(calls), caught.exception.stderr), (1, 'real'))

    @POSIX
    def test_a_child_killed_once_by_sigterm_is_run_again_and_its_verdict_returned(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'ran'
            done = retry.run([sys.executable, '-c', KILLED_ONCE, str(marker)], capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout.strip()), (0, 'verdict'))

    @POSIX
    def test_without_the_retry_the_same_child_reproduces_the_suite_failure(self):
        # The observed failure: returncode -15 and empty stderr, from a child that was not wrong.
        with tempfile.TemporaryDirectory() as directory:
            done = subprocess.run([sys.executable, '-c', KILLED_ONCE, str(Path(directory) / 'ran')], check=False, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stderr), (-signal.SIGTERM, ''))

    @POSIX
    def test_a_child_signalled_on_every_attempt_fails_loudly_naming_the_signal(self):
        always = 'import os, signal; os.kill(os.getpid(), signal.SIGTERM)'
        done = retry.run([sys.executable, '-c', always], capture_output=True, text=True, attempts=3)
        self.assertEqual(done.returncode, -signal.SIGTERM)
        self.assertIn('SIGTERM on all 3 attempts', done.stderr)
        self.assertIn('says nothing about the code under test', done.stderr)

    @POSIX
    def test_bytes_stderr_keeps_its_original_text(self):
        always = 'import os, signal, sys; sys.stderr.write("partial"); sys.stderr.flush(); os.kill(os.getpid(), signal.SIGTERM)'
        done = retry.run([sys.executable, '-c', always], capture_output=True, attempts=2)
        self.assertTrue(done.stderr.startswith(b'child terminated by SIGTERM on all 2 attempts'))
        self.assertTrue(done.stderr.endswith(b'partial'))

    def test_real_failures_and_other_signals_are_never_retried(self):
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=code[0], stderr='boom')

        for code in ([1], [-signal.SIGSEGV], [-signal.SIGINT], [-signal.SIGABRT], [0]):
            calls.clear()
            done = retry.run(['x'], runner=runner)
            self.assertEqual((len(calls), done.stderr), (1, 'boom'), code)

    @POSIX
    def test_check_true_raises_after_the_last_attempt_with_the_note_attached(self):
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            retry.run([sys.executable, '-c', 'import os, signal; os.kill(os.getpid(), signal.SIGTERM)'],
                      check=True, capture_output=True, text=True)
        self.assertEqual(caught.exception.returncode, -signal.SIGTERM)
        self.assertIn('SIGTERM on all 2 attempts', caught.exception.stderr)

    @POSIX
    def test_check_true_returns_normally_when_the_retry_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            done = retry.run([sys.executable, '-c', KILLED_ONCE, str(Path(directory) / 'ran')], check=True, capture_output=True, text=True)
            self.assertEqual(done.stdout.strip(), 'verdict')

    def test_attempts_below_one_are_refused(self):
        with self.assertRaises(ValueError):
            retry.run(['x'], attempts=0)


if __name__ == '__main__':
    unittest.main()
