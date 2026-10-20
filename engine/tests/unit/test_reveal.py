"""T074: reveal and observe (FR-021-FR-023, research R10)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import Cli

from mcp_privacy_guard.standins import ip, pseudonymize
from mcp_privacy_guard.store import Store

SID = "s-reveal"


def seeded(home: Path, sid: str = SID) -> tuple[dict[str, str], bytes]:
    store = Store.begin(home, sid)
    try:
        issued = {
            "name": pseudonymize("RULE_NAME", "Allow-Admin-Web", store, store.key),
            "ip": pseudonymize("IP", "10.1.2.15", store, store.key),
            "fqdn": pseudonymize("FQDN", "app.corp.example.com", store, store.key),
        }
        return issued, store.key
    finally:
        store.close()


def test_known_stand_ins_are_revealed_and_other_text_is_unchanged(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    text = f"Rule {issued['name']} allows {issued['ip']} to {issued['fqdn']}; 3 hits today."
    out: Cli = cli("reveal", "--session", SID, stdin=text)
    assert out.code == 0
    assert out.stdout.strip() == (
        "Rule Allow-Admin-Web allows 10.1.2.15 to app.corp.example.com; 3 hits today."
    )


def test_json_reports_counts_and_unknown_name_shaped_stand_ins(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    text = f"{issued['name']} and n-zzzzzzzz7q"
    out = cli("reveal", "--session", SID, "--json", stdin=text)
    assert out.code == 0
    assert out.json == {
        "text": "Allow-Admin-Web and n-zzzzzzzz7q⟨?⟩",
        "revealed": 1,
        "unknown": ["n-zzzzzzzz7q"],
    }


def test_stdin_may_be_a_json_object_with_text(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    out = cli("reveal", "--session", SID, stdin='{"text": "x ' + issued["name"] + '"}')
    assert out.stdout.strip() == "x Allow-Admin-Web"


def test_the_only_live_session_is_used_without_session(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    assert cli("reveal", stdin=issued["name"]).stdout.strip() == "Allow-Admin-Web"


def test_no_live_session_or_several_exits_3(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    seeded(home, "s-other")
    assert cli("reveal", stdin=issued["name"]).code == 3
    assert cli("end", "--session", SID).code == 0
    assert cli("end", "--session", "s-other").code == 0
    out = cli("reveal", "--session", SID, stdin=issued["name"])
    assert out.code == 3
    assert "Allow-Admin-Web" not in out.stdout
    assert cli("reveal", stdin=issued["name"]).code == 3


def test_a_stand_in_of_another_session_is_unknown(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    issued, _ = seeded(home)
    seeded(home, "s-other")
    out = cli("reveal", "--session", "s-other", "--json", stdin=issued["name"])
    assert out.json["revealed"] == 0
    assert out.json["unknown"] == [issued["name"]]


def test_observe_records_unissued_ip_forms_and_returns_new_entries(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    _, key = seeded(home)
    never_seen = ip.permute(key, "10.1.2.99")
    network = ip.permute(key, "10.1.2.0/24")
    base = cli("table", "--session", SID, "--since", "0").json["table"]["rev"]
    out = cli("observe", "--session", SID, "--since", str(base),
              stdin=f'{{"text": "try {never_seen} in {network}"}}')  # fmt: skip
    assert out.code == 0
    entries = {e["standin"]: e["real"] for e in out.json["table"]["entries"]}
    assert entries == {never_seen: "10.1.2.99", network: "10.1.2.0/24"}
    again = cli("observe", "--session", SID, "--since", str(out.json["table"]["rev"]),
                stdin=f'{{"text": "{never_seen}"}}')  # fmt: skip
    assert again.json["table"]["entries"] == []
    revealed = cli("reveal", "--session", SID, stdin=never_seen)
    assert revealed.stdout.strip() == "10.1.2.99"


def test_observe_without_session_or_text_is_bad_input(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    seeded(home)
    assert cli("observe", stdin="{}").code == 2
    assert cli("observe", "--session", SID, stdin="{}").code == 2
    assert cli("observe", "--session", "gone", stdin='{"text": "x"}').code == 3
