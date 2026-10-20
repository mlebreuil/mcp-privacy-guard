"""MAC, DIGITS and TEXT stand-ins. MAC and DIGITS are keyed Feistel permutations."""

from __future__ import annotations

import hmac
import re

from mcp_privacy_guard.standins.names import token

ROUNDS = 4
_MAC = re.compile(r"^(?:[0-9A-Fa-f]{2}([:-])){5}[0-9A-Fa-f]{2}$")
_MAC_DOTTED = re.compile(r"^(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$")


def _round(key: bytes, domain: str, rnd: int, half: int, bits: int) -> int:
    msg = f"{domain}\x1f{rnd}\x1f".encode() + half.to_bytes((bits + 7) // 8, "big")
    return int.from_bytes(hmac.digest(key, msg, "sha256")[:16], "big") & ((1 << bits) - 1)


def feistel(key: bytes, domain: str, value: int, bits: int) -> int:
    """A keyed permutation of the integers below 2**bits (bits must be even)."""
    half = bits // 2
    mask = (1 << half) - 1
    left, right = value >> half, value & mask
    for rnd in range(ROUNDS):
        left, right = right, left ^ _round(key, domain, rnd, right, half)
    return (left << half) | right


def mac(key: bytes, text: str) -> str:
    match = _MAC.match(text)
    if match:
        sep = match.group(1)
        digits = re.sub(r"[:-]", "", text)
    elif _MAC_DOTTED.match(text):
        sep, digits = ".", text.replace(".", "")
    else:
        return text
    raw = int(digits, 16)
    # permute the 46 bits other than the two low bits of the first octet; those two become
    # `10` (locally administered, unicast), so the map stays a bijection
    packed = ((raw >> 42) << 40) | (raw & ((1 << 40) - 1))
    packed = feistel(key, "mac", packed, 46)
    out = ((packed >> 40) << 42) | (0b10 << 40) | (packed & ((1 << 40) - 1))
    hexed = f"{out:012x}"
    if sep == ".":
        return ".".join(hexed[i : i + 4] for i in range(0, 12, 4))
    return sep.join(hexed[i : i + 2] for i in range(0, 12, 2))


def digits(key: bytes, text: str) -> str:
    """A permutation of the digit strings of this length (cycle-walking Feistel)."""
    size = len(text)
    if not text.isdigit() or size == 0:
        return text
    limit = 10**size
    bits = limit.bit_length()
    bits += bits % 2
    value = int(text)
    while True:
        value = feistel(key, f"digits{size}", value, bits)
        if value < limit:
            return f"{value:0{size}d}"


def text(key: bytes, value: str) -> str:
    return f"text-{token(key, 'text', value, 8)}"
