"""Tool arguments: stand-ins the model uses become real values again (FR-011, FR-012).

Every value coming back from the model is read as a stand-in. Stand-ins the session issued are
looked up in its mapping. An address in IP form is inverted with the session key, issued or not.
Anything else, an unknown `n-zzzzzz` included, is left as typed, and nothing in the reply says
which values were unknown. Argument keys never change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.standins import ip
from mcp_privacy_guard.store import Store

STANDIN_TOKEN = re.compile(r"\b(?:n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b")


@dataclass
class ArgsOut:
    args: dict[str, Any]
    translated: int


class _Translator:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.count = 0

    def _known(self, text: str) -> str | None:
        row = self.store.lookup_standin(text)
        if row is None or row["fixed"]:
            return None
        return str(row["real"])

    def _ip(self, text: str) -> str | None:
        if shapes.classify_whole(text) != "IP":
            return None
        real = ip.invert(self.store.key, text)
        return real if real != text else None

    def string(self, text: str) -> str:
        whole = self._known(text) or self._ip(text)
        if whole is not None:
            self.count += 1
            return whole
        out, last = [], 0
        for start, end, kind in shapes.find_embedded(text, [(STANDIN_TOKEN, "NAME")]):
            piece = text[start:end]
            real = self._known(piece) or (self._ip(piece) if kind == "IP" else None)
            if real is None:
                continue
            out.append(text[last:start])
            out.append(real)
            last = end
            self.count += 1
        out.append(text[last:])
        return "".join(out)

    def walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self.walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v) for v in value]
        if isinstance(value, str):
            return self.string(value)
        return value


def translate(args: dict[str, Any], *, store: Store) -> ArgsOut:
    translator = _Translator(store)
    out = translator.walk(args)
    return ArgsOut(out, translator.count)
