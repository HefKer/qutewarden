"""The Items seeded into the e2e Vault, each secret carrying a unique marker.

Every secret value (password, TOTP secret, notes, custom field value, card
and identity numbers) and the master password contain ``Markers.prefix``, a
random string per session, so the no-leak scan can look for all of them.
Tests refer to Items by the constants below. Domains map to the test page
server (``harness.PageServer``); ``.test`` and ``example.*`` hosts avoid
HSTS-preloaded TLDs, so plain http works.
"""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass, field
from typing import Any

from e2e.seed import VaultClient

# Bitwarden's UriMatchType
BASE_DOMAIN, HOST, STARTS_WITH, EXACT, REGULAR_EXPRESSION, NEVER = range(6)
# Bitwarden's FieldType
TEXT, HIDDEN, BOOLEAN, LINKED = range(4)
LINKED_USERNAME, LINKED_PASSWORD = 100, 101


class Markers:
    """Secret values for one session; ``all()`` is what the no-leak scan looks for."""

    def __init__(self) -> None:
        self.prefix = "QWE2E" + secrets.token_hex(6).upper()
        self._issued: set[str] = set()
        self._codes: set[str] = set()

    def secret(self, tag: str) -> str:
        value = f"{self.prefix}-{tag}"
        self._issued.add(value)
        return value

    def totp_seed(self, tag: str) -> str:
        """A base32 TOTP secret that is itself a marker."""
        value = base64.b32encode(self.secret(tag).encode()).decode().rstrip("=")
        self._issued.add(value)
        return value

    def add(self, value: str) -> None:
        """Watch a secret made during the run (e.g. a generated password)."""
        self._issued.add(value)

    def add_code(self, code: str) -> None:
        """Watch a TOTP code that was filled or copied."""
        self._codes.add(code)

    def all(self) -> set[str]:
        return set(self._issued)

    def codes(self) -> set[str]:
        return set(self._codes)


@dataclass(frozen=True)
class Uri:
    uri: str
    match: int | None = None


@dataclass(frozen=True)
class Field:
    name: str
    value: str | None
    type: int
    linked_id: int | None = None


@dataclass
class Login:
    name: str
    username: str | None
    password: str
    uris: tuple[Uri, ...]
    totp: str | None = None
    notes: str | None = None
    fields: tuple[Field, ...] = ()
    reprompt: bool = False
    id: str = ""

    @property
    def line(self) -> str:
        """How the picker shows this Item."""
        return f"{self.name} — {self.username}" if self.username else self.name


@dataclass
class Card:
    name: str
    cardholder: str
    brand: str
    number: str  # a marker ending in 4 digits, so the picker line has a "last 4"
    exp_month: str
    exp_year: str
    code: str
    reprompt: bool = False
    id: str = ""

    @property
    def line(self) -> str:
        """How the picker shows this Item: brand and last 4 digits, unless Re-prompt."""
        return self.name if self.reprompt else f"{self.name} — {self.brand} *{self.number[-4:]}"


@dataclass
class SeededVault:
    """The seeded Items, by role."""

    a: Login  # login.example.com, default mode, TOTP, notes, every custom field kind
    b: Login  # example.com, base domain: A's second Candidate
    c_never: Login  # login.example.com with match mode never
    single: Login  # the only Candidate on single.test, no TOTP
    host: Login  # a.modes.test, host
    starts_with: Login  # http://b.modes.test/app/, starts with
    exact: Login  # http://c.modes.test/login_single.html, exact
    regex: Login  # ^http://d[0-9]\.modes\.test/, regular expression
    reprompt: Login  # reprompt.test, Re-prompt item
    replace: Login  # replace.test: `generate` replaces its password
    two_1: Login  # twocands.test, with two_2: `generate` offers both and a new Item
    two_2: Login
    card: Card  # Visa, filled by `card`
    card_reprompt: Card  # a Re-prompt Card item: listed by name only
    others: list[str] = field(default_factory=list)  # names of the Card and Identity items

    def logins(self) -> list[Login]:
        return [v for v in vars(self).values() if isinstance(v, Login)]

    def cards(self) -> list[Card]:
        return [v for v in vars(self).values() if isinstance(v, Card)]


