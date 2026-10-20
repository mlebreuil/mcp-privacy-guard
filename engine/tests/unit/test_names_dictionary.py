"""T062: the session's name dictionary (research R9)."""

from __future__ import annotations

import json
from typing import Any

from tests.conftest import KEY, load_generic_results

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

generic = load_generic_results()


def process(
    store: Store, result: dict[str, Any], server: str = "gen", profile: str = "default"
) -> None:
    pseudonymize_result(
        result,
        store=store,
        profile=loader.load_bundled(profile),
        config=Config(),
        server=server,
        tool="t",
    )


def text(body: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(body)}], "isError": False}


def rows(store: Store) -> dict[str, dict[str, Any]]:
    return {r["real"]: r for r in store.names()}


def test_names_users_and_groups_are_recorded_with_server_and_kind() -> None:
    store = Store.ephemeral(KEY)
    process(
        store, text({"host": "fw-paris-01", "admin": "CORP\\jdoe", "group": "web-farm"}), "srv-a"
    )
    known = rows(store)
    assert known["fw-paris-01"]["kind"] == "NAME" and known["fw-paris-01"]["server"] == "srv-a"
    assert known["CORP\\jdoe"]["kind"] == "USER"
    assert known["web-farm"]["server"] == "srv-a"


def test_a_profile_name_kind_is_recorded_as_its_kind() -> None:
    store = Store.ephemeral(KEY)
    profile, _, _ = loader.select_profile("panos", None)
    pseudonymize_result(
        text({"items": [{"name": "Allow-Admin-Web"}]}),
        store=store,
        profile=profile,
        config=Config(),
        server="panos",
        tool="get_security_rules",
    )
    assert rows(store)["Allow-Admin-Web"]["kind"] == "RULE_NAME"


def test_values_that_are_not_names_are_not_recorded() -> None:
    store = Store.ephemeral(KEY)
    process(store, text({"ip": "10.1.2.15", "host": "app.corp.example.com", "port": 443,
                         "state": "allow", "when": "2026-10-20T10:15:00Z"}))  # fmt: skip
    assert store.names() == []


def test_common_word_names_are_flagged() -> None:
    store = Store.ephemeral(KEY)
    process(store, text({"zone": "web", "other": "fw-paris-01"}))
    known = rows(store)
    assert known["web"]["common_word"] == 1 or known["web"]["common_word"] is True
    assert not known["fw-paris-01"]["common_word"]


def test_the_same_name_on_two_servers_keeps_one_row_per_kind() -> None:
    store = Store.ephemeral(KEY)
    process(store, text({"a": "fw-paris-01"}), "one")
    process(store, text({"a": "fw-paris-01"}), "two")
    assert len([r for r in store.names() if r["real"] == "fw-paris-01"]) == 1


def test_a_new_session_starts_with_an_empty_dictionary() -> None:
    first, second = Store.ephemeral(KEY), Store.ephemeral(KEY)
    process(first, text({"a": "fw-paris-01"}))
    assert first.names() and second.names() == []


def test_object_keys_that_are_names_are_recorded() -> None:
    store = Store.ephemeral(KEY)
    process(store, text({"fw-paris-01": {"state": "up"}}))
    assert "fw-paris-01" in rows(store)


def test_the_generic_results_fill_the_dictionary() -> None:
    store = Store.ephemeral(KEY)
    process(store, generic.list_devices())
    known = rows(store)
    for name in generic.seed()["devices"]:
        assert name in known
