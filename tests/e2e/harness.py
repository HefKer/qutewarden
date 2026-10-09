"""The processes of the e2e suite (ADR-0007) and the no-leak scan.

Everything lives under one short directory in ``/tmp`` (Unix socket paths are
limited to about 100 bytes): Vaultwarden's data, rbw's profile and XDG dirs,
qutebrowser's basedir, the displays' sockets and the scripted picker's and
pinentry's logs. ``isolated_environ`` builds the environment every child gets,
so nothing reaches the developer's own rbw profile, vault or qutebrowser.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, TypeVar

E2E_DIR = Path(__file__).resolve().parent
TESTS_DIR = E2E_DIR.parent
PAGES_DIR = TESTS_DIR / "pages"
SRC_DIR = TESTS_DIR.parent / "src"
BIN_DIR = E2E_DIR / "bin"

EMAIL = "e2e@example.com"
RBW_PROFILE = "qwe2e"
CLEAR_SECONDS = 2  # totp.clipboard_clear_seconds and vault.copy_clear_seconds
EQUIVALENT_DOMAINS = [["equiv-a.test", "equiv-b.test"]]  # matching.equivalent_domains
TIMEOUT = 30.0  # seconds any single wait may take

# The only variables taken from the developer's environment.
_PASSED_THROUGH = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "LOCALE_ARCHIVE", "TZ", "TZDIR",
                   "USER", "LOGNAME", "SSL_CERT_FILE", "NIX_SSL_CERT_FILE", "FONTCONFIG_FILE")

T = TypeVar("T")


class HarnessError(Exception):
    """A process of the harness didn't start or didn't answer in time."""


def wait_for(check: Callable[[], T | None], what: str, timeout: float = TIMEOUT,
             interval: float = 0.05) -> T:
    """Poll ``check`` until it returns something truthy; raise after ``timeout``."""
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise HarnessError(f"timed out after {timeout:g} s waiting for {what}")
        time.sleep(interval)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop_process(proc: subprocess.Popen[Any], timeout: float = 10.0) -> None:
    """SIGTERM, then SIGKILL, the whole process group of ``proc`` (started with a new session)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if proc.poll() is not None:
            break
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, sig)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)  # stragglers in the group


@dataclass(frozen=True)
class Dirs:
    """The directory layout under the session root."""

    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def runtime(self) -> Path:
        return self.root / "run"

    @property
    def basedir(self) -> Path:
        return self.root / "qb"

    def make(self) -> None:
        for path in (self.home, self.home / ".config", self.home / ".cache",
                     self.home / ".local" / "share", self.home / ".local" / "state",
                     self.basedir, self.root / "bin", self.root / "picker",
                     self.root / "pinentry", self.root / "vaultwarden"):
            path.mkdir(parents=True, exist_ok=True)
        self.runtime.mkdir(mode=0o700, exist_ok=True)


def isolated_environ(dirs: Dirs, extra: Mapping[str, str] = {}) -> dict[str, str]:
    """The environment of every child: own HOME, XDG dirs and rbw profile, nothing else."""
    env = {k: os.environ[k] for k in _PASSED_THROUGH if k in os.environ}
    env.update({
        "HOME": str(dirs.home),
        "XDG_CONFIG_HOME": str(dirs.home / ".config"),
        "XDG_CACHE_HOME": str(dirs.home / ".cache"),
        "XDG_DATA_HOME": str(dirs.home / ".local" / "share"),
        "XDG_STATE_HOME": str(dirs.home / ".local" / "state"),
        "XDG_RUNTIME_DIR": str(dirs.runtime),
        "RBW_PROFILE": RBW_PROFILE,
        "QW_E2E_PICKER_DIR": str(dirs.root / "picker"),
        "QW_E2E_PINENTRY_DIR": str(dirs.root / "pinentry"),
    })
    env.update(extra)
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
                "XDG_RUNTIME_DIR"):
        if not Path(env[key]).is_relative_to(dirs.root):
            raise HarnessError(f"{key} escapes the e2e root")
    return env


