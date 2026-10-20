"""Reveal and observe: stand-ins become real values again, for the user's screen only (R10).

`reveal` is the fallback for text copied out of a transcript. `observe` is for the plugin: it
inverts IP forms the model wrote (stand-ins that were never issued) with the session key and
records them, so the plugin's table can reveal them on screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mcp_privacy_guard.arguments import _Translator
from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.errors import Refused, StoreUnavailable
from mcp_privacy_guard.standins import ip
from mcp_privacy_guard.store import Store


@dataclass
class RevealOut:
    text: str
    revealed: int
    unknown: list[str]


def reveal(text: str, *, store: Store) -> RevealOut:
    unknown: list[str] = []
    translator = _Translator(store, unknown)
    return RevealOut(translator.string(text), translator.count, unknown)


def observe(text: str, *, store: Store) -> int:
    """Record the IP forms in `text` that invert to another address. Returns how many."""
    recorded = 0
    for start, end, kind in shapes.find_embedded(text):
        if kind != "IP":
            continue
        piece = text[start:end]
        real = ip.invert(store.key, piece)
        if real == piece or store.lookup_standin(piece) is not None:
            continue
        try:
            store.issue("IP", real, piece)
        except Refused:
            continue  # the stand-in belongs to another value; the table keeps the first
        recorded += 1
    return recorded


def only_live_session(home: Path) -> str:
    live = Store.live(home)
    if len(live) != 1:
        raise StoreUnavailable(
            "no-single-session",
            "there is no single live session",
            "pass --session <id>; stand-ins of an ended session cannot be revealed",
        )
    return live[0]
