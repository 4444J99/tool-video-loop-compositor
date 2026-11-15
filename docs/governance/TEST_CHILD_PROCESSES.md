# Test child processes

Tests that spawn a render, an ffmpeg or ffprobe decode, or a node fixture run it through
`simvltanea.subprocess_retry.run`:

```python
from simvltanea import subprocess_retry as retry

result = retry.run(['node', '-e', script], capture_output=True, text=True, timeout=30)
```

The helper has the signature and the return value of `subprocess.run`. It runs the child once more
when the child died of SIGTERM, and returns any other verdict as it is, including an exit status or a
different signal. A child signalled on every attempt is returned (or raised, when `check=True`) with a
note on its stderr that names the signal and says the run judged nothing about the code.

## The sender of the SIGTERM is unconfirmed

Nothing in this repository sends SIGTERM to a test child: the sources contain no `kill`, `terminate`
or process-group signal aimed at a test's children. Failures of this kind were seen on a shared
workstation, in runs of the browser and render tests, and the sender was never observed. The workstation
may run a cleanup or a resource guard that signals long-lived children, but that is a hypothesis that no
log, process trace or reproduction has confirmed. Until the sender is identified (for example with a `dtruss` or `eslogger` trace of the signal
on a reproducing run), the retry is a containment of a failure that does not describe the code, not a
fix for its cause. Do not describe the cause as known in a commit, an issue or a review.

## What the lint covers

`src/simvltanea/test_subprocess_sweep_lint.py` fails when a test file calls `subprocess.run`,
`check_output`, `check_call`, `call` or `Popen` on a render, ffmpeg, ffprobe or node child, or on a
`python -m` module child (the CLI, a build or a verifier), without the helper. A command held in a variable, or unpacked into a list, is judged by what the module assigns to that
name (plain or annotated, at any depth, following one name to the next), whether it is passed
positionally or as `args=`. `import subprocess as sp` and `from subprocess import run` are followed. The match is on the words `ffmpeg`, `ffprobe`, `node`, `render`
and on a `-m` module run by a python executable, anywhere in the call, so a child whose arguments merely
mention one of them can be flagged. A call whose program is `git`, `swift` or `rm` is never flagged, and
`python -c` snippets are not covered. The helper has no `check_output` equivalent:
write `retry.run(command, check=True, stdout=subprocess.PIPE).stdout`.

The test keeps a `PENDING` list of files whose calls are not converted yet. A file outside the list
may not hold a bare call, and a file on the list that no longer holds one fails until it is removed,
so the list only shrinks.
