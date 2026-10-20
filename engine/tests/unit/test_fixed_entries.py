"""T090: values that reach the model unchanged and can come back (research R15)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import Cli

from mcp_privacy_guard.standins import ip, pseudonymize
from mcp_privacy_guard.store import Store

SID = "s-fixed"


def configure(home: Path, keep: list[str] | None = None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    values = json.dumps(keep or [])
    (home / "config.toml").write_text(
        f"[keep]\nvalues = {values}\n[servers.exempt]\nexempt = true\n", encoding="utf-8"
    )


def begin(cli, servers: str = "gen,exempt") -> Cli:  # type: ignore[no-untyped-def]
    return cli("begin", "--session", SID, "--servers", servers)


def call_args(cli, text: str) -> Cli:  # type: ignore[no-untyped-def]
    return cli(
        "args", "--session", SID, "--server", "gen", "--tool", "t",
        stdin=json.dumps({"args": {"q": text}}),
    )  # fmt: skip


def exempt_result(cli, text: str) -> Cli:  # type: ignore[no-untyped-def]
    body = {"result": {"content": [{"type": "text", "text": text}], "isError": False}}
    return cli(
        "result", "--session", SID, "--server", "exempt", "--tool", "t", "--exempt",
        stdin=json.dumps(body),
    )  # fmt: skip


def test_begin_records_ip_shaped_keep_values_as_fixed(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home, ["8.8.8.8", "1.1.1.0/24", "Contoso"])
    assert begin(cli).code == 0
    table = cli("table", "--session", SID, "--since", "0").json["table"]["entries"]
    assert {(e["standin"], e["real"]) for e in table} == {
        ("8.8.8.8", "8.8.8.8"), ("1.1.1.0/24", "1.1.1.0/24"),
    }  # fmt: skip
    store = Store.open(home, SID)
    row = store.lookup_standin("8.8.8.8")
    assert row is not None and row["fixed"] is True


def test_result_exempt_records_ip_forms_and_echoes_nothing(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home)
    begin(cli)
    out = exempt_result(cli, "dns 9.9.9.9, gw 10.7.7.7, net 10.7.7.0/24")
    assert out.code == 0 and out.json == {"fixed": 3}
    assert "9.9.9.9" not in out.stdout
    table = cli("table", "--session", SID, "--since", "0").json["table"]["entries"]
    assert {e["standin"] for e in table} == {"9.9.9.9", "10.7.7.7", "10.7.7.0/24"}
    assert all(e["standin"] == e["real"] for e in table)


def test_args_passes_a_fixed_ip_unchanged_and_still_inverts_stand_ins(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home, ["8.8.8.8"])
    begin(cli)
    exempt_result(cli, "gw 10.7.7.7")
    store = Store.open(home, SID)
    standin = pseudonymize("IP", "10.1.2.15", store, store.key)
    store.close()
    out = call_args(cli, f"8.8.8.8 10.7.7.7 {standin}")
    assert out.code == 0
    assert out.json["args"]["q"] == "8.8.8.8 10.7.7.7 10.1.2.15"
    assert out.json["translated"] == 1


def test_an_ip_both_fixed_and_issued_is_ambiguous(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home)
    begin(cli)
    store = Store.open(home, SID)
    standin = pseudonymize("IP", "10.1.2.15", store, store.key)
    store.close()
    assert exempt_result(cli, f"seen {standin}").code == 0  # a real address equal to a stand-in
    out = call_args(cli, standin)
    assert out.code == 4 and out.json["error"]["code"] == "ambiguous-address"
    assert standin not in out.stdout and "10.1.2.15" not in out.stdout


def test_a_real_ip_whose_stand_in_is_a_fixed_keep_value_becomes_text(home: Path) -> None:
    key = bytes(range(32))
    real = "10.1.2.15"
    clash = ip.permute(key, real)
    store = Store.ephemeral(key)
    store.issue("FIXED", clash, clash, fixed=True)
    out = pseudonymize("IP", real, store, key)
    assert out != clash and out.startswith("text-")
    assert pseudonymize("IP", real, store, key) == out


def test_observe_does_not_invert_fixed_ips(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home, ["8.8.8.8"])
    begin(cli)
    before = cli("table", "--session", SID, "--since", "0").json["table"]["rev"]
    out = cli("observe", "--session", SID, "--since", str(before), stdin='{"text": "8.8.8.8"}')
    assert out.json["table"]["entries"] == []


def test_reveal_shows_a_fixed_ip_as_itself(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home, ["8.8.8.8"])
    begin(cli)
    assert cli("reveal", "--session", SID, stdin="dns 8.8.8.8").stdout.strip() == "dns 8.8.8.8"


def test_reveal_marks_an_ambiguous_address(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    configure(home)
    begin(cli)
    store = Store.open(home, SID)
    standin = pseudonymize("IP", "10.1.2.15", store, store.key)
    store.close()
    exempt_result(cli, standin)
    out = cli("reveal", "--session", SID, stdin=standin)
    assert out.stdout.strip() == f"{standin}⟨?⟩"
