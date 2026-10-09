"""GLOSSARY.md's _Avoid_ words stay out of the docs, the repo files and the code.

Only the unambiguous ones are checked here; words with an innocent everyday
use (password, site, match, insert, client, ...) are left to review.
ADRs are records of their time and aren't scanned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

BANNED = {
    "cipher": "Item",
    "credential": "Item, or secret",
    "autotype": "Fill",
    "autologin": "Auto-fill",
    "instant fill": "Auto-fill",
    "force fill": "Mismatch fill",
    "protected item": "Re-prompt item",
    "locked item": "Re-prompt item",
    "name matching": "URI match",
    "domain lookup": "URI match",
}


def _avoid_words() -> set[str]:
    text = (ROOT / "GLOSSARY.md").read_text()
    words: set[str] = set()
    for line in re.findall(r"^_Avoid_: (.*)$", text, re.MULTILINE):
        for word in line.split(","):
            words.add(re.sub(r"\(.*?\)", "", word).strip().lower())
    return words


def _scanned_files() -> list[Path]:
    docs = [p for p in (ROOT / "docs").rglob("*.md") if "adr" not in p.parts]
    code = [*(ROOT / "src").rglob("*.py"), *(ROOT / "src").rglob("*.js")]
    repo = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "SECURITY.md"]
    templates = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
    return [*repo, *templates, *docs, *code]


def test_banned_words_are_glossary_avoid_words():
    assert set(BANNED) <= _avoid_words()


@pytest.mark.parametrize("path", _scanned_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_no_avoided_glossary_words(path: Path):
    hits = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        for word, use in BANNED.items():
            if re.search(rf"\b{word}s?\b", line, re.IGNORECASE):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {word!r} (GLOSSARY: use {use})")
    assert not hits, "\n".join(hits)
