import subprocess
import sys
from pathlib import Path

import pytest

from qutewarden import proc


def test_run_passes_input_via_stdin_and_captures_output():
    result = proc.run([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
                      input="hello")
    assert result.stdout == "HELLO\n"
    assert result.returncode == 0


def test_run_check_raises_on_failure():
    with pytest.raises(subprocess.CalledProcessError):
        proc.run([sys.executable, "-c", "raise SystemExit(3)"])


def test_run_without_check_returns_failure():
    result = proc.run([sys.executable, "-c", "import sys; sys.stderr.write('bad'); sys.exit(3)"],
                      check=False)
    assert result.returncode == 3
    assert result.stderr == "bad"


def test_run_goes_through_subprocess_popen_at_call_time(monkeypatch):
    seen = []
    real_popen = subprocess.Popen

    def recording_popen(argv, *args, **kwargs):
        seen.append((list(argv), kwargs.get("shell", False), kwargs.get("env")))
        return real_popen(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    proc.run([sys.executable, "-c", "pass"])
    proc.spawn_detached([sys.executable, "-c", "pass"])
    assert [argv[1:] for argv, _, _ in seen] == [["-c", "pass"], ["-c", "pass"]]
    assert all(shell is False and env is None for _, shell, env in seen)


def test_spawn_detached_feeds_stdin_and_does_not_wait(tmp_path: Path):
    out = tmp_path / "out"
    script = f"import sys, pathlib; pathlib.Path({str(out)!r}).write_text(sys.stdin.read())"
    proc.spawn_detached([sys.executable, "-c", script], input="value")
    import time
    for _ in range(200):
        if out.exists() and out.read_text() == "value":
            break
        time.sleep(0.01)
    assert out.read_text() == "value"
