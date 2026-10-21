"""T107 (constitution II): no subcommand prints a real value, on success or on any error path.

Every subcommand is run from a seeded session with real values from `seed.json` in its input.
Replies may carry values only where the contract returns them: `table` entries, the arguments
`args` translates for the tool, and `reveal`. Everything else, stderr and error envelopes
included, must hold no seed value and no stand-in/real pair.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import Cli, load_generic_results

from mcp_privacy_guard import cli as engine_cli

pytestmark = pytest.mark.leak
generic = load_generic_results()
SEED = generic.all_values()
SID = "s-out"
REAL_TEXT = (
    f"why is {generic.seed()['ips'][0]} blocked for {generic.seed()['users'][0]} "
    f"on {generic.seed()['fqdns'][0]}?"
)


def found(text: str) -> list[str]:
    low = text.lower()
    return [v for v in SEED if v.lower() in low or json.dumps(v).strip('"').lower() in low]


def without(reply: dict[str, Any], *keys: str) -> str:
    return json.dumps({k: v for k, v in reply.items() if k not in keys}, ensure_ascii=False)


def clean(out: Cli, *allowed: str) -> None:
    assert out.stderr == "", "the engine writes nothing to stderr"
    try:
        body = json.loads(out.stdout)
    except ValueError:
        assert found(out.stdout) == []
        return
    shown = without(body, *allowed) if isinstance(body, dict) else out.stdout
    assert found(shown) == [], "a real value reached the output"


def pairs(out: Cli) -> None:
    """No stand-in appears next to its real value outside the table."""
    body = json.loads(out.stdout)
    shown = without(body, "table", "args")
    assert "real" not in shown


@pytest.fixture
def seeded(home: Path, cli):  # type: ignore[no-untyped-def]
    assert cli("begin", "--session", SID, "--servers", "generic").code == 0
    return cli


def call(cli, *args: str, stdin: Any = None) -> Cli:  # type: ignore[no-untyped-def]
    return cli(*args, stdin=json.dumps(stdin) if stdin is not None else None)


def test_every_subcommand_succeeds_without_printing_a_value(
    seeded, home: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    cli = seeded
    outputs = []
    for tool in ("list_devices", "get_config", "get_logs", "keyed"):
        out = call(
            cli, "result", "--session", SID, "--server", "generic", "--tool", tool,
            stdin={"result": generic.TOOLS[tool](), "is_error": False},
        )  # fmt: skip
        assert out.code == 0
        clean(out, "table")
        pairs(out)
        outputs.append(out)

    learned = call(
        cli, "learn", "--session", SID, "--server", "generic", "--tool", "list_devices",
        stdin={"result": generic.TOOLS["list_devices"]()},
    )  # fmt: skip
    assert learned.code == 0
    clean(learned)

    prompt = call(cli, "prompt", "--session", SID, stdin={"text": REAL_TEXT})
    assert prompt.code == 0
    clean(prompt, "table")
    pairs(prompt)
    assert prompt.json["text"] != REAL_TEXT

    command = call(cli, "prompt", "--session", SID, "--command", stdin={"text": REAL_TEXT})
    assert command.code == 0
    clean(command)

    table = cli("table", "--session", SID, "--since", "0")
    assert table.code == 0 and table.json["table"]["entries"]  # values only here

    standin = next(e["standin"] for e in table.json["table"]["entries"] if e["kind"] == "IP")
    args = call(
        cli, "args", "--session", SID, "--server", "generic", "--tool", "t",
        stdin={"args": {"host": standin, "note": generic.seed()["ips"][1]}},
    )  # fmt: skip
    assert args.code == 0
    clean(args, "table", "args")

    observed = call(cli, "observe", "--session", SID, stdin={"text": f"try {standin}"})
    assert observed.code == 0
    clean(observed, "table")

    warm = cli("warmup", "--session", SID, "--server", "generic", "--state", "complete")
    assert warm.code == 0
    clean(warm)

    status = cli("status", "--session", SID, "--servers", "generic")
    assert status.code == 0
    clean(status)

    profile = tmp_path / "p.toml"
    profile.write_text(
        '[profile]\nid = "x"\nversion = 1\nservers = ["x"]\n'
        f"[vocabulary]\nvalues = [{json.dumps(generic.seed()['ips'][0])}]\n",
        encoding="utf-8",
    )
    checked = cli("check-profile", str(profile))
    assert checked.code == 0 and checked.json["valid"] is False
    clean(checked)

    revealed = cli("reveal", "--session", SID, stdin=prompt.json["text"])
    assert revealed.code == 0 and revealed.stderr == ""

    ended = cli("end", "--session", SID)
    assert ended.code == 0
    clean(ended)


def test_every_error_path_prints_no_value(home: Path, cli, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    real = generic.seed()["ips"][0]
    leaky_json = '{"text": "' + REAL_TEXT + '" '  # invalid JSON that holds real values
    big = {"content": [{"type": "text", "text": (real + " ok\n") * 400_000}], "isError": False}

    # exit 2: bad JSON, a missing field, a malformed session id, a bad argument
    cli("begin", "--session", SID, "--servers", "panos,generic")
    cases: list[tuple[int, Cli]] = [
        (2, cli("prompt", "--session", SID, stdin=leaky_json)),
        (
            2,
            call(
                cli, "result", "--session", SID, "--server", "g", "--tool", "t", stdin={"x": real}
            ),
        ),
        (2, cli("args", "--session", real, "--server", "g", "--tool", "t", stdin='{"args": {}}')),
        (2, cli("status", "--servers", real, "--bogus", real)),
        (2, call(cli, "observe", "--session", SID, stdin={"text": 5, "also": real})),
        # exit 3: the session does not exist or has ended
        (3, call(cli, "prompt", "--session", "gone", stdin={"text": REAL_TEXT})),
        (
            3,
            call(
                cli,
                "result",
                "--session",
                "gone",
                "--server",
                "g",
                "--tool",
                "t",
                stdin={"result": generic.TOOLS["get_logs"]()},
            ),
        ),  # fmt: skip
        (3, cli("reveal", "--session", "gone", stdin=REAL_TEXT)),
        # exit 4: warm-up pending (panos has one), begin on a live session, result too large
        (4, call(cli, "prompt", "--session", SID, stdin={"text": REAL_TEXT})),
        (4, cli("begin", "--session", SID, "--servers", "generic")),
        (
            4,
            call(
                cli,
                "result",
                "--session",
                SID,
                "--server",
                "generic",
                "--tool",
                "big",
                stdin={"result": big},
            ),
        ),  # fmt: skip
    ]
    for expected, out in cases:
        assert out.code == expected, out.stdout
        assert out.stderr == ""
        assert found(out.stdout) == [] and real not in out.stdout
        assert set(json.loads(out.stdout)) == {"error"}
        assert {"code", "message", "hint"} <= set(json.loads(out.stdout)["error"])

    # an ambiguous address in arguments (exit 4) names no address
    cli("begin", "--session", "amb", "--servers", "generic")
    from mcp_privacy_guard.config import resolve_home  # noqa: F401  (home comes from the env)
    from mcp_privacy_guard.standins import pseudonymize
    from mcp_privacy_guard.store import Store

    store = Store.open(home, "amb")
    standin = pseudonymize("IP", real, store, store.key)
    store.close()
    body = {"result": {"content": [{"type": "text", "text": standin}], "isError": False}}
    cli(
        "result",
        "--session",
        "amb",
        "--server",
        "x",
        "--tool",
        "t",
        "--exempt",
        stdin=json.dumps(body),
    )
    ambiguous = call(cli, "args", "--session", "amb", "--server", "g", "--tool", "t",
                     stdin={"args": {"h": standin}})  # fmt: skip
    assert ambiguous.code == 4
    assert standin not in ambiguous.stdout and real not in ambiguous.stdout


def test_an_internal_error_prints_no_value(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("MCP_PRIVACY_GUARD_HOME", str(home))
    assert engine_cli.main(["begin", "--session", SID, "--servers", "generic"]) == 0
    capsys.readouterr()

    def boom(*_a: Any, **_k: Any) -> None:
        raise RuntimeError(generic.seed()["ips"][0] + " " + generic.seed()["users"][0])

    monkeypatch.setattr(engine_cli, "translate", boom)
    import io
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"args": {"h": "x"}})))
    code = engine_cli.main(["args", "--session", SID, "--server", "g", "--tool", "t"])
    seen = capsys.readouterr()
    assert code == 5
    assert found(seen.out) == [] and found(seen.err) == []
    assert json.loads(seen.out)["error"]["code"] == "internal"
