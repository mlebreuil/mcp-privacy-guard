"""Name stand-ins: one `n-<token>` per real name, whatever its kind (FR-009)."""

from __future__ import annotations

import base64
import hmac
from collections.abc import Callable

NAME_TOKEN = 6


def token(key: bytes, domain: str, value: str, n: int, attempt: int = 0) -> str:
    """t(n): the first n characters of lower-case, unpadded base32 of the keyed digest."""
    msg = f"{domain}\x1f{value}\x1f{attempt}".encode()
    digest = hmac.digest(key, msg, "sha256")
    return base64.b32encode(digest).decode().lower().rstrip("=")[:n]


def make(key: bytes, real: str, is_taken: Callable[[str], bool]) -> tuple[str, int]:
    """The stand-in of a name and the attempt that produced it.

    On a collision with another real's token the attempt goes up by one and the token grows
    by two characters.
    """
    attempt, size = 0, NAME_TOKEN
    while True:
        tok = token(key, "name", real, size, attempt)
        if not is_taken(tok):
            return f"n-{tok}", attempt
        attempt += 1
        size += 2
