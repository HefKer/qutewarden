"""An in-memory Backend for tests. Every secret it returns contains SECRET_MARKER."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from qutewarden.backend.base import (
    Backend,
    BackendError,
    ItemNotFound,
    NotLoggedIn,
    SaveFailed,
)
from qutewarden.model import (
    CardItem,
    CardSecrets,
    CustomField,
    FieldKind,
    IdentityItem,
    IdentitySecrets,
    ItemSecrets,
    ItemUri,
    LoginItem,
    LoginSecrets,
    MatchMode,
    Status,
)

SECRET_MARKER = "QWSECRET"
FAKE_LAST_SYNC = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def fake_password(item_id: str) -> str:
    return f"QWSECRET-password-{item_id}"


def fake_totp(item_id: str) -> str:
    return f"QWSECRET-totp-{item_id}"


def fake_fields(item_id: str) -> tuple[CustomField, ...]:
    """Every fake Item's Custom fields; the text and hidden values contain SECRET_MARKER."""
    return (CustomField("recovery", FieldKind.HIDDEN, f"{SECRET_MARKER}-hidden-{item_id}"),
            CustomField("team", FieldKind.TEXT, f"{SECRET_MARKER}-text-{item_id}"),
            CustomField("remember", FieldKind.BOOLEAN, "true"))


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


FAKE_CARDS: tuple[CardItem, ...] = (
    CardItem(id="visa", name="Visa", brand="Visa", last4="4242"),
    CardItem(id="work-card", name="Work card", brand="Mastercard", last4="5454"),
    CardItem(id="reprompt-card", name="Re-prompt card", reprompt=True),
    CardItem(id="no-brand", name="No brand", last4="0005"),
    CardItem(id="bare-card", name="Bare card"),
)

_CARD_VALUES: dict[str, dict[str, str]] = {
    "visa": {"cardholder_name": "Alice Example", "number": "4242424242424242",
             "brand": "Visa", "exp_month": "3", "exp_year": "2030"},
    "work-card": {"cardholder_name": "Alice Example", "number": "5454545454545454",
                  "brand": "Mastercard", "exp_month": "11", "exp_year": "2031"},
    "reprompt-card": {"cardholder_name": "Alice Example", "number": "4000056655665556",
                    "brand": "Visa", "exp_month": "1", "exp_year": "2029"},
    "no-brand": {"number": "378282246310005"},
    "bare-card": {},
}


def fake_card(item_id: str) -> CardSecrets:
    """The Card item's values; its number and security code contain SECRET_MARKER."""
    values = dict(_CARD_VALUES[item_id])
    if "number" in values:
        values["number"] = f"{SECRET_MARKER}-{values['number']}"
        values["code"] = f"{SECRET_MARKER}-code-{item_id}"
    return CardSecrets(**values, fields=fake_fields(item_id))


FAKE_IDENTITIES: tuple[IdentityItem, ...] = (
    IdentityItem(id="me", name="Me"),
    IdentityItem(id="work-identity", name="Work identity"),
    IdentityItem(id="reprompt-identity", name="Re-prompt identity", reprompt=True),
)

_IDENTITY_VALUES: dict[str, dict[str, str]] = {
    "me": {"title": "Dr", "first_name": "Alice", "middle_name": "M", "last_name": "Example",
           "company": "Example Inc", "address1": "1 Main St", "address2": "Apt 2",
           "city": "Springfield", "state": "IL", "postal_code": "62701", "country": "US",
           "phone": "555-0100", "email": "alice@example.com", "ssn": "000-00-0000",
           "username": "alice"},
    "work-identity": {"first_name": "Alice", "last_name": "Example", "company": "Work Ltd",
                      "email": "alice@work.example"},
    "reprompt-identity": {"first_name": "Alice", "passport_number": "X1234567"},
}


def fake_identity(item_id: str) -> IdentitySecrets:
    """The Identity item's values; every one of them contains SECRET_MARKER."""
    return IdentitySecrets(**{key: f"{SECRET_MARKER}-{value}"
                              for key, value in _IDENTITY_VALUES[item_id].items()},
                           fields=fake_fields(item_id))


class FakeBackend(Backend):
    name = "fake"

    def __init__(self, items: Iterable[LoginItem] = FAKE_ITEMS, *, unlocked: bool = True,
                 logged_in: bool = True, items_after_sync: Iterable[LoginItem] | None = None,
                 fail_save: bool = False, cards: Iterable[CardItem] = FAKE_CARDS,
                 identities: Iterable[IdentityItem] = FAKE_IDENTITIES) -> None:
        self.items = list(items)
        self.cards = list(cards)
        self.identities = list(identities)
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

    def list_cards(self) -> list[CardItem]:
        self.calls.append("list_cards")
        self._require_unlocked()
        return list(self.cards)

    def list_identities(self) -> list[IdentityItem]:
        self.calls.append("list_identities")
        self._require_unlocked()
        return list(self.identities)

    def get_secrets(self, item_id: str) -> ItemSecrets:
        self.calls.append("get_secrets")
        self._require_unlocked()
        if any(card.id == item_id for card in self.cards):
            return fake_card(item_id)
        if any(identity.id == item_id for identity in self.identities):
            return fake_identity(item_id)
        item = self._item(item_id)
        return LoginSecrets(password=fake_password(item.id),
                            totp=fake_totp(item.id) if item.has_totp else None,
                            fields=fake_fields(item.id))

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
