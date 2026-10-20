"""The Public Suffix List (bundled, MPL-2.0; see NOTICE): where a host name's own labels start."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "public_suffix_list.dat"


@lru_cache(maxsize=1)
def _rules() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    exact: set[str] = set()
    wildcard: set[str] = set()
    exception: set[str] = set()
    for line in _DATA.read_text(encoding="utf-8").splitlines():
        rule = line.split()[0] if line.strip() and not line.startswith("//") else ""
        if not rule:
            continue
        rule = rule.lower()
        if rule.startswith("!"):
            exception.add(rule[1:])
        elif rule.startswith("*."):
            wildcard.add(rule[2:])
        else:
            exact.add(rule)
    return frozenset(exact), frozenset(wildcard), frozenset(exception)


def suffix_labels(labels: list[str]) -> int | None:
    """How many trailing labels form the public suffix, or None when no rule lists it."""
    exact, wildcard, exception = _rules()
    lowered = [label.lower() for label in labels]
    count = len(lowered)
    best = 0
    for k in range(1, count + 1):
        candidate = ".".join(lowered[count - k :])
        if candidate in exception:
            return k - 1
        if candidate in exact or (k >= 1 and ".".join(lowered[count - k + 1 :]) in wildcard):
            best = k
    return best or None


def split_host(host: str) -> tuple[list[str], str] | None:
    """(labels below the suffix, suffix) for a listed host, or None."""
    labels = host.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return None
    size = suffix_labels(labels)
    if size is None or size >= len(labels):
        return None
    return labels[:-size], ".".join(labels[-size:])
