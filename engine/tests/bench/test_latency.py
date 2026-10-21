"""T096 (SC-006): the hook path is fast enough that nobody waits for it.

The plugin's MCP path runs `args`, the tool, then `result`, each in a fresh engine process.
Budget: under 1 s from the hook's start to its reply for 500 records of 1 KB, and under 1 s for
a 2,000-character question. If this fails, record the long-lived helper alternative in plan.md
Complexity Tracking before adopting it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store
from tests.conftest import KEY, Cli, load_generic_results

pytestmark = pytest.mark.bench
generic = load_generic_results()
SID = "s-bench"
BUDGET = 1.0
RECORDS = 500


def records() -> dict[str, Any]:
    seed = generic.seed()
    rows = []
    for i in range(RECORDS):
        rows.append(
            {
                "id": i,
                "name": f"{seed['devices'][i % 3]}-{i}",
                "hostname": f"h{i}.{seed['fqdns'][i % 3]}",
                "ip": f"10.{i % 250}.{(i * 7) % 250}.{(i * 3) % 250 + 1}",
                "owner": seed["emails"][0],
                "state": "connected",
                "description": " ".join(seed["descriptions"]) * 3,
                "notes": [seed["log_free_text"][i % 2] for _ in range(9)],
            }
        )
    text = json.dumps({"records": rows})
    assert len(text) / RECORDS >= 900, "about 1 KB per record"
    return {"content": [{"type": "text", "text": text}], "isError": False}


def timed(fn):  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    value = fn()
    return time.perf_counter() - start, value


def test_hook_path_on_500_records_of_1_kb(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    assert cli("begin", "--session", SID, "--servers", "generic").code == 0
    result = records()
    cli("status", "--session", SID)  # warm the interpreter and the disk cache

    def hook() -> tuple[Cli, Cli]:
        first = cli(
            "args", "--session", SID, "--server", "generic", "--tool", "list",
            stdin=json.dumps({"args": {"filter": "all"}}),
        )  # fmt: skip
        second = cli(
            "result", "--session", SID, "--server", "generic", "--tool", "list",
            stdin=json.dumps({"result": result, "is_error": False}),
        )  # fmt: skip
        return first, second

    elapsed, (args, out) = timed(hook)
    assert args.code == 0 and out.code == 0
    assert elapsed < BUDGET, f"hook path took {elapsed:.2f}s"


def test_engine_only_args_and_result_on_500_records() -> None:
    store = Store.ephemeral(KEY)
    result = records()
    profile = loader.load_bundled("default")

    def engine() -> object:
        return pseudonymize_result(
            result, store=store, profile=profile, config=Config(), server="generic", tool="list"
        )

    elapsed, _ = timed(engine)
    assert elapsed < BUDGET, f"engine part took {elapsed:.2f}s"


def test_a_2000_character_question(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    assert cli("begin", "--session", SID, "--servers", "generic").code == 0
    seed = generic.seed()
    sentence = (
        f"Why does {seed['users'][0]} on {seed['ips'][0]} reach {seed['fqdns'][0]} "
        "while the nightly report still fails with a timeout? "
    )
    text = (sentence * 20)[:2000]
    elapsed, out = timed(lambda: cli("prompt", "--session", SID, stdin=json.dumps({"text": text})))
    assert out.code == 0 and seed["ips"][0] not in out.json["text"]
    assert elapsed < BUDGET, f"prompt took {elapsed:.2f}s"
