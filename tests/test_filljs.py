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
