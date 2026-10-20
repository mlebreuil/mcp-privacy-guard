"""Record raw `panos-mcp` offline-demo results as leak-test fixtures (research R12).

    uv run python tests/tools/record_panos_fixtures.py [--panos ../../panos-mcp]

`panos-mcp` has no runtime pseudonymization (the guard replaces it), so what it returns in
offline demo mode is the raw tool output. The script runs every tool once, in-process, on the
`baseline` scenario, writes `<tool>.json` per tool, `tools.json` and `real_values.json` (the
identifying values found, by category), and fails when the fixtures lack a FR-004 shape.

The demo samples are synthetic (panos-mcp samples/README.md), so the fixtures hold no real data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
OUT = HERE.parents[1] / "fixtures" / "panos-mcp"
SCENARIO = "baseline"
REQUIRED = ("IP", "FQDN", "DIGITS", "USER", "NAME")
# PAN-OS defaults that identify nothing: the guard keeps them (the panos-mcp profile's built-ins)
PANOS_BUILTINS = {"trust", "untrust", "vsys1", "shared"}
# JSON keys whose string values are names an operator would not want to send
NAME_KEYS = {
    "name", "hostname", "device_name", "device_group", "device_groups", "template",
    "template_stack", "templates", "members", "member", "tag", "tags", "zone", "from_zone",
    "to_zone", "rule", "rule_name", "address_group", "parent", "children", "vsys",
}  # fmt: skip


async def record(panos: Path, out: Path) -> list[str]:
    """Run inside panos-mcp's environment: call every tool, write its raw result."""
    sys.path.insert(0, str(panos))
    from panos_mcp.client.replay import ReplayTransport
    from panos_mcp.client.xmlapi import PanoramaClient
    from panos_mcp.config import Settings
    from panos_mcp.server import build_server
    from tests.contract.test_allowlist_audit import INPUTS

    settings = Settings(samples_scenario=SCENARIO, cache_ttl=0, query_timeout=5)
    client = PanoramaClient(settings, transport=ReplayTransport(panos / "samples", SCENARIO))
    server, _ = build_server(client, settings)
    out.mkdir(parents=True, exist_ok=True)
    names = []
    for tool, args in INPUTS.items():
        result = await server.call_tool(tool, args)
        body = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        (out / f"{tool}.json").write_text(json.dumps(body, indent=2, default=str) + "\n")
        names.append(tool)
    await client.aclose()
    names.append(write_user_overlay(out))
    return sorted(names)


USERS = ("CORP\\jdoe", "CORP\\asmith")


def write_user_overlay(out: Path) -> str:
    """The demo samples carry no user names, so derive one authored fixture that does.

    It is `query_logs` with `src_user` filled by synthetic domain users, in the structured
    content and in the text the model reads (same order). Marked `_authored` in the file.
    """
    body = json.loads((out / "query_logs.json").read_text())
    users = iter(USERS * 1000)
    for item in body["structuredContent"]["items"]:
        item["src_user"] = next(users)
    users = iter(USERS * 1000)
    for block in body["content"]:
        if block.get("type") == "text":
            parts = block["text"].split('"src_user":null')
            block["text"] = parts[0] + "".join(
                f'"src_user":{json.dumps(next(users))}{part}' for part in parts[1:]
            )
    body["_authored"] = "query_logs with synthetic src_user values (no real data)"
    name = "query_logs_with_users"
    (out / f"{name}.json").write_text(json.dumps(body, indent=2, default=str) + "\n")
    return name


def strings(value: Any, key: str | None = None, out: list[tuple[str | None, str]] | None = None):
    out = [] if out is None else out
    if isinstance(value, str):
        out.append((key, value))
    elif isinstance(value, list):
        for item in value:
            strings(item, key, out)
    elif isinstance(value, dict):
        for k, v in value.items():
            strings(v, k, out)
    return out


def analyse(out: Path) -> dict[str, list[str]]:
    """Find the identifying values in the recorded results, by category."""
    from mcp_privacy_guard.classify import shapes
    from mcp_privacy_guard.classify.vocabulary import is_safe_word
    from mcp_privacy_guard.standins import ip as ipmod

    found: dict[str, set[str]] = {k: set() for k in ("IP", "FQDN", "DIGITS", "USER", "NAME")}
    other: set[str] = set()
    for path in sorted(out.glob("*.json")):
        if path.name in {"tools.json", "real_values.json"}:
            continue
        body = json.loads(path.read_text())
        for key, text in strings(body.get("structuredContent")):
            kind = shapes.classify_whole(text)
            if kind in found:
                found[kind].add(text)
            elif kind is not None:
                other.add(text)
            elif key in NAME_KEYS and text and not is_safe_word(text):
                found["NAME"].add(text)
            for start, end, embedded in shapes.find_embedded(text):
                if embedded in found:
                    found[embedded].add(text[start:end])
                else:
                    other.add(text[start:end])
    values = {k: sorted(v) for k, v in found.items()}
    values["NAME"] = [v for v in values["NAME"] if v not in PANOS_BUILTINS]
    # Addresses that stay as they are by design (a /8 summary, netmasks): the stand-in of an
    # address is never the address, except where every bit is fixed (contracts/standin-formats.md)
    unchanged = [v for v in values["IP"] if ipmod.permute(bytes(32), v) == v]
    values["IP"] = [v for v in values["IP"] if v not in unchanged]
    values["UNCHANGED_BY_DESIGN"] = unchanged
    values["OTHER"] = sorted(other)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default = os.environ.get("PANOS_MCP_REPO") or str(HERE.parents[4] / "panos-mcp")
    parser.add_argument("--panos", default=default, help="path of the panos-mcp repository")
    parser.add_argument("--record-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    panos = Path(args.panos).expanduser().resolve()

    if args.record_only:  # the part that runs in panos-mcp's environment
        names = asyncio.run(record(panos, OUT))
        (OUT / "tools.json").write_text(json.dumps(names, indent=2) + "\n")
        return 0

    env = {**os.environ, "PANOS_MCP_SAMPLES_SCENARIO": SCENARIO}
    env.pop("VIRTUAL_ENV", None)
    done = subprocess.run(  # noqa: S603
        ["uv", "run", "--project", str(panos), "python", str(HERE), "--panos", str(panos),  # noqa: S607
         "--record-only"],
        cwd=panos, env=env, check=False,
    )  # fmt: skip
    if done.returncode != 0:
        print("recording failed", file=sys.stderr)
        return done.returncode
    values = analyse(OUT)
    (OUT / "real_values.json").write_text(json.dumps(values, indent=2, ensure_ascii=False) + "\n")
    missing = [kind for kind in REQUIRED if not values[kind]]
    counts = {k: len(v) for k, v in values.items()}
    print(f"recorded {len(json.loads((OUT / 'tools.json').read_text()))} tools; values: {counts}")
    if missing:
        print(f"the fixtures lack a FR-004 shape: {missing}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
