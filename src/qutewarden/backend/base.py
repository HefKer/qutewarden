"""The Backend interface: how qutewarden talks to a Vault.

Nothing here is specific to rbw; a ``bw`` Backend can implement the same calls.
Secrets only ever cross this interface as return values of ``get_secrets`` and
arguments of ``create_login``/``update_password``. Implementations pass them to
and from their child process through stdin/stdout only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from qutewarden.errors import QutewardenError
from qutewarden.model import LoginItem, Secrets, Status


class BackendError(QutewardenError):
    """A Backend failure. ``str(e)`` is user-facing and never contains secrets."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:
        return f"{self.message} ({self.hint})" if self.hint else self.message


class BackendUnavailable(BackendError):
    """The Backend program is missing or too old."""


class NotLoggedIn(BackendError):
    """The Backend has no account configured / logged in."""


class UnlockFailed(BackendError):
    """Wrong master password, or the password prompt was cancelled."""


class ItemNotFound(BackendError):
    """No Item with that id."""


class SaveFailed(BackendError):
    """create_login/update_password failed; callers must not Fill."""


class Backend(ABC):
    name: ClassVar[str]

    @abstractmethod
    def is_unlocked(self) -> bool: ...

    @abstractmethod
    def unlock(self) -> None:
        """Unlock the Vault; asking for the master password is the Backend's job."""

    @abstractmethod
    def lock(self) -> None: ...

    @abstractmethod
    def sync(self) -> None: ...

    @abstractmethod
    def status(self) -> Status: ...

    @abstractmethod
    def list_logins(self) -> list[LoginItem]:
        """Every Login item, without secrets."""

    @abstractmethod
    def get_secrets(self, item_id: str) -> Secrets:
        """The Item's password and current TOTP code (None if it has no TOTP)."""

    @abstractmethod
    def create_login(self, *, name: str, username: str | None, uri: str,
                     password: str) -> None: ...

    @abstractmethod
    def update_password(self, item_id: str, password: str) -> None:
        """Replace the Item's password; the old one goes to its password history."""
