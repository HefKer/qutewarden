"""The fill JavaScript, run in headless Chromium against sample pages.

The rendered script runs in an isolated world created over CDP, like
qutebrowser's ``jseval --world``: it shares the DOM with the page but not
the page's JavaScript globals.
"""

import dataclasses
from pathlib import Path

import pytest

from qutewarden.filljs import (
    render_card_fill_js,
    render_fill_js,
    render_identity_fill_js,
    render_probe_js,
)
from qutewarden.model import CardSecrets, CustomField, FieldKind, IdentitySecrets

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


# --- Card items (#35) ---------------------------------------------------------

CARD = CardSecrets(cardholder_name="Alice M Example", number="4242424242424242", brand="Visa",
                   exp_month="3", exp_year="2030", code="QWSECRET-123")
SHIPPING_IDS = ("first", "last", "email", "phone", "promo")


def fill_card(page, card: CardSecrets = CARD, *, origin: str = ORIGIN) -> None:
    run_isolated(page, render_card_fill_js(expected_origin=origin, card=card))


def test_card_fields_are_found_by_autocomplete_with_a_single_expiry_field(page):
    load(page, "checkout.html")
    fill_card(page)
    assert values(page, "cc-name", "cc-number", "cc-exp", "cc-csc") == {
        "cc-name": "Alice M Example", "cc-number": "4242424242424242", "cc-exp": "03/30",
        "cc-csc": "QWSECRET-123"}


def test_a_card_fill_leaves_other_fields_alone_and_never_submits(page):
    load(page, "checkout.html")
    fill_card(page)
    assert values(page, *SHIPPING_IDS) == dict.fromkeys(SHIPPING_IDS, "")
    page.wait_for_timeout(100)
    assert page.evaluate("window.submitted") == 0


@pytest.mark.parametrize(("attribute", "value", "expiry"), [
    ("maxlength", "7", "03/2030"),
    ("placeholder", "MM/YYYY", "03/2030"),
    ("placeholder", "e.g. 12/2031", "03/2030"),
    ("pattern", r"\d{2}/\d{4}", "03/2030"),
    ("pattern", r"\d{2}/\d{2}", "03/30"),
])
def test_a_single_expiry_field_gets_a_4_digit_year_only_when_it_asks_for_one(
        page, attribute, value, expiry):
    load(page, "checkout.html")
    page.evaluate("""([attribute, value]) => {
        const el = document.getElementById("cc-exp");
        el.removeAttribute("maxlength");
        el.removeAttribute("placeholder");
        el.setAttribute(attribute, value);
    }""", [attribute, value])
    fill_card(page)
    assert values(page, "cc-exp") == {"cc-exp": expiry}


def test_split_card_fields_are_filled_separately(page):
    load(page, "checkout_split.html")
    fill_card(page)
    ids = ("cc-given-name", "cc-family-name", "cc-number", "cc-exp-month", "cc-exp-year",
           "cc-exp-year-4", "cc-csc", "cc-type")
    assert values(page, *ids) == {
        "cc-given-name": "Alice M", "cc-family-name": "Example", "cc-number": "4242424242424242",
        "cc-exp-month": "03", "cc-exp-year": "30", "cc-exp-year-4": "2030",
        "cc-csc": "QWSECRET-123", "cc-type": "Visa"}


def test_selects_take_the_option_whose_value_or_text_matches(page):
    load(page, "checkout_selects.html")
    fill_card(page)
    assert values(page, "cc-name", "cc-type", "cc-number", "cc-exp-month", "cc-exp-year") == {
        "cc-name": "Alice M Example", "cc-type": "VI", "cc-number": "4242424242424242",
        "cc-exp-month": "3", "cc-exp-year": "30"}
    assert ["cc-exp-month", "change"] in page.evaluate("window.events")


def test_a_select_without_a_matching_option_is_left_alone(page):
    load(page, "checkout_selects.html")
    fill_card(page, dataclasses.replace(CARD, brand="Discover", exp_year="2031"))
    assert values(page, "cc-type", "cc-exp-year", "cc-exp-month") == {
        "cc-type": "", "cc-exp-year": "", "cc-exp-month": "3"}


