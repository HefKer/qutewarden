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
class Secrets:
    password: str | None = None
    totp: str | None = None  # the current TOTP *code*, not the seed

    def __repr__(self) -> str:
        return "Secrets(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True)
class Status:
    unlocked: bool
    last_sync: datetime | None  # aware datetime, None if unknown
