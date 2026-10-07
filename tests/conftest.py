from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from fakes.qutebrowser import FakeQutebrowser


@pytest.fixture
def fake_qutebrowser(tmp_path: Path) -> Iterator[FakeQutebrowser]:
    qb = FakeQutebrowser(tmp_path)
    yield qb
    qb.close()
