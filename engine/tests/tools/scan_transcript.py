"""Find known real values in what a Claude Code session sent to the model.

    uv run python tests/tools/scan_transcript.py <transcript.jsonl> <values.json>

`values.json` is the generic `seed.json` or the panos-mcp `real_values.json`. Every string in the
transcript that the model reads is searched (case-insensitive): user messages, assistant and
tool-result text, system sections. Exits 1 when a value is found; it prints only counts and line
numbers, never a value, so its output can be shared.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def values_from(path: Path) -> list[str]:
    data = json.loads(path.read_text())
    out: list[str] = []
    for key, items in data.items():
        if key.startswith("_") or key in {"UNCHANGED_BY_DESIGN", "OTHER"}:
            continue
        if isinstance(items, list):
            out.extend(v for v in items if isinstance(v, str))
    return out


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    if isinstance(value, dict):
        return [s for item in value.values() for s in strings(item)]
    return []


def scan(transcript: Path, values: list[str]) -> dict[int, int]:
    """line number -> how many known values the line holds."""
    wanted = [v.lower() for v in values if v]
    found: dict[int, int] = {}
    for number, line in enumerate(transcript.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            text = "\n".join(strings(json.loads(line))).lower()
        except json.JSONDecodeError:
            text = line.lower()
        hits = sum(1 for v in wanted if v in text)
        if hits:
            found[number] = hits
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    hits = scan(Path(argv[1]), values_from(Path(argv[2])))
    if not hits:
        print("clean: no known value found")
        return 0
    print(f"LEAK: {sum(hits.values())} known value(s) on {len(hits)} line(s)")
    for number, count in sorted(hits.items()):
        print(f"  line {number}: {count}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
