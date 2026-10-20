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
from mcp_privacy_guard.errors import Refused
from mcp_privacy_guard.standins import ip
from mcp_privacy_guard.store import Store

UNKNOWN_MARK = "\u27e8?\u27e9"
STANDIN_TOKEN = re.compile(r"\b(?:n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b")


@dataclass
class ArgsOut:
    args: dict[str, Any]
    translated: int


class _Translator:
    def __init__(self, store: Store, unknown: list[str] | None = None) -> None:
        self.store = store
        self.count = 0
        self.unknown = unknown  # when given, unknown name-shaped stand-ins are collected here
        self.flagged: set[str] = set()

    def _resolve(self, text: str, may_invert: bool) -> str | None:
        """The real value of a stand-in, or None to leave `text` as typed.

        A fixed entry is a value the model saw unchanged: it is never inverted. A value that
        is both fixed and an issued stand-in cannot be told apart (research R15): `args`
        refuses the call, `reveal` marks it.
        """
        row = self.store.lookup_standin(text)
        if row is not None:
            if row["fixed"]:
                return None
            if self.store.is_ambiguous(text):
                if self.unknown is None:
                    raise Refused("ambiguous-address", "an address in this call is ambiguous")
                self.flagged.add(text)
                return None
            return str(row["real"])
        if not may_invert or shapes.classify_whole(text) != "IP":
            return None
        real = ip.invert(self.store.key, text)
        return real if real != text else None

    def string(self, text: str) -> str:
        whole = self._resolve(text, True)
        if whole is not None:
            self.count += 1
            return whole
        out, last = [], 0
        for start, end, kind in shapes.find_embedded(text, [(STANDIN_TOKEN, "NAME")]):
            piece = text[start:end]
            real = self._resolve(piece, kind == "IP")
            if real is None:
                if self.unknown is not None and (kind == "NAME" or piece in self.flagged):
                    out.append(text[last:end])
                    out.append(UNKNOWN_MARK)
                    last = end
                    if kind == "NAME":
                        self.unknown.append(piece)
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
