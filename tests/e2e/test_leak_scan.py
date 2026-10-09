"""The e2e no-leak scan itself; runs in the normal suite, no browser needed."""

from __future__ import annotations

import os
from collections.abc import Set as AbstractSet
from pathlib import Path

from e2e.harness import leak_scan

MARKER = "QWE2E0123456789AB-pw-a"


def _scan(tmp_path: Path, *, log: bytes = b"", codes: AbstractSet[str] = frozenset(),
          samples: dict[bytes, str] | None = None) -> list[str]:
    (tmp_path / "qb").mkdir(exist_ok=True)
    (tmp_path / "run").mkdir(exist_ok=True)
    (tmp_path / "qb.log").write_bytes(log)
    return leak_scan({MARKER}, set(codes), log=tmp_path / "qb.log", basedir=tmp_path / "qb",
                     runtime_dir=tmp_path / "run", samples=samples or {})


def test_a_clean_run_has_no_hits(tmp_path: Path):
    assert _scan(tmp_path, log=b'{"message": "filling Example A (alice)"}\n') == []


def test_a_marker_in_the_log_is_a_hit(tmp_path: Path):
    log = f'{{"message": "Got userscript command: jseval {MARKER}"}}\n'.encode()
    assert _scan(tmp_path, log=log) == [f"qutebrowser log: {MARKER}"]


def test_a_utf16_marker_in_a_basedir_file_is_a_hit(tmp_path: Path):
    (tmp_path / "qb" / "data").mkdir(parents=True)
    (tmp_path / "qb" / "data" / "Local Storage").write_bytes(MARKER.encode("utf-16-le"))
    assert _scan(tmp_path) == [f"{tmp_path / 'qb' / 'data' / 'Local Storage'}: {MARKER}"]


def test_a_marker_in_a_proc_snapshot_is_a_hit(tmp_path: Path):
    samples = {b"wl-copy\0" + MARKER.encode() + b"\0": "pid 7 wl-copy cmdline"}
    assert _scan(tmp_path, samples=samples) == [f"/proc pid 7 wl-copy cmdline: {MARKER}"]


def test_a_totp_code_counts_only_as_a_whole_number(tmp_path: Path):
    assert _scan(tmp_path, log=b'"created": 1791514803.3234777', codes={"323477"}) == []
    assert _scan(tmp_path, log=b"code 323477.", codes={"323477"}) == [
        "qutebrowser log: 323477"]


def test_a_leftover_fill_pipe_is_a_hit(tmp_path: Path):
    (tmp_path / "run").mkdir()
    os.mkfifo(tmp_path / "run" / "fill-0.js")
    assert _scan(tmp_path) == [f"{tmp_path / 'run' / 'fill-0.js'}: left behind"]
