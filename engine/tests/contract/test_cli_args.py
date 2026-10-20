"""The `args` subcommand envelope (contracts/engine-cli.md), as the plugin calls it."""

from __future__ import annotations

import json

from tests.conftest import load_generic_results

generic = load_generic_results()


def begin_and_issue(cli) -> dict:  # type: ignore[no-untyped-def, type-arg]
    assert cli("begin", "--session", "s1", "--servers", "generic").code == 0
    stdin = json.dumps({"result": generic.list_devices(), "is_error": False})
    table = cli("result", "--session", "s1", "--server", "generic", "--tool", "t", stdin=stdin)
    return {e["real"]: e["standin"] for e in table.json["table"]["entries"]}


def args_cmd(cli, payload, *extra: str):  # type: ignore[no-untyped-def]
    return cli(
        "args", "--session", "s1", "--server", "generic", "--tool", "t", *extra,
        stdin=json.dumps(payload),
    )  # fmt: skip


def test_args_translates_and_counts_values(cli) -> None:  # type: ignore[no-untyped-def]
    issued = begin_and_issue(cli)
    out = args_cmd(
        cli, {"args": {"name": issued["fw-paris-01"], "limit": 5, "ip": issued["10.1.2.15"]}}
    )
    assert out.code == 0
    data = out.json
    assert set(data) == {"args", "translated", "table"}
    assert data["args"] == {"name": "fw-paris-01", "limit": 5, "ip": "10.1.2.15"}
    assert data["translated"] == 2


def test_unknown_stand_ins_are_passed_as_typed_and_not_reported(cli) -> None:  # type: ignore[no-untyped-def]
    begin_and_issue(cli)
    out = args_cmd(cli, {"args": {"name": "n-zzzzzz"}})
    assert (
        out.code == 0 and out.json["args"] == {"name": "n-zzzzzz"} and out.json["translated"] == 0
    )
    assert "unknown" not in out.stdout.lower()


def test_since_limits_the_table_entries(cli) -> None:  # type: ignore[no-untyped-def]
    begin_and_issue(cli)
    out = args_cmd(cli, {"args": {}}, "--since", "0")
    assert out.json["table"]["entries"]  # the whole table after revision 0
    rev = out.json["table"]["rev"]
    assert args_cmd(cli, {"args": {}}, "--since", str(rev)).json["table"]["entries"] == []


def test_invalid_stdin_exits_2(cli) -> None:  # type: ignore[no-untyped-def]
    begin_and_issue(cli)
    for stdin in ("nope", "[]", json.dumps({"no": "args"}), json.dumps({"args": "x"})):
        out = cli("args", "--session", "s1", "--server", "generic", "--tool", "t", stdin=stdin)
        assert out.code == 2


def test_without_a_session_exits_3(cli, home) -> None:  # type: ignore[no-untyped-def]
    out = args_cmd(cli, {"args": {"a": "b"}})
    assert out.code == 3 and not home.exists()
