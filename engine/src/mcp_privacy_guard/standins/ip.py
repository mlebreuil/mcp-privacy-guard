"""IP stand-ins: Crypto-PAn keyed by the session secret (research R7).

A prefix-preserving permutation: two addresses that share their first `n` bits keep sharing
exactly `n` bits. The bits of a *fixed prefix* are not permuted, so an address keeps its
special block (private, loopback, multicast...) or, for a public address, its first octet
(first 16 bits for IPv6) and its publicness: the fixed prefix of a public address is the
shortest one whose region contains no special block, so a public stand-in can never fall
into a special block and two reals never share a stand-in.
"""

from __future__ import annotations

import hmac
import ipaddress as ia
import re
from collections.abc import Callable
from functools import lru_cache

V4_BLOCKS = [
    "0.0.0.0/32", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/5", "248.0.0.0/6",
    "252.0.0.0/7", "254.0.0.0/8", "255.0.0.0/8",
]  # fmt: skip
# Everything in 255.0.0.0/8 (the broadcast address and every netmask) is left unchanged.
UNCHANGED_V4 = ia.ip_network("255.0.0.0/8")
V6_BLOCKS = [
    "::/128", "::1/128", "::ffff:0:0/96", "fc00::/7", "fe80::/10", "ff00::/8", "2001:db8::/32",
]  # fmt: skip
MIN_FIXED = {4: 8, 6: 16}
WIDTH = {4: 32, 6: 128}

# (first address, last address, prefix length) of each special block, by IP version
_BLOCKS: dict[int, list[tuple[int, int, int]]] = {
    version: [
        (
            int(net.network_address),
            int(net.broadcast_address),
            net.max_prefixlen if net == UNCHANGED_V4 else net.prefixlen,
        )
        for net in (ia.ip_network(b) for b in blocks)
    ]
    for version, blocks in ((4, V4_BLOCKS), (6, V6_BLOCKS))
}

_WILDCARD = re.compile(r"^(\d{1,3})(\.(\d{1,3}))?(\.(\d{1,3}))?(\.\*)+$")


def _flip(key: bytes, version: int, i: int, prefix: int) -> int:
    msg = b"ip\x1f" + bytes([version, i]) + prefix.to_bytes(16, "big")
    return hmac.digest(key, msg, "sha256")[0] & 1


@lru_cache(maxsize=65536)
def _fixed_len(version: int, value: int) -> int:
    """Number of leading bits of `value` that are not permuted."""
    width = WIDTH[version]
    for first, last, plen in _BLOCKS[version]:
        if first <= value <= last:
            return plen
    for length in range(MIN_FIXED[version], width + 1):
        shift = width - length
        lo = (value >> shift) << shift
        hi = lo + (1 << shift) - 1
        if not any(lo <= last and first <= hi for first, last, _ in _BLOCKS[version]):
            return length
    return width


def _permute_int(key: bytes, value: int, version: int) -> int:
    width = WIDTH[version]
    out = value
    for i in range(_fixed_len(version, value), width):
        pos = width - i - 1
        bit = (value >> pos) & 1
        flip = _flip(key, version, i, value >> (width - i))
        out = (out & ~(1 << pos)) | ((bit ^ flip) << pos)
    return out


def _invert_int(key: bytes, value: int, version: int) -> int:
    width = WIDTH[version]
    out = value
    for i in range(_fixed_len(version, value), width):
        pos = width - i - 1
        bit = (value >> pos) & 1
        flip = _flip(key, version, i, out >> (width - i))
        out = (out & ~(1 << pos)) | ((bit ^ flip) << pos)
    return out


def _step(key: bytes, decode: bool) -> Callable[[int, int], int]:
    if decode:
        return lambda value, version: _invert_int(key, value, version)
    return lambda value, version: _permute_int(key, value, version)


def _addr(text: str) -> ia.IPv4Address | ia.IPv6Address | None:
    if not text or "%" in text or text != text.strip():
        return None
    try:
        return ia.ip_address(text)
    except ValueError:
        return None


def _map_address(key: bytes, text: str, decode: bool) -> str | None:
    addr = _addr(text)
    if addr is None:
        return None
    out = _step(key, decode)(int(addr), addr.version)
    return str(type(addr)(out))


def _map_prefix(key: bytes, text: str, decode: bool) -> str | None:
    head, sep, tail = text.partition("/")
    if not sep or not tail.isdigit() or str(int(tail)) != tail:
        return None
    addr = _addr(head)
    length = int(tail)
    if addr is None or length > addr.max_prefixlen:
        return None
    version, width = addr.version, WIDTH[addr.version]
    if length == 0 and int(addr) == 0:
        return text
    host_mask = (1 << (width - length)) - 1
    step = _step(key, decode)
    value = int(addr)
    if value & host_mask == 0:  # a network: the host bits stay zero
        out = step(value, version) & ~host_mask
    else:  # an interface address: cycle-walk so the host bits stay non-zero
        out = step(value, version)
        while out & host_mask == 0:
            out = step(out, version)
    return f"{type(addr)(out)}/{length}"


def _map_range(key: bytes, text: str, decode: bool) -> str | None:
    head, sep, tail = text.partition("-")
    if not sep:
        return None
    first, second = _addr(head), _addr(tail)
    if first is None or second is None or first.version != second.version:
        return None
    step = _step(key, decode)
    pair = sorted(step(int(a), first.version) for a in (first, second))
    return "-".join(str(type(first)(v)) for v in pair)


def _map_wildcard(key: bytes, text: str, decode: bool) -> str | None:
    if "*" not in text or ":" in text:
        return None
    parts = text.split(".")
    known = [p for p in parts if p != "*"]
    if (
        len(parts) != 4
        or not known
        or parts[: len(known)] != known
        or any(not p.isdigit() or int(p) > 255 or str(int(p)) != p for p in known)
    ):
        return None
    value = 0
    for part in known:
        value = (value << 8) | int(part)
    value <<= 8 * (4 - len(known))
    out = _step(key, decode)(value, 4) >> (8 * (4 - len(known)))
    octets = [(out >> (8 * (len(known) - 1 - i))) & 0xFF for i in range(len(known))]
    return ".".join([*(str(o) for o in octets), *["*"] * (4 - len(known))])


def _map(key: bytes, text: str, decode: bool) -> str:
    for mapper in (_map_address, _map_prefix, _map_range, _map_wildcard):
        out = mapper(key, text, decode)
        if out is not None:
            return out
    return text


def permute(key: bytes, text: str) -> str:
    """The stand-in of an address, prefix, range or wildcard; anything else is returned as is."""
    return _map(key, text, decode=False)


def invert(key: bytes, text: str) -> str:
    """The real value behind a stand-in of `permute` under the same key."""
    return _map(key, text, decode=True)
