"""Run a child process, retrying when something outside the repository signals it.

A test child (a render, an ffmpeg decode, a node fixture) that dies of SIGTERM was not judging the code:
nothing in this repository sends that signal to its children, so it comes from a cleanup or guard on a shared
workstation. Such a child is run again; a verdict (any exit status, including a negative one from another signal)
is returned as it is. A child signalled on every attempt fails loudly with the signal named, never silently.
"""
from __future__ import annotations

import signal
import subprocess

EXTERNAL_SIGNALS = (signal.SIGTERM,)  # SIGHUP is POSIX-only and the portability audit forbids it in source
DEFAULT_ATTEMPTS = 2


def _signal_of(returncode):
    if returncode is None or returncode >= 0:
        return None
    try:
        number = signal.Signals(-returncode)
    except ValueError:
        return None
    return number if number in EXTERNAL_SIGNALS else None


def _note(number, attempts):
    return (f'child terminated by {number.name} on all {attempts} attempts; the signal was sent from outside the '
            f'child (nothing in this repository sends it), so this run says nothing about the code under test.')


def _prefixed(text, note):
    if isinstance(text, bytes):
        return note.encode() + b'\n' + text
    return note + ('\n' + text if text else '')


def run(command, *, attempts=DEFAULT_ATTEMPTS, runner=subprocess.run, reset=None, **kwargs):
    """subprocess.run, run again up to ``attempts`` times while the child dies of an outside SIGTERM.

    ``reset`` is called (no arguments) before every re-run, never before the first attempt, so a child that
    mutates its outputs (and refuses to start over existing ones) begins each re-run from a clean state.
    """
    if attempts < 1:
        raise ValueError('attempts must be at least 1')
    for attempt in range(1, attempts + 1):
        if attempt > 1 and reset is not None:
            reset()
        try:
            completed = runner(command, **kwargs)
        except subprocess.CalledProcessError as error:
            number = _signal_of(error.returncode)
            if number is None:
                raise
            if attempt == attempts:
                error.stderr = _prefixed(error.stderr, _note(number, attempts))
                raise
            continue
        number = _signal_of(completed.returncode)
        if number is None:
            return completed
        if attempt == attempts:
            completed.stderr = _prefixed(completed.stderr, _note(number, attempts))
            return completed
    raise AssertionError('unreachable')