# --- Vaultwarden -------------------------------------------------------------------


class Vaultwarden:
    """A Vaultwarden server on 127.0.0.1 with its data in the session root."""

    def __init__(self, dirs: Dirs) -> None:
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        data = dirs.root / "vaultwarden"
        env = isolated_environ(dirs, {
            "DATA_FOLDER": str(data), "ROCKET_ADDRESS": "127.0.0.1",
            "ROCKET_PORT": str(self.port), "SIGNUPS_ALLOWED": "true",
            "WEB_VAULT_ENABLED": "false", "DOMAIN": self.url, "LOG_LEVEL": "warn",
        })
        with open(data / "server.log", "wb") as log:
            self._proc = subprocess.Popen(["vaultwarden"], env=env, cwd=data,
                                          stdin=subprocess.DEVNULL, stdout=log,
                                          stderr=subprocess.STDOUT, start_new_session=True)
        wait_for(self._alive, "Vaultwarden to start")

    def _alive(self) -> bool:
        if self._proc.poll() is not None:
            raise HarnessError("Vaultwarden exited; see its server.log")
        try:
            with urllib.request.urlopen(self.url + "/alive", timeout=1):
                return True
        except OSError:
            return False

    def stop(self) -> None:
        stop_process(self._proc)


# --- scripted pinentry and picker --------------------------------------------------


class Pinentry:
    """The scripted pinentry (bin/fake-pinentry): logs each call, answers as told.

    ``mode`` is "ok" (the master password), "cancel" or "wrong".
    """

    def __init__(self, dirs: Dirs, master_password: str) -> None:
        self.dir = dirs.root / "pinentry"
        self.path = dirs.root / "bin" / "pinentry"
        shutil.copy(BIN_DIR / "fake-pinentry", self.path)
        (self.dir / "password").write_text(master_password)
        self.mode = "ok"

    @property
    def mode(self) -> str:
        return (self.dir / "mode").read_text()

    @mode.setter
    def mode(self, value: str) -> None:
        (self.dir / "mode").write_text(value)

    def calls(self) -> list[dict[str, Any]]:
        """One dict per GETPIN: the description, prompt and error rbw set."""
        try:
            text = (self.dir / "calls.jsonl").read_text()
        except FileNotFoundError:
            return []
        return [json.loads(line) for line in text.splitlines()]


@dataclass
class PickerRequest:
    number: int
    argv: list[str]
    lines: list[str]

    @property
    def prompt(self) -> str | None:
        return self.argv[self.argv.index("-p") + 1] if "-p" in self.argv else None


class Picker:
    """The scripted dmenu-style picker (bin/fake-picker).

    Each run writes ``request-N.json`` and waits for ``answer-N.json``; tests
    read the request (``next``) and then ``answer`` it, so a test can act
    while the picker is open.
    """

    def __init__(self, dirs: Dirs) -> None:
        self.dir = dirs.root / "picker"
        # Named dmenu so qutewarden passes the prompt as `-p PROMPT`.
        self.path = dirs.root / "bin" / "dmenu"
        shutil.copy(BIN_DIR / "fake-picker", self.path)
        self._seen = 0

    def next(self, timeout: float = TIMEOUT) -> PickerRequest:
        """The next picker request, in order."""
        number = self._seen + 1
        path = self.dir / f"request-{number}.json"
        data = wait_for(lambda: _read_json(path), f"picker request {number}", timeout)
        self._seen = number
        return PickerRequest(number, data["argv"], data["lines"])

    def answer(self, request: PickerRequest, line: str | None) -> None:
        """Choose ``line`` (any text, as if typed) or cancel with None."""
        tmp = self.dir / f".answer-{request.number}"
        tmp.write_text(json.dumps({"line": line}))
        tmp.rename(self.dir / f"answer-{request.number}.json")

    def choose(self, line: str | None, *, expect_lines: Sequence[str] | None = None
               ) -> PickerRequest:
        """Wait for the next request and answer it with ``line``."""
        request = self.next()
        if expect_lines is not None:
            assert request.lines == list(expect_lines)
        self.answer(request, line)
        return request

    def pending(self) -> list[int]:
        """Requests that were never answered (the picker cancels them after a timeout)."""
        numbers = [int(p.stem.split("-")[1]) for p in self.dir.glob("request-*.json")]
        return [n for n in numbers if not (self.dir / f"answer-{n}.json").exists()]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return None


