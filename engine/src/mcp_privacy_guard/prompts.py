"""Questions: real values typed by the user become the same stand-ins the tool results use.

Shapes (IPs, FQDNs, serials, e-mails, MACs, domain users, URLs) are recognised anywhere. Names
are matched whole-token and case-sensitively against the session's dictionary. A name that is
also a plain English word is replaced only where it clearly refers to an item: quoted, or
within three words after a cue word of its kind (research R9, FR-017, FR-018).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.standins import pseudonymize
from mcp_privacy_guard.store import Store
from mcp_privacy_guard.warmup import check_gate

GENERIC_CUES = ("server", "host", "object", "group", "rule")
_TOKEN = re.compile(r"[^\s'\"`,;()\[\]{}<>=|]+")
_QUOTES = "'\"`"
CUE_WINDOW = 3


@dataclass
class PromptOut:
    text: str
    replacements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cues(row: dict[str, Any], config: Config) -> list[str]:
    profile, _, _ = loader.select_profile(row["server"], config.server(row["server"]).profile)
    declared = profile.kinds.get(row["kind"])
    return [*GENERIC_CUES, *(declared.cues if declared else [])]


def _cue_before(text: str, start: int, cues: list[str]) -> bool:
    tokens = text[:start].split()[-CUE_WINDOW:]
    window = " ".join(t.strip(".,:;!?()'\"`").lower() for t in tokens)
    return any(
        re.search(r"(?<![\w-])" + re.escape(cue.lower()) + r"(?![\w-])", window) for cue in cues
    )


def _name_spans(text: str, store: Store, config: Config) -> list[tuple[int, int, str, str, str]]:
    """(start, end, row kind, reason, real) of every known name in the question."""
    found = []
    for match in _TOKEN.finditer(text):
        token = match.group(0).rstrip(".:!?")
        start, end = match.start(), match.start() + len(token)
        rows = store.names_for(token) if token else []
        if not rows:
            continue
        row = rows[0]
        if not any(r["common_word"] for r in rows):
            found.append((start, end, row["kind"], "name", token))
            continue
        quoted = (
            start > 0 and text[start - 1] in _QUOTES
            and end < len(text) and text[end] == text[start - 1]
        )  # fmt: skip
        if quoted:
            found.append((start, end, row["kind"], "name+quote", token))
        elif any(_cue_before(text, start, _cues(r, config)) for r in rows):
            found.append((start, end, row["kind"], "name+cue", token))
    return found


def _hidden_spans(text: str, config: Config) -> list[tuple[int, int, str, str, str]]:
    found = []
    for value in {*config.hide_values, *config.hide_files}:
        if not value:
            continue
        pattern = r"(?<![\w-])" + re.escape(value) + r"(?![\w-])"
        found += [(m.start(), m.end(), "TEXT", "name", value) for m in re.finditer(pattern, text)]
    return found


def _spans(text: str, store: Store, config: Config) -> list[tuple[int, int, str, str, str]]:
    keep = {*config.keep_values, *config.keep_files}
    spans = [
        (s, e, kind, "shape", text[s:e])
        for s, e, kind in shapes.find_embedded(text)
        if text[s:e] not in keep
    ]
    for candidate in (*_hidden_spans(text, config), *_name_spans(text, store, config)):
        start, end = candidate[0], candidate[1]
        if candidate[4] in keep:
            continue
        if all(end <= s or start >= e for s, e, *_ in spans):
            spans.append(candidate)
    return sorted(spans)


def identifying(text: str, *, store: Store, config: Config) -> bool:
    """Whether the question holds anything that would be replaced; changes nothing."""
    return bool(_spans(text, store, config))


def pseudonymize_prompt(text: str, *, store: Store, config: Config) -> PromptOut:
    check_gate(store)  # no question before the session's names have loaded (FR-034)
    out, replacements, last = [], [], 0
    for start, end, kind, reason, real in _spans(text, store, config):
        core = "NAME" if reason != "shape" and kind != "TEXT" else kind
        standin = pseudonymize(core, real, store, store.key)
        if standin == real:
            continue  # unchanged by design (a netmask, the default route)
        out.append(text[last:start])
        out.append(standin)
        last = end
        replacements.append(
            {"start": start, "end": end, "kind": kind, "standin": standin, "reason": reason}
        )
    out.append(text[last:])
    return PromptOut("".join(out), replacements)
