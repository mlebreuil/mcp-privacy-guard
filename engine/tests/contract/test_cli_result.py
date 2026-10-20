"""The `result` subcommand envelope (contracts/engine-cli.md), as the plugin calls it."""

from __future__ import annotations

import json

from tests.conftest import load_generic_results

generic = load_generic_results()


def begin(cli) -> None:  # type: ignore[no-untyped-def]
    assert cli("begin", "--session", "s1", "--servers", "generic").code == 0


def result_args(*extra: str) -> list[str]:
    return ["result", "--session", "s1", "--server", "generic", "--tool", "list_devices", *extra]


def test_result_pseudonymizes_and_carries_the_table(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    stdin = json.dumps({"result": generic.list_devices(), "is_error": False})
    out = cli(*result_args("--since", "0"), stdin=stdin)
    assert out.code == 0
    data = out.json
    assert set(data) == {"result", "withheld", "notices", "table"}
    assert data["withheld"] == 0 and data["notices"] == []
    # the table holds real values for the plugin; the result is what the model reads
    assert not any(v in json.dumps(data["result"]) for v in generic.all_values())
    table = data["table"]
    assert table["rev"] > 0 and table["entries"]
    assert {"standin", "real", "kind"} <= set(table["entries"][0])


def test_since_limits_the_table_entries(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    stdin = json.dumps({"result": generic.get_logs(), "is_error": False})
    first = cli(*result_args("--since", "0"), stdin=stdin).json["table"]
    again = cli(*result_args("--since", str(first["rev"])), stdin=stdin).json["table"]
    assert again["entries"] == [] and again["rev"] == first["rev"]


def test_invalid_stdin_exits_2(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    for stdin in ("not json", "[]", json.dumps({"no": "result"})):
        out = cli(*result_args(), stdin=stdin)
        assert out.code == 2 and out.json["error"]["code"]


def test_a_result_that_is_too_large_exits_4(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    out = cli(*result_args(), stdin=json.dumps({"result": generic.big(), "is_error": False}))
    assert out.code == 4 and out.json["error"]["code"] == "too-large"
    assert "10.1.2.15" not in out.stdout and "10.1.2.15" not in out.stderr


def test_without_a_session_exits_3(cli, home) -> None:  # type: ignore[no-untyped-def]
    stdin = json.dumps({"result": generic.get_logs(), "is_error": False})
    out = cli(*result_args(), stdin=stdin)
    assert out.code == 3 and out.json["error"]["code"] == "session-missing"
    assert not home.exists()
