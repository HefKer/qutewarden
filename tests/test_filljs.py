"""The fill JavaScript, run in headless Chromium against sample pages.

The rendered script runs in an isolated world created over CDP, like
qutebrowser's ``jseval --world``: it shares the DOM with the page but not
the page's JavaScript globals.
"""

from pathlib import Path

import pytest

from qutewarden.filljs import render_fill_js, render_probe_js

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
    assert values(page, "username", "password", "q", "hidden-text", "disabled-text", "csrf") == {
        "username": "alice", "password": "QWSECRET-pw", "q": "", "hidden-text": "",
        "disabled-text": "", "csrf": "tok",
    }


def test_focused_search_box_does_not_count_as_focus(page):
    load(page, "login_single.html")
    page.focus("#q")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
    ))
    assert values(page, "username", "password", "q") == {
        "username": "alice", "password": "QWSECRET-pw", "q": "",
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


def test_signup_fills_only_new_password_and_confirmation(page):
    # Spec `generate` step 3: without a username, only the new-password fields.
    load(page, "signup.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", password="QWSECRET-generated",
    ))
    assert values(page, "username", "email", "password", "confirm", "hidden-password") == {
        "username": "", "email": "", "password": "QWSECRET-generated",
        "confirm": "QWSECRET-generated", "hidden-password": "",
    }


def test_signup_fills_a_username_into_an_empty_username_field(page):
    # #16: a username asked for in the picker also goes into the page.
    load(page, "signup.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "username", "email", "password", "confirm", "hidden-password") == {
        "username": "alice", "email": "", "password": "QWSECRET-generated",
        "confirm": "QWSECRET-generated", "hidden-password": "",
    }


def test_signup_fills_the_username_into_the_focused_text_input(page):
    load(page, "signup.html")
    page.focus("#email")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "username", "email", "password") == {
        "username": "", "email": "alice", "password": "QWSECRET-generated",
    }


def add_newsletter_name_input(page):
    """An unrelated text input inside the signup form, focused."""
    page.evaluate("""() => {
        const input = document.createElement('input');
        input.type = 'text';
        input.name = input.id = 'newsletter_name';
        document.getElementById('signup').prepend(input);
    }""")
    page.focus("#newsletter_name")


def test_signup_ignores_a_focused_text_input_that_is_not_a_username_field(page):
    # #24: the username goes into the real username field, not the focused one.
    load(page, "signup.html")
    add_newsletter_name_input(page)
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "newsletter_name", "username", "password") == {
        "newsletter_name": "", "username": "alice", "password": "QWSECRET-generated",
    }


def test_signup_without_form_ignores_a_focused_unrelated_text_input(page):
    load(page, "signup_no_form.html")
    page.focus("#q")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "q", "username", "password", "confirm") == {
        "q": "", "username": "alice", "password": "QWSECRET-generated",
        "confirm": "QWSECRET-generated",
    }


def test_signup_without_a_username_field_fills_only_the_passwords(page):
    load(page, "signup.html")
    page.evaluate("""() => {
        for (const id of ['username', 'email']) document.getElementById(id).remove();
    }""")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "password", "confirm") == {
        "password": "QWSECRET-generated", "confirm": "QWSECRET-generated",
    }
    assert page.evaluate(
        "() => Array.from(document.querySelectorAll('input')).every("
        "el => el.type === 'password' || el.value === '')")


def test_signup_keeps_a_username_the_user_typed(page):
    load(page, "signup.html")
    page.fill("#username", "typed-by-user")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated",
    ))
    assert values(page, "username", "password") == {
        "username": "typed-by-user", "password": "QWSECRET-generated",
    }


def test_signup_without_password_fields_fills_and_submits_nothing(page):
    load(page, "signup.html")
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('input[type=password]')) el.remove();
        document.getElementById('signup').addEventListener('submit', (e) => {
            e.preventDefault();
            document.body.dataset.submitted = 'yes';
        });
    }""")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated", submit=True,
    ))
    assert values(page, "username") == {"username": ""}
    assert page.evaluate("() => document.body.dataset.submitted") is None


def test_new_password_without_autocomplete_fills_every_password_field(page):
    load(page, "signup.html")
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[autocomplete]')) {
            el.removeAttribute('autocomplete');
        }
    }""")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", password="QWSECRET-generated",
    ))
    assert values(page, "username", "password", "confirm", "hidden-password") == {
        "username": "", "password": "QWSECRET-generated",
        "confirm": "QWSECRET-generated", "hidden-password": "",
    }


def test_react_controlled_inputs_see_the_values(page):
    load(page, "react_like.html")
    # Sanity check of the emulation: a plain assignment is not seen.
    page.evaluate("""() => {
        const el = document.getElementById('username');
        el.value = 'x'; el.dispatchEvent(new Event('input', {bubbles: true})); el.value = '';
    }""")
    assert page.evaluate("window.state.username") == ""

    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
    ))
    assert page.evaluate("window.state") == {"username": "alice", "password": "QWSECRET-pw"}


ALL_TWO_FORMS = ("user-a", "pass-a", "user-b", "pass-b", "user-c", "pass-c", "user-d", "pass-d")


