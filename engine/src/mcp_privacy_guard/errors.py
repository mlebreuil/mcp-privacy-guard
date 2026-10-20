"""Engine errors. Each carries a short code; none ever holds an input value."""

from __future__ import annotations


class GuardError(Exception):
    """Base class. `code` is stable and safe to show; `hint` says how to fix it."""

    exit_code = 5

    def __init__(self, code: str, message: str | None = None, hint: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.message = message or code
        self.hint = hint


class BadInput(GuardError):
    exit_code = 2


class StoreUnavailable(GuardError):
    exit_code = 3


class Refused(GuardError):
    exit_code = 4