# --- rbw -----------------------------------------------------------------------------


class Rbw:
    """rbw with its own profile and XDG dirs, logged in to the e2e Vaultwarden."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = dict(env)

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["rbw", *args], env=self.env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=TIMEOUT, check=check)

    def setup(self, server: str, pinentry: Path) -> None:
        self.run("config", "set", "email", EMAIL)
        self.run("config", "set", "base_url", server)
        self.run("config", "set", "pinentry", str(pinentry))
        self.run("login")
        self.run("sync")

    def is_unlocked(self) -> bool:
        return self.run("unlocked", check=False).returncode == 0

    def stop(self) -> None:
        self.run("stop-agent", check=False)


# --- test pages ----------------------------------------------------------------------

# Appended to every page: reports the page's fields every 100 ms. Runs in the
# page's main world, so it also sees `window.submitted` of pages that count submits.
_REPORT_JS = """<script>
(() => {
  const load = Math.random().toString(36).slice(2);
  const report = () => {
    const fields = {};
    for (const el of document.querySelectorAll("input")) fields[el.id || el.name] = el.value;
    fetch("/__e2e/report", {method: "POST", body: JSON.stringify({
      load, href: location.href, origin: location.origin, fields,
      submitted: window.submitted === undefined ? null : window.submitted})});
  };
  report();
  setInterval(report, 100);
})();
</script>"""


@dataclass
class PageReport:
    load: str
    href: str
    origin: str
    fields: dict[str, str]
    submitted: int | None
    received: float  # time.monotonic() on arrival


@dataclass
class Submission:
    host: str
    path: str
    body: str
    received: float


class PageServer:
    """Serves ``tests/pages`` on any host qutebrowser maps here, and collects the reports.

    A request is served the page named by the last path component, so
    ``http://b.modes.test/app/login_single.html`` is ``login_single.html``.
    Form submissions (any other POST) are recorded and answered with a blank page.
    """

    def __init__(self) -> None:
        self.reports: dict[str, PageReport] = {}  # load id -> latest report
        self.submissions: list[Submission] = []
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                name = self.path.split("?")[0].rsplit("/", 1)[-1]
                page = PAGES_DIR / name
                if not name.endswith(".html") or not page.is_file():
                    self.send_error(404)
                    return
                html = page.read_text().replace("</body>", _REPORT_JS + "</body>")
                self._reply(html.encode())

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
                if self.path == "/__e2e/report":
                    server._report(json.loads(body))
                    self.send_response(204)
                    self.end_headers()
                    return
                with server._lock:
                    server.submissions.append(Submission(
                        self.headers.get("Host", ""), self.path, body, time.monotonic()))
                self._reply(b"<!doctype html><title>submitted</title><body></body>")

            def _reply(self, data: bytes) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def _report(self, data: dict[str, Any]) -> None:
        report = PageReport(data["load"], data["href"], data["origin"], data["fields"],
                            data["submitted"], time.monotonic())
        with self._lock:
            self.reports[report.load] = report

    def loads(self) -> set[str]:
        with self._lock:
            return set(self.reports)

    def latest(self, load: str) -> PageReport:
        with self._lock:
            return self.reports[load]

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@dataclass
class Page:
    """One page load in qutebrowser, seen through its reports."""

    server: PageServer
    load: str
    url: str

    def fields(self, *, after: float | None = None) -> dict[str, str]:
        """The page's field values, from a report that arrived after ``after`` (default: now)."""
        since = time.monotonic() if after is None else after

        def fresh() -> PageReport | None:
            report = self.server.latest(self.load)
            return report if report.received > since else None

        return wait_for(fresh, f"a report from {self.url}").fields

    def wait_fields(self, check: Callable[[dict[str, str]], bool], what: str) -> dict[str, str]:
        """Wait until the reported fields satisfy ``check``."""

        def satisfied() -> PageReport | None:
            report = self.server.latest(self.load)
            return report if check(report.fields) else None

        return wait_for(satisfied, what).fields

    def submitted(self) -> int | None:
        return self.server.latest(self.load).submitted


