"""Engine errors. Each carries a short code; none ever holds an input value."""

from __future__ import annotations

from typing import Any


class GuardError(Exception):
    """Base class. `code` is stable and safe to show; `hint` says how to fix it."""

    exit_code = 5

    def __init__(
        self,
        code: str,
        message: str | None = None,
        hint: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message or code
        self.hint = hint
        self.details = details or {}  # extra error fields, never a value from the input


class BadInput(GuardError):
    exit_code = 2


class StoreUnavailable(GuardError):
    exit_code = 3


class Refused(GuardError):
    exit_code = 4
