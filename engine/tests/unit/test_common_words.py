"""The common-word list: SCOWL (size 35, US spelling), with its notice and the networking terms."""

from __future__ import annotations

import re
from pathlib import Path

from mcp_privacy_guard.classify import vocabulary

DATA = Path(vocabulary.__file__).parent.parent / "data" / "common_words.txt"
NETWORK_TERMS = "inside outside trust untrust dmz web test prod dev lan wan mgmt".split()


def test_the_list_carries_the_scowl_copyright_notice() -> None:
    text = DATA.read_text(encoding="utf-8")
    assert "Copyright 2000-2026 by Kevin Atkinson" in text
    assert "Permission to use, copy, modify, distribute, and sell" in text


def test_comment_lines_are_not_words() -> None:
    words = vocabulary.common_words()
    assert all(re.fullmatch(r"[a-z]{3,}", w) for w in words)


def test_the_networking_terms_are_common_words() -> None:
    words = vocabulary.common_words()
    assert all(term in words for term in NETWORK_TERMS)


def test_the_list_holds_plain_english_words() -> None:
    words = vocabulary.common_words()
    assert {"system", "device", "network", "allow"} <= words
    assert len(words) > 10_000  # SCOWL size 35
