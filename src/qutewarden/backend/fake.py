"""An in-memory Backend for tests. Every secret it returns contains SECRET_MARKER."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from qutewarden.backend.base import (Backend, BackendError, ItemNotFound, NotLoggedIn,
                                     SaveFailed)
from qutewarden.model import ItemUri, LoginItem, MatchMode, Secrets, Status

SECRET_MARKER = "QWSECRET"
FAKE_LAST_SYNC = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def fake_password(item_id: str) -> str:
    return f"QWSECRET-password-{item_id}"


def fake_totp(item_id: str) -> str:
    return f"QWSECRET-totp-{item_id}"


FAKE_ITEMS: tuple[LoginItem, ...] = (
    LoginItem(id="github", name="GitHub", username="alice",
              uris=(ItemUri("https://github.com/login"),), has_totp=True),
    LoginItem(id="github-alt", name="GitHub (work)", username="alice-work",
              uris=(ItemUri("github.com", MatchMode.BASE_DOMAIN),), has_totp=True),
    LoginItem(id="example", name="Example", username="bob",
              uris=(ItemUri("https://example.com"),), has_totp=True),
    LoginItem(id="no-totp", name="No TOTP", username="carol",
              uris=(ItemUri("https://no-totp.test"),)),
    LoginItem(id="never", name="Never", username="dave",
              uris=(ItemUri("https://github.com/login", MatchMode.NEVER),)),
    LoginItem(id="elsewhere", name="Elsewhere", username="erin",
              uris=(ItemUri("https://other.test"),)),
)


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, items: Iterable[LoginItem] = FAKE_ITEMS, *, unlocked: bool = True,
                 logged_in: bool = True, items_after_sync: Iterable[LoginItem] | None = None,
                 fail_save: bool = False) -> None:
        self.items = list(items)
        self.unlocked = unlocked
        self.logged_in = logged_in
        self.items_after_sync = None if items_after_sync is None else list(items_after_sync)
        self.fail_save = fail_save
        self.calls: list[str] = []
        self.created: list[dict] = []
        self.updated: list[tuple[str, str]] = []

    def is_unlocked(self) -> bool:
        self.calls.append("is_unlocked")
        return self.unlocked

    def unlock(self) -> None:
        self.calls.append("unlock")
        self._require_login()
        self.unlocked = True

    def lock(self) -> None:
        self.calls.append("lock")
        self.unlocked = False

    def sync(self) -> None:
        self.calls.append("sync")
        self._require_login()
        if self.items_after_sync is not None:
            self.items = list(self.items_after_sync)

    def status(self) -> Status:
        self.calls.append("status")
        return Status(unlocked=self.unlocked, last_sync=FAKE_LAST_SYNC if self.logged_in else None)

    def list_logins(self) -> list[LoginItem]:
        self.calls.append("list_logins")
        self._require_unlocked()
        return list(self.items)

    def get_secrets(self, item_id: str) -> Secrets:
        self.calls.append("get_secrets")
        item = self._item(item_id)
        return Secrets(password=fake_password(item.id),
                       totp=fake_totp(item.id) if item.has_totp else None)

    def create_login(self, *, name: str, username: str | None, uri: str,
                     password: str) -> None:
        self.calls.append("create_login")
        self._require_unlocked()
        if self.fail_save:
            raise SaveFailed("fake backend refused to save")
        self.created.append({"name": name, "username": username, "uri": uri,
                             "password": password})
        self.items.append(LoginItem(id=f"created-{len(self.created)}", name=name,
                                    username=username, uris=(ItemUri(uri),)))

    def update_password(self, item_id: str, password: str) -> None:
        self.calls.append("update_password")
        self._item(item_id)
        if self.fail_save:
            raise SaveFailed("fake backend refused to save")
        self.updated.append((item_id, password))

    def _require_login(self) -> None:
        if not self.logged_in:
            raise NotLoggedIn("not logged in", hint="log in to the fake backend")

    def _require_unlocked(self) -> None:
        self._require_login()
        if not self.unlocked:
            raise BackendError("vault is locked")

    def _item(self, item_id: str) -> LoginItem:
        self._require_unlocked()
        for item in self.items:
            if item.id == item_id:
                return item
        raise ItemNotFound(f"no item with id {item_id}")