# --- displays -------------------------------------------------------------------------


def _tail(path: Path, lines: int = 60) -> str:
    """The last ``lines`` lines of a log file, for error messages."""
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        return f"(unreadable: {e})"
    return "\n".join(text.splitlines()[-lines:])


class Displays:
    """Headless sway (for wl-clipboard) and Xvfb (for xclip)."""

    def __init__(self, dirs: Dirs) -> None:
        self._dirs = dirs
        config = dirs.root / "sway.cfg"
        config.write_text("xwayland disable\n")  # Xvfb serves X11
        before = set(dirs.runtime.glob("wayland-*"))
        # nixpkgs' sway wrapper starts its own bus with dbus-run-session when
        # there is none, which needs /etc/dbus-1/session.conf: NixOS has it,
        # CI runners don't. Headless sway needs no bus, so point it at none.
        env = {"WLR_BACKENDS": "headless", "WLR_RENDERER": "pixman",
               "WLR_LIBINPUT_NO_DEVICES": "1",
               "DBUS_SESSION_BUS_ADDRESS": f"unix:path={dirs.runtime / 'no-bus'}"}
        log = dirs.root / "sway.log"
        with log.open("wb") as output:
            self._sway = subprocess.Popen(
                ["sway", "-c", str(config)], env=isolated_environ(dirs, env),
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)

        def socket() -> list[Path] | None:
            if self._sway.poll() is not None:
                raise HarnessError(f"sway exited with code {self._sway.returncode}")
            return [p for p in dirs.runtime.glob("wayland-*")
                    if p not in before and p.suffix != ".lock" and p.is_socket()]

        try:
            sock = wait_for(socket, "sway's Wayland socket")
        except HarnessError as e:
            stop_process(self._sway)
            raise HarnessError(f"{e}; sway's log:\n{_tail(log)}") from None
        self.wayland_display = sock[0].name
        read, write = os.pipe()
        self._xvfb = subprocess.Popen(
            ["Xvfb", "-displayfd", str(write), "-nolisten", "tcp", "-screen", "0", "640x480x24"],
            env=isolated_environ(dirs), pass_fds=(write,), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        os.close(write)
        with os.fdopen(read) as f:
            number = f.readline().strip()
        if not number:
            raise HarnessError("Xvfb didn't start")
        self.x_display = f":{number}"

    def environ(self) -> dict[str, str]:
        return {"WAYLAND_DISPLAY": self.wayland_display, "DISPLAY": self.x_display}

    def paste(self, kind: str) -> str:
        """The clipboard's text ("wayland" or "x11"); empty if it holds nothing."""
        argv = (["wl-paste", "--no-newline"] if kind == "wayland"
                else ["xclip", "-selection", "clipboard", "-o"])
        env = isolated_environ(self._dirs, self.environ())
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10,
                                stdin=subprocess.DEVNULL, check=False)
        return result.stdout if result.returncode == 0 else ""

    def wait_paste(self, kind: str, check: Callable[[str], bool], what: str,
                   timeout: float = TIMEOUT) -> str:
        """Wait until the clipboard's text satisfies ``check``; returns that text."""

        def satisfied() -> tuple[str] | None:
            text = self.paste(kind)
            return (text,) if check(text) else None

        return wait_for(satisfied, what, timeout)[0]

    def copy(self, kind: str, text: str) -> None:
        """Put non-secret ``text`` on the clipboard, as the user would."""
        argv = (["wl-copy"] if kind == "wayland" else ["xclip", "-selection", "clipboard"])
        env = isolated_environ(self._dirs, self.environ())
        proc = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, text=True,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        assert proc.stdin is not None
        proc.stdin.write(text)
        proc.stdin.close()
        wait_for(lambda: self.paste(kind) == text, f"{text!r} on the {kind} clipboard")

    def stop(self) -> None:
        stop_process(self._sway)
        stop_process(self._xvfb)


