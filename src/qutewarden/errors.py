"""Exception types shared by every module.

``str(error)`` of a QutewardenError is shown to the user, so it must never
contain secrets.
"""


class QutewardenError(Exception):
    """A handled, user-facing error (shown with message-error, exit 1)."""


class UserCancelled(Exception):
    """The user dismissed a picker or prompt (exit 0, no message)."""
