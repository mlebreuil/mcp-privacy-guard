"""Built-in safe vocabulary and the common-word list."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_COMMON = Path(__file__).parent.parent / "data" / "common_words.txt"

SAFE_WORDS = frozenset(
    """
    true false yes no none null nil on off
    allow deny drop permit block reject accept reset
    enabled disabled up down active inactive ok failed success failure pending
    tcp udp icmp icmpv6 sctp gre esp ah ipv4 ipv6
    http https ssh telnet ftp sftp tftp smtp imap pop3 dns ntp snmp ldap ldaps radius syslog
    kerberos rdp sip tls ssl
    info informational notice low medium high critical warning warn error debug alert emergency
    get post put delete patch head options connect trace
    any unknown default
    """.split()
)


# Short function words the common-word list (three letters and up) does not hold.
FUNCTION_WORDS = frozenset(
    "a an as at be by do go he i if in is it me my no of on or so to up us we am".split()
)

# Words of field names that are not in the common-word list: a key made of these is a plain key.
KEY_WORDS = frozenset(
    """
    ip ips mac url uri id ids fqdn hostname serial vsys dns ntp cpu ram os sw hw ha vpn nat acl
    vlan src dst dport sport proto app rule rules zone zones tag tags uuid cidr asn mtu ttl ssl
    tls ssh http https tcp udp icmp api sku vm vms db dc lan wan dmz
    """.split()
)


@lru_cache(maxsize=1)
def common_words() -> frozenset[str]:
    lines = _COMMON.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip())


def is_safe_word(word: str) -> bool:
    return word.lower() in SAFE_WORDS


def _stems(word: str) -> list[str]:
    """The word and the plain forms it may be an inflection of (devices, allowed, listing)."""
    out = [word]
    for suffix, replacement in (
        ("ies", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"),
        ("er", ""), ("ers", ""), ("ly", ""), ("ness", ""),
    ):  # fmt: skip
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            stem = word[: len(word) - len(suffix)] + replacement
            out.append(stem)
            if len(stem) > 3 and stem[-1] == stem[-2]:  # stopped -> stop
                out.append(stem[:-1])
    return out


def is_common_word(word: str) -> bool:
    lowered = word.lower()
    if lowered in FUNCTION_WORDS:
        return True
    words = common_words()
    return any(stem in words for stem in _stems(lowered))


def is_key_word(word: str) -> bool:
    lowered = word.lower()
    return is_common_word(lowered) or lowered in KEY_WORDS or lowered in SAFE_WORDS