# --- qutebrowser ------------------------------------------------------------------------

# The userscript: this checkout's src/, run by the dev shell's Python. It is
# its own argv[0], so `generate`'s second stage can spawn it again. The
# variants drop display variables to pick a clipboard tool (or none).
_USERSCRIPT = """#!{python} -I
import os, sys
sys.path.insert(0, {src!r})
os.environ["PYTHONPATH"] = {src!r}  # for `python -m qutewarden.clipboard_clear`
for name in {drop!r}:
    os.environ.pop(name, None)
from qutewarden.cli import main
raise SystemExit(main())
"""
USERSCRIPTS = {"qutewarden": (), "qutewarden-x11": ("WAYLAND_DISPLAY",),
               "qutewarden-noclip": ("WAYLAND_DISPLAY", "DISPLAY")}

_FINISHED = re.compile(r"Process finished with code (-?\d+)")


@dataclass
class LogEntry:
    logger: str
    level: str
    message: str


@dataclass
class Run:
    """One userscript run (or two, for `generate`'s stages) and what it logged."""

    qb: Qutebrowser
    start: int  # index into the log where the run began
    processes: int
    exit_codes: list[int] = field(default_factory=list)
    finished_at: float = 0.0

    def wait(self, timeout: float = TIMEOUT) -> Run:
        """Wait until all its processes finished; returns self."""
        def done() -> list[int] | None:
            codes = [int(m[1]) for e in self.qb.log(self.start) if e.logger == "procs"
                     if (m := _FINISHED.search(e.message))]
            return codes if len(codes) >= self.processes else None
        self.exit_codes = wait_for(done, "the userscript to finish", timeout)
        self.finished_at = time.monotonic()
        return self

    def messages(self) -> list[tuple[str, str]]:
        """(level, text) of every message qutewarden showed since the run began."""
        return [(e.level, e.message) for e in self.qb.log(self.start)
                if e.logger == "message" and e.level != "DEBUG"
                and e.message.startswith("qutewarden: ")]

    def commands(self) -> list[str]:
        """The commands qutewarden sent through QUTE_FIFO since the run began."""
        prefix = "Got userscript command: "
        return [e.message.removeprefix(prefix) for e in self.qb.log(self.start)
                if e.message.startswith(prefix)]

    def entered_insert_mode(self) -> bool:
        return any("mode-enter insert" == c for c in self.commands())


