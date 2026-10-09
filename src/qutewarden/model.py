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
class ItemSecrets:
    """The values of one Item, as ``Backend.get_secrets`` returns them.

    One subclass per item type; they never show their values in ``repr``.
    """

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


@dataclass(frozen=True)
class Status:
    unlocked: bool
    last_sync: datetime | None  # aware datetime, None if unknown
