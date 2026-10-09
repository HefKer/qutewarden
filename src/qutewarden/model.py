"""Domain types shared by matching, backends and commands. See GLOSSARY.md."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MatchMode(StrEnum):
    BASE_DOMAIN = "base_domain"
    HOST = "host"
    STARTS_WITH = "starts_with"
    EXACT = "exact"
    REGULAR_EXPRESSION = "regular_expression"
    NEVER = "never"


@dataclass(frozen=True)
class ItemUri:
    uri: str
    mode: MatchMode | None = None  # None -> config.matching_default_mode


@dataclass(frozen=True)
class LoginItem:
    """A Login item's metadata. Never holds secrets."""

    id: str
    name: str
    username: str | None = None
    uris: tuple[ItemUri, ...] = ()
    has_totp: bool = False
    reprompt: bool = False  # Re-prompt item (info only; rbw does the prompting)


@dataclass(frozen=True)
class CardItem:
    """A Card item's metadata. Never holds secrets.

    ``brand`` and ``last4`` (the number's last 4 digits) are the only parts of
    the card that may appear in a picker line or message (Security rule 6).
    Both are None for a Re-prompt item, whose number isn't read for listing.
    """

    id: str
    name: str
    brand: str | None = None
    last4: str | None = None
    reprompt: bool = False


@dataclass(frozen=True)
class IdentityItem:
    """An Identity item's metadata: its name only, since every value is a secret."""

    id: str
    name: str
    reprompt: bool = False


class FieldKind(StrEnum):
    """A Custom field's kind, as Bitwarden names it."""

    TEXT = "text"
    HIDDEN = "hidden"
    BOOLEAN = "boolean"
    LINKED = "linked"


@dataclass(frozen=True)
class CustomField:
    """One Custom field of an Item. Its value counts as a secret (Security rule 6).

    A boolean's value is ``"true"`` or ``"false"``. A linked field's value is the
    built-in value it stands for, resolved by the Backend; None if the Item has none.
    """

    name: str
    kind: FieldKind
    value: str | None = None

    def __repr__(self) -> str:
        return f"CustomField({self.name!r}, {self.kind.value}, <redacted>)"

    __str__ = __repr__


@dataclass(frozen=True)
class ItemSecrets:
    """The values of one Item, as ``Backend.get_secrets`` returns them.

    One subclass per item type; they never show their values in ``repr``.
    ``fields`` are the Item's Custom fields, in the Vault's order.
    """

    fields: tuple[CustomField, ...] = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class LoginSecrets(ItemSecrets):
    password: str | None = None
    totp: str | None = None  # the current TOTP *code*, not the seed


@dataclass(frozen=True, repr=False)
class CardSecrets(ItemSecrets):
    """A Card item's values, as the Vault stores them (expiry not normalised)."""

    cardholder_name: str | None = None
    number: str | None = None
    brand: str | None = None
    exp_month: str | None = None
    exp_year: str | None = None
    code: str | None = None  # the security code


@dataclass(frozen=True, repr=False)
class IdentitySecrets(ItemSecrets):
    """An Identity item's values, named as rbw names them.

    Every value counts as a secret in messages (Security rule 6). ``company``
    is Bitwarden's; rbw 1.15 doesn't pass it on, so the rbw Backend leaves it None.
    """

    title: str | None = None
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    ssn: str | None = None
    license_number: str | None = None
    passport_number: str | None = None
    username: str | None = None


@dataclass(frozen=True)
class Status:
    unlocked: bool
    last_sync: datetime | None  # aware datetime, None if unknown