class Qutebrowser:
    """Offscreen qutebrowser with JSON debug logging, driven over its IPC socket."""

    def __init__(self, dirs: Dirs, env: Mapping[str, str], page_port: int, *,
                 extra_settings: Sequence[tuple[str, str]] = ()) -> None:
        self.dirs = dirs
        self.basedir = dirs.basedir
        self.log_path = dirs.root / "qutebrowser.log"
        userscripts = self.basedir / "data" / "userscripts"
        userscripts.mkdir(parents=True, exist_ok=True)
        for name, drop in USERSCRIPTS.items():
            path = userscripts / name
            path.write_text(_USERSCRIPT.format(python=sys.executable, src=str(SRC_DIR),
                                               drop=drop))
            path.chmod(0o755)
        argv = ["qutebrowser", "--basedir", str(self.basedir), "--json-logging", "--debug",
                "--qt-flag", f"host-resolver-rules=MAP * 127.0.0.1:{page_port}",
                "-s", "auto_save.session", "false", "-s", "session.default_name", "e2e",
                "-s", "content.notifications.enabled", "false",
                # No GPU: Chromium aborts ("GLOzone not found") where no GL exists, as on CI.
                "-s", "qt.force_software_rendering", "chromium"]
        for key, value in extra_settings:
            argv += ["-s", key, value]
        argv.append("about:blank")
        self._entries: list[LogEntry] = []
        self._read_pos = 0
        self._partial = b""
        # The offscreen platform uses GLX when DISPLAY is set (it is, for the
        # xclip userscripts) and aborts if Xvfb has none, as on CI runners.
        qt_env = {"QT_QPA_PLATFORM": "offscreen", "QT_QPA_OFFSCREEN_NO_GLX": "1"}
        with open(self.log_path, "wb") as log:
            self._proc = subprocess.Popen(argv, env={**env, **qt_env},
                                          cwd=self.basedir, stdin=subprocess.DEVNULL,
                                          stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True)
        try:
            self.socket_path = wait_for(self._ipc_socket, "qutebrowser's IPC socket", 60)
            wait_for(lambda: self._ipc_socket() and any("Init done" in e.message
                                                        for e in self.log()),
                     "qutebrowser to finish starting", 60)
        except HarnessError as e:
            stop_process(self._proc)
            raise HarnessError(f"{e}; qutebrowser's log:\n{_tail(self.log_path)}") from None

    def _ipc_socket(self) -> Path | None:
        if self._proc.poll() is not None:
            raise HarnessError(f"qutebrowser exited with code {self._proc.returncode}")
        found = [p for p in (self.basedir / "runtime").glob("ipc-*") if p.is_socket()]
        return found[0] if found else None

    def command(self, cmd: str) -> None:
        """Run one qutebrowser command; it shows up in the log, so never put a secret in it."""
        payload = json.dumps({"args": [cmd if cmd.startswith(":") else ":" + cmd],
                              "target_arg": None, "protocol_version": 1, "cwd": str(self.basedir),
                              "version": "e2e"})
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(10)
            s.connect(str(self.socket_path))
            s.sendall(payload.encode() + b"\n")

    def log(self, start: int = 0) -> list[LogEntry]:
        """Parsed log entries from index ``start`` on."""
        with open(self.log_path, "rb") as f:
            f.seek(self._read_pos)
            data = f.read()
        self._read_pos += len(data)
        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        for line in lines:
            try:
                raw = json.loads(line)
            except ValueError:
                continue  # Chromium writes plain lines too
            if isinstance(raw, dict):
                self._entries.append(LogEntry(str(raw.get("name", "")),
                                              str(raw.get("levelname", "")),
                                              str(raw.get("message", ""))))
        return self._entries[start:]

    def mark(self) -> int:
        """The current end of the log."""
        return len(self.log())

    def open(self, server: PageServer, url: str, *, tab: bool = False) -> Page:
        """Open ``url`` (in a new tab if ``tab``) and wait until the page reports."""
        known = server.loads()
        self.command(f"open {'-t ' if tab else ''}{url}")
        load = wait_for(lambda: [ld for ld in server.loads() - known
                                 if server.latest(ld).href == url], f"{url} to load")
        return Page(server, load[0], url)

    def open_internal(self, url: str) -> None:
        """Open a page the test server doesn't serve (qute://, file://) and wait for it."""
        start = self.mark()
        self.command(f"open {url}")
        wait_for(lambda: any(f"url='{url}'>: LoadStatus.success" in e.message
                             for e in self.log(start)), f"{url} to load")

    def spawn(self, *args: str, script: str = "qutewarden", processes: int = 1) -> Run:
        """Start ``:spawn --userscript <script> <args>`` without waiting for it."""
        start = self.mark()
        self.command(" ".join(["spawn", "--userscript", script, *args]))
        return Run(self, start, processes)

    def run(self, *args: str, script: str = "qutewarden", processes: int = 1) -> Run:
        """Run the userscript and wait until it finished."""
        return self.spawn(*args, script=script, processes=processes).wait()

    def stop(self) -> None:
        if self._proc.poll() is None:
            with contextlib.suppress(OSError):
                self.command("quit")
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(15)
        stop_process(self._proc)  # by PID: the Nix wrapper renames the process


