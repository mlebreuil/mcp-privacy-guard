"""Shape detection: what kind of identifying value a string is, whole or embedded in text."""

from __future__ import annotations

import ipaddress as ia
import re
from collections.abc import Sequence

from mcp_privacy_guard import suffix

LABEL = r"[A-Za-z0-9_](?:[A-Za-z0-9_-]*[A-Za-z0-9_])?"

_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s<>\"'`]+")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@(?:" + LABEL + r"\.)+[A-Za-z]{2,}")
_MAC = re.compile(
    r"(?<![0-9A-Fa-f:\-])(?:[0-9A-Fa-f]{2}([:\-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}"
    r"|[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})(?![0-9A-Fa-f:\-])"
)
_USER = re.compile(r"(?<![\w\\])[A-Za-z0-9][A-Za-z0-9._-]*\\[A-Za-z0-9][A-Za-z0-9._$-]*")
_V4 = r"\d{1,3}(?:\.\d{1,3}){3}"
_IPV4 = re.compile(
    rf"(?<![\w.]){_V4}(?:-{_V4}|/\d{{1,2}})?(?![\w]|\.\d)"
    r"|(?<![\w.])\d{1,3}(?:\.\d{1,3}){0,2}(?:\.\*)+(?![\w*])"
)
_IPV6 = re.compile(r"(?<![\w:.])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?:/\d{1,3})?(?![\w:])")
_FQDN = re.compile(r"(?<![\w.@\-])(?:" + LABEL + r"\.)+[A-Za-z][A-Za-z0-9-]*(?![\w\-]|\.\w)")
_DIGITS = re.compile(r"(?<![\w.])\d{7,}(?![\w])")

_WHOLE_FQDN = re.compile(r"^(?:" + LABEL + r"\.)+[A-Za-z][A-Za-z0-9-]*$")

# the priority breaks ties between spans of the same length
_KINDS = ("URL", "EMAIL", "MAC", "USER", "IP", "FQDN", "DIGITS")

_SAFE = [
    re.compile(p)
    for p in (
        r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$",
        r"^\d{4}/\d{2}/\d{2}(?: \d{2}:\d{2}(?::\d{2})?)?$",
        r"^P(?=\d|T)(?:\d+[YMWD])*(?:T(?:\d+[HMS])+)?$",
        r"^(?:\d+[smhdw])+$",
        r"^\d{1,2}:\d{2}(?::\d{2})?$",
        r"^\d{1,6}$",
        r"^\d+\.\d+(?:\.\d+)?(?:-h\d+)?$",  # versions: 11.1, 10.2.10-h3
        r"^\d+-\d+$",  # content versions: 8912-9301
    )
]


def _valid_ipv4(text: str) -> bool:
    return all(p.isdigit() and int(p) <= 255 and str(int(p)) == p for p in text.split("."))


def _ip_address_ok(text: str) -> bool:
    try:
        ia.ip_address(text)
    except ValueError:
        return False
    return True


def _is_ip(text: str) -> bool:
    if "-" in text:
        head, _, tail = text.partition("-")
        return _ip_address_ok(head) and _ip_address_ok(tail) and (":" in head) == (":" in tail)
    if "/" in text:
        head, _, tail = text.partition("/")
        if not (tail.isdigit() and _ip_address_ok(head)):
            return False
        return int(tail) <= (128 if ":" in head else 32)
    if "*" in text:
        parts = text.split(".")
        known = [p for p in parts if p != "*"]
        return (
            len(parts) == 4
            and 0 < len(known) < 4
            and parts[: len(known)] == known
            and _valid_ipv4(".".join(known))
        )
    return _ip_address_ok(text)


def _is_fqdn(text: str) -> bool:
    return bool(_WHOLE_FQDN.match(text)) and suffix.split_host(text) is not None


def classify_whole(text: str) -> str | None:
    """The identifying kind of a whole value, or None when its shape says nothing."""
    if _URL.fullmatch(text):
        return "URL"
    if _EMAIL.fullmatch(text):
        return "EMAIL"
    if _MAC.fullmatch(text):
        return "MAC"
    if _USER.fullmatch(text):
        return "USER"
    if _is_ip(text):
        return "IP"
    if _is_fqdn(text):
        return "FQDN"
    if text.isascii() and text.isdigit() and len(text) >= 7:
        return "DIGITS"
    return None


def _candidates(
    text: str, extra: Sequence[tuple[re.Pattern[str], str]] = ()
) -> list[tuple[int, int, str]]:
    found: list[tuple[int, int, str]] = []
    patterns = {
        "URL": [_URL],
        "EMAIL": [_EMAIL],
        "MAC": [_MAC],
        "USER": [_USER],
        "IP": [_IPV4, _IPV6],
        "FQDN": [_FQDN],
        "DIGITS": [_DIGITS],
    }
    for kind in _KINDS:
        for pattern in patterns[kind]:
            for match in pattern.finditer(text):
                span = match.group(0).rstrip(".,;:)")
                if not span:
                    continue
                if kind == "IP" and not _is_ip(span):
                    continue
                if kind == "FQDN" and not _is_fqdn(span):
                    continue
                found.append((match.start(), match.start() + len(span), kind))
    for pattern, kind in extra:
        found.extend((m.start(), m.end(), kind) for m in pattern.finditer(text))
    return found


def find_embedded(
    text: str, extra: Sequence[tuple[re.Pattern[str], str]] = ()
) -> list[tuple[int, int, str]]:
    """Non-overlapping (start, end, kind) spans of identifying shapes inside free text.

    `extra` adds caller patterns (for example the stand-in tokens) as further candidates.
    """
    order = {kind: i for i, kind in enumerate(_KINDS)}
    ranked = sorted(
        _candidates(text, extra),
        key=lambda s: (-(s[1] - s[0]), order.get(s[2], len(order)), s[0]),
    )
    chosen: list[tuple[int, int, str]] = []
    for start, end, kind in ranked:
        if all(end <= s or start >= e for s, e, _ in chosen):
            chosen.append((start, end, kind))
    return sorted(chosen)


def is_safe_form(text: str) -> bool:
    """Timestamps, durations and short counters: values that identify nothing."""
    return any(p.match(text) for p in _SAFE)
