"""The only place that starts child processes.

Secrets go to children through stdin only: never argv, never ``env=``, never
``shell=True``. ``subprocess`` is looked up at call time so tests can patch
``subprocess.Popen`` and record every child.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence


def run(argv: Sequence[str], *, input: str | None = None, timeout: float | None = None,
        check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``argv`` to completion, capturing stdout and stderr as text."""
    return subprocess.run(
        list(argv),
        input=input,
        stdin=None if input is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def spawn_detached(argv: Sequence[str], *, input: str | None = None) -> None:
    """Start ``argv`` in its own session and return without waiting for it."""
    child = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    if input is not None:
        assert child.stdin is not None
        try:
            child.stdin.write(input)
        finally:
            child.stdin.close()
