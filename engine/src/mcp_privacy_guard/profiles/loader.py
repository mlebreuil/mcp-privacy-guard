"""Profile loading, validation and path patterns (contracts/profile-format.md).

A profile can only make handling more precise (FR-014): it can let listed enum or vocabulary
values through, never a value of identifying shape, and it cannot drop a warm-up.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_privacy_guard.classify import shapes

PROFILES_DIR = Path(__file__).parent
CORE_KINDS = frozenset(
    {"IP", "FQDN", "URL", "MAC", "EMAIL", "USER", "GROUP", "NAME", "DIGITS", "TEXT", "MIXED"}
)
_ID = re.compile(r"[a-z0-9-]+")
_KIND = re.compile(r"[A-Z][A-Z0-9_]*")
_SEGMENT = re.compile(r"^(\*\*|\*|[^.\[\]*\s]+)((?:\[\])*)$")
ARRAY = "[]"


class ProfileError(Exception):
    """A profile that cannot be applied. `reason` is a stable code; no input value is held."""

    def __init__(self, reason: str, path: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.path = path


# -- path patterns -----------------------------------------------------------------------


@dataclass(frozen=True)
class PathPattern:
    source: str
    tokens: tuple[tuple[str, str], ...]

    def matches(self, steps: Sequence[str]) -> bool:
        return self._match(0, 0, tuple(steps))

    def _match(self, ti: int, si: int, steps: tuple[str, ...]) -> bool:
        if ti == len(self.tokens):
            return si == len(steps)
        kind, value = self.tokens[ti]
        if kind == "deep":
            return any(self._match(ti + 1, k, steps) for k in range(si, len(steps) + 1))
        if si == len(steps):
            return False
        step = steps[si]
        if kind == "array":
            ok = step == ARRAY
        elif kind == "any":
            ok = step != ARRAY
        else:
            ok = step == value
        return ok and self._match(ti + 1, si + 1, steps)


def compile_path(pattern: str) -> PathPattern:
    if not pattern:
        raise ProfileError("bad-path")
    tokens: list[tuple[str, str]] = []
    for segment in pattern.split("."):
        match = _SEGMENT.match(segment)
        if match is None:
            raise ProfileError("bad-path")
        head, arrays = match.groups()
        if head == "**":
            if arrays or (tokens and tokens[-1][0] == "deep"):
                raise ProfileError("bad-path")
            tokens.append(("deep", ""))
        elif head == "*":
            tokens.append(("any", ""))
        else:
            tokens.append(("key", head))
        tokens.extend(("array", "") for _ in range(len(arrays) // 2))
    return PathPattern(pattern, tuple(tokens))


# -- the profile model -------------------------------------------------------------------


@dataclass(frozen=True)
class FieldRule:
    path: str
    matcher: PathPattern
    tools: tuple[str, ...] | None = None
    kind: str | None = None
    enum: tuple[str, ...] | None = None
    keys: str | None = None


@dataclass(frozen=True)
class KindDecl:
    cues: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Warmup:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Profile:
    id: str
    version: int
    description: str
    servers: list[str]
    kinds: dict[str, KindDecl]
    vocabulary: frozenset[str]
    fields: list[FieldRule]
    text_mode: str
    warmup: list[Warmup]

    def applies_to(self, alias: str) -> bool:
        return any(fnmatch.fnmatchcase(alias, pattern) for pattern in self.servers)

    def match_field(
        self, tool: str, steps: Sequence[str], want: str | None = None
    ) -> FieldRule | None:
        """The first rule matching the path: tool-specific rules first, then the general ones.

        `want` narrows to the rules about values (`kind`/`enum`) or about object keys (`keys`).
        """

        def relevant(rule: FieldRule) -> bool:
            if want == "value":
                return rule.keys is None
            if want == "keys":
                return rule.keys is not None
            return True

        for rule in self.fields:
            if rule.tools is not None and tool in rule.tools and relevant(rule):
                if rule.matcher.matches(steps):
                    return rule
        for rule in self.fields:
            if rule.tools is None and relevant(rule) and rule.matcher.matches(steps):
                return rule
        return None


# -- loading -----------------------------------------------------------------------------


def _strings(value: object, reason: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProfileError(reason)
    return list(value)


def _check_values(values: Iterable[str]) -> None:
    for value in values:
        if shapes.classify_whole(value) is not None:
            raise ProfileError("identifying-vocabulary")


def _vocabulary(table: dict[str, Any], base: Path | None) -> frozenset[str]:
    values = _strings(table.get("values", []), "bad-vocabulary")
    for name in _strings(table.get("files", []), "bad-vocabulary"):
        try:
            lines = ((base or PROFILES_DIR) / name).read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ProfileError("bad-vocabulary-file") from exc
        values += [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    _check_values(values)
    return frozenset(v.lower() for v in values)


def _field(raw: object, declared: set[str]) -> FieldRule:
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
        raise ProfileError("field-rule")
    matcher = compile_path(raw["path"])
    actions = [k for k in ("kind", "enum", "keys") if k in raw]
    if len(actions) != 1:
        raise ProfileError("field-rule", raw["path"])
    tools = None
    if "tools" in raw:
        tools = tuple(_strings(raw["tools"], "field-rule"))
    kind = enum = keys = None
    if "kind" in raw:
        kind = raw["kind"]
        if not isinstance(kind, str) or kind not in CORE_KINDS | declared:
            raise ProfileError("unknown-kind", raw["path"])
    elif "enum" in raw:
        enum = tuple(_strings(raw["enum"], "field-rule"))
        _check_values(enum)
    else:
        keys = raw["keys"]
        if keys not in ("keep", "hide"):
            raise ProfileError("bad-keys", raw["path"])
    return FieldRule(raw["path"], matcher, tools, kind, enum, keys)


def _overlaps(a: Iterable[str], b: Iterable[str]) -> bool:
    b = list(b)
    return any(fnmatch.fnmatchcase(x, y) or fnmatch.fnmatchcase(y, x) for x in a for y in b)


def load_profile(
    text: str, *, base: Path | None = None, bundled: Iterable[Profile] = ()
) -> Profile:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError("invalid-toml") from exc
    allowed = {"profile", "kinds", "vocabulary", "fields", "text", "warmup"}
    if set(data) - allowed:
        raise ProfileError("unknown-key")
    head = data.get("profile")
    if not isinstance(head, dict):
        raise ProfileError("bad-id")
    pid = head.get("id")
    if not isinstance(pid, str) or not _ID.fullmatch(pid):
        raise ProfileError("bad-id")
    if head.get("version") != 1 or isinstance(head.get("version"), bool):
        raise ProfileError("bad-version")
    servers = _strings(head.get("servers"), "bad-servers")
    if not servers:
        raise ProfileError("bad-servers")

    kinds: dict[str, KindDecl] = {}
    raw_kinds = data.get("kinds", {})
    if not isinstance(raw_kinds, dict):
        raise ProfileError("bad-kind-name")
    for name, decl in raw_kinds.items():
        if not _KIND.fullmatch(name):
            raise ProfileError("bad-kind-name")
        if name in CORE_KINDS:
            raise ProfileError("core-kind-redefined")
        if not isinstance(decl, dict):
            raise ProfileError("bad-kind-name")
        kinds[name] = KindDecl(_strings(decl.get("cues", []), "bad-cues"))

    vocabulary = _vocabulary(data.get("vocabulary", {}), base)
    fields = [_field(raw, set(kinds)) for raw in data.get("fields", [])]
    mode = data.get("text", {}).get("mode", "mixed")
    if mode not in ("mixed", "whole"):
        raise ProfileError("bad-text-mode")
    warmup = []
    for raw in data.get("warmup", []):
        tool, args = raw.get("tool"), raw.get("args", {})
        if not isinstance(tool, str) or not isinstance(args, dict):
            raise ProfileError("bad-warmup")
        warmup.append(Warmup(tool, args))

    profile = Profile(
        pid, 1, str(head.get("description", "")), servers, kinds, vocabulary, fields, mode, warmup
    )
    for other in bundled:
        if other.id != pid and other.warmup and not warmup and _overlaps(servers, other.servers):
            raise ProfileError("warmup-required")
    return profile


def load_file(path: Path, *, bundled: Iterable[Profile] = ()) -> Profile:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError("unreadable") from exc
    return load_profile(text, base=path.parent, bundled=bundled)


def load_bundled(name: str) -> Profile:
    return load_file(PROFILES_DIR / f"{name}.toml")


def bundled_profiles() -> list[Profile]:
    """Every bundled profile except the default, in name order."""
    return [load_file(p) for p in sorted(PROFILES_DIR.glob("*.toml")) if p.stem != "default"]


def select_profile(alias: str, configured: str | None) -> tuple[Profile, str, str | None]:
    """The profile for a server alias: (profile, "valid" | "invalid", reason).

    Order: the profile named in the config, then the bundled profile whose server globs
    match, then the default. An invalid choice falls back to the default, never to pass-through.
    """
    default = load_bundled("default")
    bundled = {p.id: p for p in bundled_profiles()}
    if configured is not None:
        if configured in bundled:
            return bundled[configured], "valid", None
        if configured == "default":
            return default, "valid", None
        return default, "invalid", "unknown-profile"
    for profile in bundled.values():
        if profile.applies_to(alias):
            return profile, "valid", None
    return default, "valid", None