@pytest.mark.parametrize(("focus", "filled"), [
    (None, ("user-a", "pass-a")),             # no focus: first login form
    ("pass-b", ("user-b", "pass-b")),         # focused input's <form>
    ("user-b", ("user-b", "pass-b")),
    ("user-d", ("user-d", "pass-d")),         # no form: nearest common ancestor
    ("pass-c", ("user-c", "pass-c")),
])
def test_focused_input_decides_which_fields_get_filled(page, focus, filled):
    load(page, "login_two_forms.html")
    if focus:
        page.focus(f"#{focus}")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
    ))
    expected = {
        i: ("" if i not in filled else "alice" if i.startswith("user") else "QWSECRET-pw")
        for i in ALL_TWO_FORMS
    }
    assert values(page, *ALL_TWO_FORMS) == expected


@pytest.mark.parametrize(("submit", "submitted"), [(False, 0), (True, 1)])
def test_form_is_submitted_only_when_asked(page, submit, submitted):
    load(page, "login_single.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=submit,
    ))
    assert page.evaluate("window.submitted") == submitted


def fill_and_submit(page):
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=True,
    ))
    return page.evaluate("window.submissions")


def test_submit_sends_the_default_buttons_name_and_value(page):
    load(page, "login_single.html")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] == "submit"
    assert ["action", "signin"] in submission["data"]


def test_submit_uses_a_default_button_linked_from_outside_the_form(page):
    load(page, "login_single.html")
    page.evaluate("""() => {
        const button = document.getElementById("submit");
        button.setAttribute("form", "login");
        document.body.prepend(button);
    }""")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] == "submit"
    assert ["action", "signin"] in submission["data"]


def test_submit_uses_the_first_submit_button_in_tree_order(page):
    load(page, "login_single.html")
    page.evaluate("""() => {
        const image = document.createElement("input");
        image.type = "image";
        image.id = "image";
        image.name = "go";
        document.getElementById("login").prepend(image);
    }""")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] == "image"


def test_submit_with_a_disabled_default_button_sends_no_submitter(page):
    load(page, "login_single.html")
    page.evaluate("document.getElementById('submit').disabled = true")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] is None


def test_submit_with_a_default_button_in_a_disabled_fieldset_sends_no_submitter(page):
    load(page, "login_single.html")
    page.evaluate("""() => {
        const fieldset = document.createElement("fieldset");
        fieldset.disabled = true;
        const button = document.getElementById("submit");
        button.replaceWith(fieldset);
        fieldset.append(button);
    }""")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] is None


def test_submit_without_a_submit_button_sends_no_submitter(page):
    load(page, "login_single.html")
    page.evaluate("document.getElementById('submit').remove()")
    [submission] = fill_and_submit(page)
    assert submission["submitter"] is None
    assert ["password", "QWSECRET-pw"] in submission["data"]


def test_submit_without_form_clicks_the_submit_button(page):
    load(page, "react_like.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=True,
    ))
    assert page.evaluate("window.clicked") == 1


def test_submit_without_form_never_clicks_a_show_password_toggle(page):
    load(page, "login_toggle.html")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=True,
    ))
    assert page.evaluate("window.clicks") == ["submit"]


def test_submit_without_form_or_safe_button_clicks_nothing(page):
    load(page, "login_toggle.html")
    page.evaluate("document.getElementById('submit').remove()")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=True,
    ))
    assert page.evaluate("window.clicks") == []
    assert values(page, "username", "password") == {
        "username": "alice", "password": "QWSECRET-pw"}


PROBE_ATTR ="data-qutewarden-probe-0123abcd"


def probe_attr(page):
    return page.evaluate(f"document.documentElement.getAttribute('{PROBE_ATTR}')")


def test_probe_writes_the_username_into_a_page_attribute(page):
    load(page, "signup.html")
    page.fill("#username", "alice")
    page.fill("#password", "typed-password")
    run_isolated(page, render_probe_js(expected_origin=ORIGIN, nonce="0123abcd"))
    assert probe_attr(page) == "alice"


def test_probe_ignores_a_focused_text_input_that_is_not_a_username_field(page):
    load(page, "signup.html")
    page.fill("#username", "alice")
    add_newsletter_name_input(page)
    page.fill("#newsletter_name", "Alice Liddell")
    run_isolated(page, render_probe_js(expected_origin=ORIGIN, nonce="0123abcd"))
    assert probe_attr(page) == "alice"


def test_probe_on_other_origin_writes_nothing(page):
    load(page, "signup.html", origin="https://evil.example.test")
    page.fill("#username", "alice")
    run_isolated(page, render_probe_js(expected_origin=ORIGIN, nonce="0123abcd"))
    assert probe_attr(page) is None


def test_new_password_fill_removes_the_probe_attribute(page):
    load(page, "signup.html")
    page.evaluate(f"document.documentElement.setAttribute('{PROBE_ATTR}', 'alice')")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="new_password", username="alice",
        password="QWSECRET-generated", probe_nonce="0123abcd",
    ))
    assert probe_attr(page) is None
    assert values(page, "password") == {"password": "QWSECRET-generated"}


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
