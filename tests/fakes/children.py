"""ChildRecorder: replaces ``subprocess.Popen`` and records every child process.

``qutewarden.proc`` is the only place that starts children and looks up
``subprocess.Popen`` / ``subprocess.run`` at call time, so patching
``subprocess.Popen`` sees all of them. No child actually runs: each one
"exits" 0 with empty output.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Child:
    argv: list[str]
    env: dict[str, str]  # the environment the child would get (inherited if env=None)
    stdin: list[str] = field(default_factory=list)


class _FakePopen:
    def __init__(self, recorder: ChildRecorder, args: Any, **kwargs: Any) -> None:
        argv = [args] if isinstance(args, (str, bytes)) else list(args)
        env = kwargs.get("env")
        self.child = Child([os.fsdecode(a) for a in argv],
                           dict(os.environ if env is None else env))
        recorder.children.append(self.child)
        self.args = args
        self.pid = 0
        self.returncode: int | None = None
        text = bool(kwargs.get("text") or kwargs.get("universal_newlines")
                    or kwargs.get("encoding") or kwargs.get("errors"))
        self.stdin = _Stdin(self.child) if kwargs.get("stdin") == -1 else None  # PIPE
        empty = "" if text else b""
        self._empty = empty
        self.stdout = io.StringIO() if text else io.BytesIO()
        self.stderr = io.StringIO() if text else io.BytesIO()

    def __enter__(self) -> _FakePopen:
        return self

    def __exit__(self, *exc: object) -> None:
        self.wait()

    def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[Any, Any]:
        if input:
            self.child.stdin.append(input if isinstance(input, str) else input.decode())
        self.returncode = 0
        return self._empty, self._empty

    def poll(self) -> int:
        self.returncode = 0
        return 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        pass

    terminate = kill


class _Stdin:
    def __init__(self, child: Child) -> None:
        self._child = child
        self.closed = False

    def write(self, data: Any) -> int:
        self._child.stdin.append(data if isinstance(data, str) else data.decode())
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class ChildRecorder:
    def __init__(self) -> None:
        self.children: list[Child] = []

    def popen(self, args: Any, *a: Any, **kwargs: Any) -> _FakePopen:
        return _FakePopen(self, args, **kwargs)
