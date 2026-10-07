"""The fake Backend: what command tests rely on."""

import pytest

from qutewarden.backend.base import (Backend, BackendError, ItemNotFound, NotLoggedIn,
                                     SaveFailed)
from qutewarden.backend.fake import (FAKE_ITEMS, SECRET_MARKER, FakeBackend, fake_password,
                                     fake_totp)
from qutewarden.model import LoginItem, MatchMode, Secrets, Status


def test_fake_is_a_backend_named_fake():
    backend = FakeBackend()
    assert isinstance(backend, Backend)
    assert backend.name == "fake"


def test_fake_secrets_are_known_placeholders_containing_the_marker():
    assert fake_password("github") == "QWSECRET-password-github"
    assert fake_totp("github") == "QWSECRET-totp-github"
    assert SECRET_MARKER == "QWSECRET"


def test_default_items_cover_the_cases_commands_need():
    by_id = {item.id: item for item in FAKE_ITEMS}
    assert {"github", "github-alt", "example", "no-totp", "never", "elsewhere"} <= set(by_id)
    assert all(SECRET_MARKER not in repr(item) for item in FAKE_ITEMS)
    assert by_id["never"].uris[0].mode is MatchMode.NEVER
    assert not by_id["no-totp"].has_totp
    assert by_id["github"].has_totp


@pytest.mark.parametrize("page_url, expected", [
    ("https://github.com/login", ["github", "github-alt"]),
    ("https://example.com/", ["example"]),
    ("https://other.test/", ["elsewhere"]),
])
def test_default_items_give_the_documented_candidates(tmp_path, page_url, expected):
    from qutewarden.match import candidates, make_suffix_extractor
    found = candidates(FAKE_ITEMS, page_url, default_mode=MatchMode.BASE_DOMAIN,
                       extractor=make_suffix_extractor(tmp_path, offline=True))
    assert [item.id for item in found] == expected


def test_list_logins_returns_items_without_secrets():
    assert FakeBackend().list_logins() == list(FAKE_ITEMS)


def test_get_secrets_returns_password_and_totp_code():
    secrets = FakeBackend().get_secrets("github")
    assert secrets == Secrets(password=fake_password("github"), totp=fake_totp("github"))


def test_get_secrets_without_totp_and_unknown_item():
    backend = FakeBackend()
    assert backend.get_secrets("no-totp").totp is None
    with pytest.raises(ItemNotFound):
        backend.get_secrets("missing")


def test_locked_fake_must_be_unlocked_before_reading():
    backend = FakeBackend(unlocked=False)
    assert not backend.is_unlocked()
    with pytest.raises(BackendError):
        backend.list_logins()
    backend.unlock()
    assert backend.is_unlocked()
    assert backend.list_logins()
    backend.lock()
    assert not backend.is_unlocked()


def test_not_logged_in_fake_fails_with_a_hint():
    backend = FakeBackend(unlocked=False, logged_in=False)
    with pytest.raises(NotLoggedIn) as excinfo:
        backend.unlock()
    assert excinfo.value.hint


def test_sync_switches_to_items_after_sync():
    later = (LoginItem(id="new", name="New"),)
    backend = FakeBackend(items_after_sync=later)
    backend.sync()
    assert backend.list_logins() == list(later)


def test_status_reports_lock_state():
    status = FakeBackend(unlocked=False).status()
    assert isinstance(status, Status)
    assert status.unlocked is False


def test_calls_are_recorded_in_order():
    backend = FakeBackend(unlocked=False)
    backend.is_unlocked()
    backend.unlock()
    backend.sync()
    backend.list_logins()
    backend.get_secrets("github")
    assert backend.calls == ["is_unlocked", "unlock", "sync", "list_logins", "get_secrets"]


def test_create_login_and_update_password_are_recorded_in_memory():
    backend = FakeBackend()
    backend.create_login(name="Site", username="alice", uri="https://site.test",
                         password="QWSECRET-generated")
    backend.update_password("github", "QWSECRET-new")
    assert backend.created == [{"name": "Site", "username": "alice", "uri": "https://site.test",
                                "password": "QWSECRET-generated"}]
    assert backend.updated == [("github", "QWSECRET-new")]
    assert backend.calls[-2:] == ["create_login", "update_password"]
    assert any(item.name == "Site" for item in backend.list_logins())


def test_fail_save_raises_save_failed():
    backend = FakeBackend(fail_save=True)
    with pytest.raises(SaveFailed):
        backend.create_login(name="Site", username=None, uri="https://site.test", password="x")
    with pytest.raises(SaveFailed):
        backend.update_password("github", "x")
    assert backend.created == [] and backend.updated == []


def test_backend_errors_carry_an_optional_hint():
    assert BackendError("boom").hint is None
    assert BackendError("boom", hint="run `rbw sync`").hint == "run `rbw sync`"
    assert str(BackendError("boom")) == "boom"
    assert str(BackendError("boom", hint="run `rbw sync`")) == "boom (run `rbw sync`)"