def test_card_fields_without_autocomplete_are_found_by_name_id_label_and_placeholder(page):
    load(page, "checkout_plain.html")
    fill_card(page)
    assert values(page, "holder", "cardnumber", "expiry", "cvc") == {
        "holder": "Alice M Example", "cardnumber": "4242424242424242", "expiry": "03/2030",
        "cvc": "QWSECRET-123"}
    assert values(page, "fname", "phone", "promo") == {"fname": "", "phone": "", "promo": ""}


def test_fields_the_card_has_no_value_for_are_left_alone(page):
    load(page, "checkout.html")
    page.fill("#cc-exp", "12/29")
    page.fill("#cc-csc", "999")
    fill_card(page, CardSecrets(number="4242424242424242", exp_month="13", exp_year="2030"))
    assert values(page, "cc-name", "cc-number", "cc-exp", "cc-csc") == {
        "cc-name": "", "cc-number": "4242424242424242", "cc-exp": "12/29", "cc-csc": "999"}


def test_the_focused_fields_form_is_the_card_fill_scope(page):
    load(page, "checkout.html")
    page.evaluate("""() => document.body.insertAdjacentHTML("afterbegin",
        '<form id="other"><input id="other-number" autocomplete="cc-number"></form>')""")
    page.focus("#cc-csc")
    fill_card(page)
    assert values(page, "other-number", "cc-number") == {
        "other-number": "", "cc-number": "4242424242424242"}


def test_a_card_fill_on_another_origin_fills_nothing(page):
    load(page, "checkout.html", origin="https://evil.example.test")
    fill_card(page)
    assert values(page, "cc-name", "cc-number", "cc-csc") == {
        "cc-name": "", "cc-number": "", "cc-csc": ""}


# Same-origin iframes (spec-v2 "Iframes")

OTHER_ORIGIN = "https://sso.other.test"


HOST_FORM = """<form><input type="text" name="login" id="host-user">
<input type="password" name="password" id="host-password"></form>"""


def load_with_frame(page, frame_url: str, *, host_form: bool = False):
    """Open a page at ORIGIN with an iframe showing login_single.html at ``frame_url``.

    With ``host_form`` the page itself also has a login form, before the iframe.
    """
    body = (PAGES / "login_single.html").read_text()
    host = (f'<!doctype html><title>Host</title>{HOST_FORM if host_form else ""}'
            f'<iframe id="frame" src="{frame_url}"></iframe>')
    for origin in (ORIGIN, OTHER_ORIGIN):
        page.route(f"{origin}/frame", lambda route: route.fulfill(
            body=body, content_type="text/html"))
    page.route(f"{ORIGIN}/", lambda route: route.fulfill(body=host, content_type="text/html"))
    page.goto(f"{ORIGIN}/")
    page.frame_locator("#frame").locator("#password").wait_for(state="attached")
    frame = page.frame(url=frame_url)
    assert frame is not None
    return frame


def frame_values(frame, *ids: str) -> dict[str, str]:
    return {i: frame.eval_on_selector(f"#{i}", "el => el.value") for i in ids}


def test_login_form_in_a_same_origin_iframe_fills(page):
    frame = load_with_frame(page, f"{ORIGIN}/frame")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert frame_values(frame, "username", "password") == {
        "username": "alice", "password": "QWSECRET-pw"}
    assert frame.evaluate("window.events") == [
        ["username", "input"], ["username", "change"],
        ["password", "input"], ["password", "change"],
    ]


@pytest.mark.parametrize("focus_frame", [False, True])
def test_focused_iframe_input_beats_the_pages_own_form(page, focus_frame):
    frame = load_with_frame(page, f"{ORIGIN}/frame", host_form=True)
    if focus_frame:
        frame.focus("#password")
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    in_frame = frame_values(frame, "username", "password")
    in_host = values(page, "host-user", "host-password")
    filled = {"username": "alice", "password": "QWSECRET-pw"}
    empty = {"username": "", "password": ""}
    assert (in_frame, list(in_host.values())) == (
        (filled, ["", ""]) if focus_frame else (empty, ["alice", "QWSECRET-pw"]))


