import os
import stat
from pathlib import Path

import pytest

from fakes.qutebrowser import FakeQutebrowser
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
