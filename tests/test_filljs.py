"""The fill JavaScript, run in headless Chromium against sample pages.

The rendered script runs in an isolated world created over CDP, like
qutebrowser's ``jseval --world``: it shares the DOM with the page but not
the page's JavaScript globals.
"""

from pathlib import Path

import pytest

from qutewarden.filljs import render_fill_js

pytestmark = pytest.mark.browser
sync_api = pytest.importorskip("playwright.sync_api")

PAGES = Path(__file__).parent / "pages"
ORIGIN = "https://login.example.test"


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()


def load(page, name: str, *, origin: str = ORIGIN):
    """Serve tests/pages/<name> at <origin>/ and open it."""
    body = (PAGES / name).read_text()
    page.route(f"{origin}/**", lambda route: route.fulfill(body=body, content_type="text/html"))
    page.goto(f"{origin}/")


def run_isolated(page, js: str):
    """Evaluate ``js`` in a fresh isolated world of the page's main frame."""
    cdp = page.context.new_cdp_session(page)
    frame_id = cdp.send("Page.getFrameTree")["frameTree"]["frame"]["id"]
    ctx_id = cdp.send(
        "Page.createIsolatedWorld", {"frameId": frame_id, "worldName": "qutewarden"}
    )["executionContextId"]
    result = cdp.send(
        "Runtime.evaluate", {"expression": js, "contextId": ctx_id, "returnByValue": True}
    )
    assert "exceptionDetails" not in result, result["exceptionDetails"]
    return result["result"]


def values(page, *ids: str) -> dict[str, str]:
    return {i: page.eval_on_selector(f"#{i}", "el => el.value") for i in ids}


def test_single_step_login_fills_username_and_password(page):
    load(page, "login_single.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert values(page, "username", "password", "q", "hidden-text", "csrf") == {
        "username": "alice", "password": "QWSECRET-pw", "q": "", "hidden-text": "", "csrf": "tok",
    }


def test_fires_bubbling_input_and_change_events(page):
    load(page, "login_single.html")
    page.evaluate("""() => {
        window.bubbled = [];
        for (const t of ["input", "change"]) {
            document.addEventListener(t, (e) => window.bubbled.push([e.target.id, e.type]));
        }
    }""")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert page.evaluate("window.bubbled") == [
        ["username", "input"], ["username", "change"],
        ["password", "input"], ["password", "change"],
    ]


def test_script_returns_nothing(page):
    load(page, "login_single.html")
    result = run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert result == {"type": "undefined"}


@pytest.mark.parametrize("mode", ["auto", "login"])
def test_two_step_login_fills_what_each_page_has(page, mode):
    js = render_fill_js(
        expected_origin=ORIGIN, mode=mode, username="alice@example.test",
        password="QWSECRET-pw", totp="123456",
    )
    load(page, "login_two_step_1.html")
    run_isolated(page, js)
    assert values(page, "username") == {"username": "alice@example.test"}

    load(page, "login_two_step_2.html")
    run_isolated(page, js)
    assert values(page, "identifier", "shown", "password") == {
        "identifier": "alice@example.test", "shown": "alice@example.test",
        "password": "QWSECRET-pw",
    }


@pytest.mark.parametrize("mode", ["auto", "otp"])
def test_otp_page_gets_the_totp_code(page, mode):
    load(page, "otp.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode=mode, username="alice", password="QWSECRET-pw",
        totp="123456",
    ))
    assert values(page, "otp", "q") == {"otp": "123456", "q": ""}


def test_otp_field_found_by_name_without_autocomplete(page):
    load(page, "otp.html")
    page.evaluate("document.getElementById('otp').removeAttribute('autocomplete')")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        totp="123456",
    ))
    assert values(page, "otp", "q") == {"otp": "123456", "q": ""}


def test_otp_page_without_totp_code_fills_nothing(page):
    load(page, "otp.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
    ))
    assert values(page, "otp", "q") == {"otp": "", "q": ""}


def test_login_page_in_auto_mode_does_not_get_the_totp_code(page):
    load(page, "login_single.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        totp="123456",
    ))
    assert values(page, "username", "password", "q") == {
        "username": "alice", "password": "QWSECRET-pw", "q": "",
    }


@pytest.mark.parametrize("served_at", [
    "https://evil.example.test",
    "http://login.example.test",          # same host, other scheme
    "https://login.example.test:8443",    # same host, other port
])
def test_origin_mismatch_fills_nothing(page, served_at):
    load(page, "login_single.html", origin=served_at)
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert values(page, "username", "password") == {"username": "", "password": ""}
    assert page.evaluate("window.events") == []