@pytest.mark.parametrize("expected_origin", [ORIGIN, OTHER_ORIGIN])
def test_login_form_in_a_cross_origin_iframe_is_left_alone(page, expected_origin):
    frame = load_with_frame(page, f"{OTHER_ORIGIN}/frame")
    run_isolated(page, render_fill_js(
        expected_origin=expected_origin, mode="login", username="alice",
        password="QWSECRET-pw", submit=True,
    ))
    assert frame_values(frame, "username", "password") == {"username": "", "password": ""}
    assert frame.evaluate("[window.events, window.submitted]") == [[], 0]


def test_same_origin_iframe_that_navigated_elsewhere_is_left_alone(page):
    load_with_frame(page, f"{ORIGIN}/frame")
    with page.expect_event(
        "framenavigated", lambda f: f.url == f"{OTHER_ORIGIN}/frame"
    ) as navigated:
        page.eval_on_selector("#frame", f"el => {{ el.src = '{OTHER_ORIGIN}/frame'; }}")
    frame = navigated.value
    frame.wait_for_load_state()
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="login", username="alice", password="QWSECRET-pw",
    ))
    assert frame_values(frame, "username", "password") == {"username": "", "password": ""}
    assert frame.evaluate("window.events") == []


@pytest.mark.parametrize(("frame_origin", "filled"), [(ORIGIN, True), (OTHER_ORIGIN, False)])
def test_a_card_form_in_an_iframe_is_filled_only_from_the_same_origin(
        page, frame_origin, filled):
    body = (PAGES / "checkout_selects.html").read_text()
    page.route(f"{frame_origin}/frame", lambda route: route.fulfill(
        body=body, content_type="text/html"))
    page.route(f"{ORIGIN}/", lambda route: route.fulfill(
        body=f'<!doctype html><iframe id="frame" src="{frame_origin}/frame"></iframe>',
        content_type="text/html"))
    page.goto(f"{ORIGIN}/")
    page.frame_locator("#frame").locator("#cc-number").wait_for(state="attached")
    frame = page.frame(url=f"{frame_origin}/frame")
    assert frame is not None
    fill_card(page)
    expected = {"cc-number": "4242424242424242", "cc-exp-month": "3", "cc-type": "VI"}
    assert frame_values(frame, *expected) == (
        expected if filled else dict.fromkeys(expected, ""))


# --- Identity items (#36) -----------------------------------------------------

IDENTITY = IdentitySecrets(
    title="Dr", first_name="Alice", middle_name="M", last_name="Example", company="Example Inc",
    address1="1 Main St", address2="Apt 2", city="Springfield", state="IL", postal_code="62701",
    country="US", phone="555-0100", email="alice@example.com", ssn="000-00-0000",
    username="alice")
ADDRESS_IDS = ("title", "given-name", "additional-name", "family-name", "organization",
               "address-line1", "address-line2", "address-level2", "address-level1",
               "postal-code", "country", "email", "tel", "username")


def fill_identity(page, identity: IdentitySecrets = IDENTITY, *, origin: str = ORIGIN) -> None:
    run_isolated(page, render_identity_fill_js(expected_origin=origin, identity=identity))


def test_identity_fields_are_found_by_autocomplete(page):
    load(page, "address.html")
    fill_identity(page)
    assert values(page, *ADDRESS_IDS) == {
        "title": "Dr", "given-name": "Alice", "additional-name": "M", "family-name": "Example",
        "organization": "Example Inc", "address-line1": "1 Main St", "address-line2": "Apt 2",
        "address-level2": "Springfield", "address-level1": "IL", "postal-code": "62701",
        "country": "US", "email": "alice@example.com", "tel": "555-0100", "username": "alice"}
    assert ["country", "change"] in page.evaluate("window.events")


