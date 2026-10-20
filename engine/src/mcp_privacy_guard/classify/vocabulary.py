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


@lru_cache(maxsize=1)
def common_words() -> frozenset[str]:
    lines = _COMMON.read_text(encoding="utf-8").splitlines()
    return frozenset(line.strip().lower() for line in lines if line.strip())


def is_safe_word(word: str) -> bool:
    return word.lower() in SAFE_WORDS


def is_common_word(word: str) -> bool:
    return word.lower() in common_words()
