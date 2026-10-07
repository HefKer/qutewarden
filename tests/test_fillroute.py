import os
import stat
import time
from pathlib import Path

import pytest

from fakes.qutebrowser import FakeQutebrowser
from qutewarden.errors import QutewardenError
from qutewarden.fillroute import FillRouteError, pipe_dir, send_js
from qutewarden.qute import FILL_WORLD_ID, Qute

JS = '(function () { var a = {"password": "QWSECRET-password-github"}; })();'


def mode_of(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


# --- pipe_dir -------------------------------------------------------------

def test_pipe_dir_is_created_private_under_xdg_runtime_dir(tmp_path):
    path = pipe_dir({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert path == tmp_path / "qutewarden"
    assert path.is_dir()
    assert mode_of(path) == 0o700


def test_pipe_dir_without_xdg_runtime_dir_is_an_error():
    with pytest.raises(FillRouteError, match="XDG_RUNTIME_DIR"):
        pipe_dir({})


def test_pipe_dir_reuses_an_existing_private_dir(tmp_path):
    (tmp_path / "qutewarden").mkdir(mode=0o700)
    assert pipe_dir({"XDG_RUNTIME_DIR": str(tmp_path)}) == tmp_path / "qutewarden"


def test_pipe_dir_refuses_a_dir_others_can_access(tmp_path):
    (tmp_path / "qutewarden").mkdir()
    os.chmod(tmp_path / "qutewarden", 0o755)
    with pytest.raises(FillRouteError, match="permissions"):
        pipe_dir({"XDG_RUNTIME_DIR": str(tmp_path)})


def test_pipe_dir_refuses_a_symlink(tmp_path):
    (tmp_path / "elsewhere").mkdir(mode=0o700)
    (tmp_path / "qutewarden").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(FillRouteError):
        pipe_dir({"XDG_RUNTIME_DIR": str(tmp_path)})


# --- send_js --------------------------------------------------------------

@pytest.fixture
def runtime_dir(tmp_path) -> Path:
    path = tmp_path / "run" / "qutewarden"
    path.parent.mkdir()
    return path


@pytest.fixture
def qute(fake_qutebrowser: FakeQutebrowser) -> Qute:
    return Qute.from_environ(fake_qutebrowser.environ())


def test_send_js_hands_the_js_to_qutebrowser_through_a_pipe(fake_qutebrowser, qute, runtime_dir):
    send_js(qute, JS, runtime_dir=runtime_dir)
    fake_qutebrowser.close()

    assert fake_qutebrowser.js == [JS]
    [command] = fake_qutebrowser.commands
    pipe = fake_qutebrowser.pipes[0].path
    assert command == f"jseval --quiet --world={FILL_WORLD_ID} --file {pipe}"
    assert pipe.parent == runtime_dir


def test_the_secret_never_goes_into_qute_fifo(fake_qutebrowser, qute, runtime_dir):
    send_js(qute, JS, runtime_dir=runtime_dir)
    fake_qutebrowser.close()
    assert not any("QWSECRET" in c for c in fake_qutebrowser.commands)


def test_pipe_is_a_private_fifo_in_a_private_dir(fake_qutebrowser, qute, runtime_dir):
    send_js(qute, JS, runtime_dir=runtime_dir)
    fake_qutebrowser.close()
    [seen] = fake_qutebrowser.pipes
    assert seen.is_fifo
    assert seen.mode == 0o600
    assert seen.dir_mode == 0o700
    assert seen.uid == os.getuid()


def test_pipe_is_removed_after_success(fake_qutebrowser, qute, runtime_dir):
    send_js(qute, JS, runtime_dir=runtime_dir)
    fake_qutebrowser.close()
    assert list(runtime_dir.iterdir()) == []


def test_each_run_gets_a_new_pipe_name(fake_qutebrowser, qute, runtime_dir):
    send_js(qute, JS, runtime_dir=runtime_dir)
    send_js(qute, JS, runtime_dir=runtime_dir)
    fake_qutebrowser.close()
    first, second = (seen.path for seen in fake_qutebrowser.pipes)
    assert first != second
    assert fake_qutebrowser.js == [JS, JS]


def test_large_scripts_are_written_completely(fake_qutebrowser, qute, runtime_dir):
    big = "/*" + "x" * 300_000 + "*/" + JS
    send_js(qute, big, runtime_dir=runtime_dir)
    fake_qutebrowser.close()
    assert fake_qutebrowser.js == [big]


def test_qutebrowser_that_never_reads_the_pipe_times_out(tmp_path, runtime_dir):
    qb = FakeQutebrowser(tmp_path, reads_js_files=False)
    qute = Qute.from_environ(qb.environ())
    start = time.monotonic()
    try:
        with pytest.raises(FillRouteError, match="didn't read the fill script"):
            send_js(qute, JS, runtime_dir=runtime_dir, timeout=0.2)
    finally:
        qb.close()
    assert 0.2 <= time.monotonic() - start < 2
    assert list(runtime_dir.iterdir()) == []
    assert len(qb.commands) == 1  # the jseval line was sent, with no secret in it
    assert "QWSECRET" not in qb.commands[0]


def test_pipe_is_removed_when_sending_the_command_fails(runtime_dir):
    no_qutebrowser = Qute.from_environ({})
    with pytest.raises(QutewardenError, match="QUTE_FIFO"):
        send_js(no_qutebrowser, JS, runtime_dir=runtime_dir, timeout=0.1)
    assert list(runtime_dir.iterdir()) == []


def test_runtime_dir_with_loose_permissions_is_refused(qute, runtime_dir):
    runtime_dir.mkdir()
    os.chmod(runtime_dir, 0o777)
    with pytest.raises(FillRouteError, match="permissions"):
        send_js(qute, JS, runtime_dir=runtime_dir, timeout=0.1)
    assert list(runtime_dir.iterdir()) == []