def test_an_identity_fill_leaves_other_fields_alone_and_never_submits(page):
    load(page, "address.html")
    fill_identity(page)
    assert values(page, "cc-number", "gift") == {"cc-number": "", "gift": ""}
    page.wait_for_timeout(100)
    assert page.evaluate("window.submitted") == 0


def test_a_street_address_field_gets_every_address_line(page):
    load(page, "address.html")
    page.evaluate("""() => {
        document.getElementById("address-line1").setAttribute("autocomplete", "street-address");
        document.getElementById("address-line2").remove();
    }""")
    fill_identity(page)
    assert values(page, "address-line1") == {"address-line1": "1 Main St, Apt 2"}


def test_identity_fields_without_autocomplete_are_found_by_name_id_label_and_placeholder(page):
    load(page, "address_plain.html")
    fill_identity(page, dataclasses.replace(IDENTITY, country="United States"))
    assert values(page, "fname", "lname", "org", "street", "apt", "town", "region", "zip",
                  "land", "mail", "phone") == {
        "fname": "Alice", "lname": "Example", "org": "Example Inc", "street": "1 Main St",
        "apt": "Apt 2", "town": "Springfield", "region": "IL", "zip": "62701", "land": "us",
        "mail": "alice@example.com", "phone": "555-0100"}
    assert values(page, "gift") == {"gift": ""}


def test_a_country_select_without_a_matching_option_is_left_alone(page):
    load(page, "address.html")
    fill_identity(page, dataclasses.replace(IDENTITY, country="Narnia"))
    assert values(page, "country", "postal-code") == {"country": "", "postal-code": "62701"}


def test_fields_the_identity_has_no_value_for_are_left_alone(page):
    load(page, "address.html")
    page.fill("#organization", "Typed Ltd")
    fill_identity(page, IdentitySecrets(first_name="Alice"))
    assert values(page, "given-name", "family-name", "organization", "country") == {
        "given-name": "Alice", "family-name": "", "organization": "Typed Ltd", "country": ""}


def test_the_focused_fields_form_is_the_identity_fill_scope(page):
    load(page, "address.html")
    page.evaluate("""() => document.body.insertAdjacentHTML("afterbegin",
        '<form id="other"><input id="other-email" autocomplete="email"></form>')""")
    page.focus("#postal-code")
    fill_identity(page)
    assert values(page, "other-email", "email") == {
        "other-email": "", "email": "alice@example.com"}


def test_an_identity_fill_on_another_origin_fills_nothing(page):
    load(page, "address.html", origin="https://evil.example.test")
    fill_identity(page)
    assert values(page, "given-name", "email") == {"given-name": "", "email": ""}


# --- Custom fields (#37) --------------------------------------------------------

def text(name: str, value: str) -> CustomField:
    return CustomField(name, FieldKind.TEXT, value)


def checked(page, *ids: str) -> dict[str, bool]:
    return {i: page.eval_on_selector(f"#{i}", "el => el.checked") for i in ids}


def fill_login(page, *fields: CustomField, submit: bool = False):
    run_isolated(page, render_fill_js(
        expected_origin=ORIGIN, mode="auto", username="alice", password="QWSECRET-pw",
        submit=submit, fields=fields))


def test_custom_fields_match_name_id_label_aria_label_and_placeholder(page):
    load(page, "login_custom.html")
    fill_login(page, text("team", "core"),
               CustomField("member-id", FieldKind.HIDDEN, "QWSECRET-member"),
               CustomField("  BACKUP CODE ", FieldKind.HIDDEN, "QWSECRET-backup"),
               text("customer number", "c-42"),
               CustomField("Branch", FieldKind.LINKED, "alice"))
    assert values(page, "team", "Member-ID", "backup", "customer", "branch", "other") == {
        "team": "core", "Member-ID": "QWSECRET-member", "backup": "QWSECRET-backup",
        "customer": "c-42", "branch": "alice", "other": ""}
    assert ["team", "input"] in page.evaluate("window.events")