def build(markers: Markers) -> SeededVault:
    s = markers.secret
    return SeededVault(
        a=Login("Example A", "alice", s("pw-a"), (Uri("https://login.example.com/"),),
                totp=markers.totp_seed("totp-a"), notes=s("notes-a"),
                fields=(Field("question", s("field-text"), TEXT),
                        Field("pin", s("field-hidden"), HIDDEN),
                        Field("remember", "true", BOOLEAN),
                        Field("account", None, LINKED, LINKED_USERNAME))),
        b=Login("Example B", "bob", s("pw-b"), (Uri("example.com", BASE_DOMAIN),)),
        c_never=Login("Example C", "carol", s("pw-c"),
                      (Uri("https://login.example.com", NEVER),)),
        single=Login("Single S", "sam", s("pw-single"), (Uri("https://single.test"),)),
        host=Login("Mode host", "hal", s("pw-host"), (Uri("a.modes.test", HOST),)),
        starts_with=Login("Mode starts", "sue", s("pw-starts"),
                          (Uri("http://b.modes.test/app/", STARTS_WITH),)),
        exact=Login("Mode exact", "eve", s("pw-exact"),
                    (Uri("http://c.modes.test/login_single.html", EXACT),)),
        regex=Login("Mode regex", "rex", s("pw-regex"),
                    (Uri(r"^http://d[0-9]\.modes\.test/", REGULAR_EXPRESSION),)),
        reprompt=Login("Reprompt R", "rita", s("pw-reprompt"), (Uri("https://reprompt.test"),),
                       reprompt=True),
        replace=Login("Replace Z", "zoe", s("pw-replace"), (Uri("https://replace.test"),),
                      notes=s("notes-replace")),
        two_1=Login("Two Y1", "yuri", s("pw-two-1"), (Uri("https://twocands.test"),)),
        two_2=Login("Two Y2", "yara", s("pw-two-2"), (Uri("https://twocands.test"),)),
        card=Card("Card C", "Al Ice", "Visa", s("card-number-4242"), "1", "2030",
                  s("card-code")),
        card_reprompt=Card("Card R", "Al Ice", "Mastercard", s("card-number-5454"), "12", "2031",
                           s("card-code-r"), reprompt=True),
    )


def seed(client: VaultClient, vault: SeededVault, markers: Markers) -> None:
    """Create every Item of ``vault`` (and a Card and an Identity) on the server."""
    for login in vault.logins():
        login.id = client.create_item(_login_body(client, login))
    e = client.encrypt
    s = markers.secret
    for card in vault.cards():
        card.id = client.create_item({
            "type": 3, "name": e(card.name), "reprompt": 1 if card.reprompt else 0,
            "notes": e(s(f"notes-{card.name}")),
            "card": {"cardholderName": e(card.cardholder), "brand": e(card.brand),
                     "number": e(card.number), "expMonth": e(card.exp_month),
                     "expYear": e(card.exp_year), "code": e(card.code)}})
        vault.others.append(card.name)
    identity = {"type": 4, "name": e("Ident I"), "reprompt": 0,
                "identity": {"firstName": e("Al"), "lastName": e("Ice"),
                             "email": e("al@example.com"), "ssn": e(s("identity-ssn")),
                             "passportNumber": e(s("identity-passport"))}}
    client.create_item(identity)
    vault.others.append("Ident I")


def _login_body(client: VaultClient, login: Login) -> dict[str, Any]:
    e = client.encrypt
    return {
        "type": 1, "name": e(login.name), "notes": e(login.notes),
        "reprompt": 1 if login.reprompt else 0,
        "login": {"username": e(login.username), "password": e(login.password),
                  "totp": e(login.totp),
                  "uris": [{"uri": e(u.uri), "match": u.match} for u in login.uris]},
        "fields": [{"name": e(f.name), "value": e(f.value), "type": f.type,
                    "linkedId": f.linked_id} for f in login.fields],
    }
