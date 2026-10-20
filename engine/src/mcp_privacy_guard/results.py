"""MCP tool results: what the model may read of one (contracts/engine-cli.md `result`).

Text blocks that are JSON are walked and re-serialised in their own style, a summary line
followed by JSON is handled line by line, other text goes through the MIXED rule one line at a
time, `structuredContent` is walked, and anything that is not text is withheld. A result that
is too large or takes too long is refused, never passed through (FR-007).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from mcp_privacy_guard.classify.text import hide_block, mixed
from mcp_privacy_guard.classify.walker import Walker
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.errors import Refused
from mcp_privacy_guard.profiles.loader import Profile
from mcp_privacy_guard.store import Store

MAX_TEXT = 2 * 1024 * 1024
TIME_LIMIT = 10.0


@dataclass
class ResultOut:
    result: dict[str, Any]
    withheld: int = 0
    notices: list[str] = field(default_factory=list)


def _dumps(value: Any, style: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, **style)


STYLES: list[dict[str, Any]] = [
    {"separators": (",", ":")},
    {},
    {"indent": 2},
    {"indent": 4},
]


def _style_of(original: str, parsed: Any) -> dict[str, Any]:
    stripped = original.strip()
    for style in STYLES:
        if _dumps(parsed, style) == stripped:
            return style
    if "\n" in stripped:
        lines = stripped.split("\n")
        indent = len(lines[1]) - len(lines[1].lstrip()) if len(lines) > 1 else 2
        return {"indent": indent or 2}
    return {} if ", " in stripped or ": " in stripped else {"separators": (",", ":")}


def _parse_container(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        value = json.loads(stripped)
    except ValueError:
        return None
    return value if isinstance(value, (dict, list)) else None


class _Handler:
    def __init__(
        self,
        store: Store,
        profile: Profile,
        config: Config,
        server: str,
        tool: str,
        deadline: float,
    ) -> None:
        self.store, self.profile, self.config, self.server = store, profile, config, server
        self.walker = Walker(
            store=store, profile=profile, config=config, server=server, tool=tool, deadline=deadline
        )

    def json_text(self, text: str, parsed: Any) -> str:
        style = _style_of(text, parsed)
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()) :]
        return lead + _dumps(self.walker.walk(parsed), style) + trail

    def line(self, line: str) -> str:
        self.walker.tick()
        parsed = _parse_container(line)
        if parsed is not None:
            return self.json_text(line, parsed)
        return mixed(
            line, store=self.store, profile=self.profile, config=self.config, server=self.server
        )

    def text_block(self, text: str) -> str:
        parsed = _parse_container(text)
        if parsed is not None:
            return self.json_text(text, parsed)
        if self.profile.text_mode == "whole":
            return hide_block(text, store=self.store) if text.strip() else text
        out = []
        for raw in text.split("\n"):
            body = raw.rstrip("\r")
            out.append(self.line(body) + raw[len(body) :])
        return "\n".join(out)


def pseudonymize_result(
    result: dict[str, Any],
    *,
    store: Store,
    profile: Profile,
    config: Config,
    server: str,
    tool: str,
    is_error: bool = False,
    time_limit: float = TIME_LIMIT,
    max_text: int = MAX_TEXT,
) -> ResultOut:
    deadline = time.monotonic() + time_limit
    blocks = result.get("content") or []
    size = sum(len(str(b.get("text", "")).encode()) for b in blocks if isinstance(b, dict))
    if "structuredContent" in result:
        size += len(json.dumps(result["structuredContent"], ensure_ascii=False).encode())
    if size > max_text:
        raise Refused("too-large", "the result is too large to pseudonymize", "narrow the query")

    handler = _Handler(store, profile, config, server, tool, deadline)
    content: list[dict[str, Any]] = []
    withheld = 0
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
            content.append({"type": "text", "text": handler.text_block(str(block["text"]))})
        else:
            withheld += 1
    notices: list[str] = []
    if withheld:
        notices.append(f"{withheld} non-text item(s) withheld")
        content.append({"type": "text", "text": f"[privacy-guard: {notices[0]}]"})

    out: dict[str, Any] = {"content": content, "isError": bool(result.get("isError", is_error))}
    if "structuredContent" in result and result["structuredContent"] is not None:
        out["structuredContent"] = handler.walker.walk(result["structuredContent"])
    return ResultOut(out, withheld, notices)