def test_boolean_custom_fields_turn_checkboxes_and_radio_buttons_on_and_off(page):
    load(page, "login_custom.html")
    fill_login(page, CustomField("remember", FieldKind.BOOLEAN, "true"),
               CustomField("Terms", FieldKind.BOOLEAN, "false"),
               CustomField("plan-pro", FieldKind.BOOLEAN, "true"))
    assert checked(page, "remember", "terms", "plan-pro", "plan-free") == {
        "remember": True, "terms": False, "plan-pro": True, "plan-free": False}
    assert ["remember", "change"] in page.evaluate("window.events")


def test_a_custom_field_never_overrides_what_the_built_in_fill_filled(page):
    load(page, "login_custom.html")
    fill_login(page, text("login", "QWSECRET-not-the-username"),
               CustomField("Password", FieldKind.HIDDEN, "QWSECRET-not-the-password"))
    assert values(page, "username", "password") == {
        "username": "alice", "password": "QWSECRET-pw"}


def test_a_boolean_custom_field_never_sets_a_text_input_nor_text_a_checkbox(page):
    load(page, "login_custom.html")
    fill_login(page, CustomField("team", FieldKind.BOOLEAN, "true"), text("remember", "x"))
    assert values(page, "team", "remember") == {"team": "", "remember": "on"}
    assert checked(page, "remember") == {"remember": False}


def test_custom_fields_that_match_nothing_are_skipped(page):
    load(page, "login_custom.html")
    fill_login(page, text("no such field", "QWSECRET-x"), text("team", "core"))
    assert values(page, "username", "team", "other") == {
        "username": "alice", "team": "core", "other": ""}


def test_custom_fields_are_filled_before_the_form_is_submitted(page):
    load(page, "login_custom.html")
    fill_login(page, text("team", "core"), submit=True)
    page.wait_for_function("window.submitted === 1")
    assert page.evaluate("window.submittedTeam") == "core"


def test_custom_fields_fill_on_a_page_without_login_fields(page):
    load(page, "login_custom.html")
    page.evaluate("""() => { document.getElementById("username").remove();
                             document.getElementById("password").remove(); }""")
    fill_login(page, text("branch", "QWSECRET-branch"), submit=True)
    assert values(page, "branch", "team") == {"branch": "QWSECRET-branch", "team": ""}
    page.wait_for_timeout(100)
    assert page.evaluate("window.submitted") == 0  # only a built-in fill submits


def test_a_card_fill_also_fills_the_cards_custom_fields(page):
    load(page, "checkout.html")
    fill_card(page, dataclasses.replace(CARD, fields=(
        text("promo", "QWSECRET-promo"), text("cc-number", "QWSECRET-not-the-number"))))
    assert values(page, "promo", "cc-number") == {
        "promo": "QWSECRET-promo", "cc-number": "4242424242424242"}


def test_an_identity_fill_also_fills_the_identitys_custom_fields(page):
    load(page, "address.html")
    fill_identity(page, dataclasses.replace(IDENTITY, fields=(
        CustomField("Gift message", FieldKind.HIDDEN, "QWSECRET-gift"),
        text("email", "QWSECRET-not-the-email"))))
    assert values(page, "gift", "email") == {
        "gift": "QWSECRET-gift", "email": "alice@example.com"}


def test_custom_fields_on_another_origin_fill_nothing(page):
    load(page, "login_custom.html", origin="https://evil.example.test")
    fill_login(page, text("team", "core"))
    assert values(page, "team") == {"team": ""}


@pytest.mark.parametrize("focus_frame", [False, True])
def test_custom_fields_fill_only_the_document_the_built_in_fill_chose(page, focus_frame):
    frame = load_with_frame(page, f"{ORIGIN}/frame", host_form=True)
    page.evaluate("""() => document.querySelector("form").insertAdjacentHTML(
        "beforeend", '<input type="text" name="q" id="host-q">')""")
    if focus_frame:
        frame.focus("#password")
    fill_login(page, text("q", "QWSECRET-q"))
    in_frame = frame_values(frame, "q")["q"]
    in_host = values(page, "host-q")["host-q"]
    assert (in_frame, in_host) == (
        ("QWSECRET-q", "") if focus_frame else ("", "QWSECRET-q"))
