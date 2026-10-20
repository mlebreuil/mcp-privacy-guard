"""Walks a JSON value and pseudonymizes every identifying string, keys included.

Decision order for a string (research R4, first match wins): hide list, keep list, profile
field rule (kind or enum), built-in safe forms and vocabulary, whole-value shape, a single
token (a name), then the MIXED rule. Numbers, booleans and null are never identifying.
"""

from __future__ import annotations

import re
import time
from typing import Any

from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.classify.text import mixed
from mcp_privacy_guard.classify.vocabulary import is_common_word, is_key_word, is_safe_word
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.errors import Refused
from mcp_privacy_guard.profiles.loader import ARRAY, Profile
from mcp_privacy_guard.standins import CORE_KINDS, pseudonymize
from mcp_privacy_guard.store import Store

_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_SPLIT = re.compile(r"[\s_.\-/]+")
_SHAPE_KINDS = frozenset({"IP", "FQDN", "URL", "MAC", "EMAIL", "USER", "DIGITS"})
_NAME_KINDS = frozenset({"NAME", "USER", "GROUP"})
MAX_KEY_WORDS = 4


class Walker:
    def __init__(
        self,
        *,
        store: Store,
        profile: Profile,
        config: Config,
        server: str,
        tool: str,
        deadline: float | None = None,
    ) -> None:
        self.store = store
        self.profile = profile
        self.config = config
        self.server = server
        self.tool = tool
        self.deadline = deadline
        self.hide = frozenset((*config.hide_values, *config.hide_files))
        self.keep = frozenset((*config.keep_values, *config.keep_files))

    # -- guards ------------------------------------------------------------------------

    def tick(self) -> None:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise Refused("timeout", "the result took too long to pseudonymize")

    def stand_in(self, kind: str, real: str) -> str:
        if kind in _NAME_KINDS or kind not in CORE_KINDS:
            # a name, user or group: learn it so a question can recognise it (research R9)
            self.store.add_name(real, kind, self.server, is_common_word(real))
        return pseudonymize(kind, real, self.store, self.store.key)

    # -- walking -----------------------------------------------------------------------

    def walk(self, value: Any, steps: tuple[str, ...] = ()) -> Any:
        self.tick()
        if isinstance(value, dict):
            return {self.key(k, steps): self.walk(v, (*steps, k)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v, (*steps, ARRAY)) for v in value]
        if isinstance(value, str):
            return self.string(value, steps)
        return value

    # -- keys --------------------------------------------------------------------------

    def hidden_key(self, key: str) -> str:
        return self.stand_in(shapes.classify_whole(key) or "NAME", key)

    def plain_key(self, key: str) -> bool:
        if any(ch.isdigit() for ch in key):
            return False
        words = [w for part in _SPLIT.split(key) for w in _CAMEL.split(part) if w]
        if not words or len(words) > MAX_KEY_WORDS:
            return False
        return all(
            (w.isalpha() and len(w) <= 2) or is_key_word(w) or w.lower() in self.profile.vocabulary
            for w in words
        )

    def key(self, key: str, steps: tuple[str, ...]) -> str:
        if key in self.hide:
            return self.stand_in("TEXT", key)
        rule = self.profile.match_field(self.tool, (*steps, key), "keys")
        mode = rule.keys if rule is not None else None
        if mode == "hide":
            return self.hidden_key(key)
        if shapes.classify_whole(key) is not None:
            return self.hidden_key(key)  # a key of identifying shape is never kept (FR-004)
        if mode == "keep" or self.plain_key(key):
            return key
        return self.hidden_key(key)

    # -- strings -----------------------------------------------------------------------

    def string(self, value: str, steps: tuple[str, ...]) -> str:
        if value == "":
            return value
        if value in self.hide:
            return self.stand_in("TEXT", value)
        if value in self.keep:
            return value
        rule = self.profile.match_field(self.tool, steps, "value")
        if rule is not None:
            ruled = self.by_rule(value, rule.kind, rule.enum)
            if ruled is not None:
                return ruled
        if (
            shapes.is_safe_form(value)
            or is_safe_word(value)
            or value.lower() in self.profile.vocabulary
        ):
            return value
        kind = shapes.classify_whole(value)
        if kind is not None:
            return self.stand_in(kind, value)
        if not any(ch.isspace() for ch in value):
            return self.stand_in("NAME", value)
        return self.text(value)

    def by_rule(self, value: str, kind: str | None, enum: tuple[str, ...] | None) -> str | None:
        if enum is not None:
            if value.lower() in {e.lower() for e in enum}:
                return value
            return self.stand_in("NAME", value)
        if kind is None:
            return None
        if kind == "MIXED":
            return self.text(value)
        if kind in _SHAPE_KINDS:
            if shapes.classify_whole(value) != kind:
                return None  # not of that shape: the default classification decides
            return self.stand_in(kind, value)
        if kind == "GROUP" and "\\" not in value:
            return self.stand_in("NAME", value)
        return self.stand_in(kind, value)  # a core kind or a profile name kind

    def text(self, value: str) -> str:
        return mixed(
            value, store=self.store, profile=self.profile, config=self.config, server=self.server
        )


def walk_json(
    value: Any,
    *,
    store: Store,
    profile: Profile,
    config: Config,
    server: str,
    tool: str,
    deadline: float | None = None,
) -> Any:
    return Walker(
        store=store, profile=profile, config=config, server=server, tool=tool, deadline=deadline
    ).walk(value)
