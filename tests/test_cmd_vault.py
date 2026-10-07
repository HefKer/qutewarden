"""`vault`: pick from every Login item; Mismatch fill after confirmation; opt-in copy (#9)."""

from __future__ import annotations

import dataclasses

import pytest

from fakes.picker import FakePicker
from qutewarden import cli
from qutewarden.backend.fake import FakeBackend, fake_password
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"


@pytest.fixture
def vault(ctx, fake_qutebrowser):
    """Run ``qutewarden vault [flags]`` on ``url``; return the exit code."""

    def vault(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
              picker: FakePicker | None = None, clipboard: object = ...) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker,
                clipboard=ctx.clipboard if clipboard is ... else clipboard)

        try:
            return cli.main(["vault", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return vault


def test_the_picker_lists_every_login_item_not_only_candidates(vault):
    picker = FakePicker(choices=[None])
    assert vault(picker=picker) == 0
    assert picker.lines == [["GitHub — alice", "GitHub (work) — alice-work", "Example — bob",
                             "No TOTP — carol", "Never — dave", "Elsewhere — erin"]]


def test_picking_a_candidate_fills_it_without_asking(vault, fake_qutebrowser):
    picker = FakePicker(choices=[1], confirm=False)
    assert vault(picker=picker) == 0
    [js] = fake_qutebrowser.js
    assert '"mode": "auto"' in js
    assert f'"password": "{fake_password("github-alt")}"' in js
    assert '"origin": "https://github.com"' in js
    assert "Yes" not in sum(picker.lines, [])
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling GitHub (work) (alice-work)")]