def totp_codes(seed: str) -> set[str]:
    """RFC 6238 codes (SHA-1, 6 digits, 30 s) for the previous, current and next step."""
    key = base64.b32decode(seed + "=" * (-len(seed) % 8))
    step = int(time.time()) // 30
    codes = set()
    for counter in (step - 1, step, step + 1):
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
        codes.add(f"{value % 1_000_000:06d}")
    return codes


# --- no-leak scan -------------------------------------------------------------------------


class ProcSampler:
    """Snapshots every readable ``/proc/*/cmdline`` and ``environ`` while tests run."""

    def __init__(self, interval: float = 0.02) -> None:
        self.blobs: dict[bytes, str] = {}  # snapshot -> "pid <n> <cmd> cmdline|environ"
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.sample()
            self._stop.wait(self._interval)

    def sample(self) -> None:
        uid = os.getuid()
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            with contextlib.suppress(OSError):
                if entry.stat().st_uid != uid:
                    continue
                cmdline = Path(entry.path, "cmdline").read_bytes()
                environ = Path(entry.path, "environ").read_bytes()
                name = cmdline.split(b"\0", 1)[0].decode(errors="replace")
                self.blobs.setdefault(cmdline, f"pid {entry.name} {name} cmdline")
                self.blobs.setdefault(environ, f"pid {entry.name} {name} environ")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()


def _encodings(marker: str) -> list[bytes]:
    return [marker.encode(), marker.encode("utf-16-le")]


def scan_bytes(data: bytes, markers: set[str]) -> set[str]:
    return {m for m in markers if any(enc in data for enc in _encodings(m))}


def _files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        with contextlib.suppress(OSError):
            if stat.S_ISREG(path.lstat().st_mode):
                yield path


def scan_codes(data: bytes, codes: set[str]) -> set[str]:
    """TOTP codes are only digits, so they count only as a whole number."""
    return {c for c in codes if re.search(rb"(?<![0-9])" + c.encode() + rb"(?![0-9])", data)}


def leak_scan(markers: set[str], codes: set[str], *, log: Path, basedir: Path,
              runtime_dir: Path, samples: Mapping[bytes, str]) -> list[str]:
    """Every place a marker turned up, as ``"<where>: <marker>"``; empty means no leak.

    Looks in qutebrowser's whole log, every file in its basedir, the
    ``/proc`` snapshots and qutewarden's runtime dir, which must also hold
    no leftover fill pipes. TOTP ``codes`` are looked for in the log and the
    snapshots only: a six-digit number turns up in binary files by chance.
    """
    data = log.read_bytes()
    hits = [f"qutebrowser log: {m}" for m in scan_bytes(data, markers) | scan_codes(data, codes)]
    for path in _files(basedir):
        hits += [f"{path}: {m}" for m in scan_bytes(path.read_bytes(), markers)]
    for blob, where in samples.items():
        hits += [f"/proc {where}: {m}"
                 for m in scan_bytes(blob, markers) | scan_codes(blob, codes)]
    if runtime_dir.exists():
        for path in runtime_dir.iterdir():
            if not stat.S_ISREG(path.lstat().st_mode):
                hits.append(f"{path}: left behind")
            else:
                hits += [f"{path}: {m}" for m in scan_bytes(path.read_bytes(), markers)]
    return sorted(hits)
