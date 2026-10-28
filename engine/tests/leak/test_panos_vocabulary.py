"""T046: with the panos-mcp profile, PAN-OS vocabulary passes unchanged (Story 1 scenario 6)."""

from __future__ import annotations

import json

import pytest
from tests.conftest import KEY, panos_fixtures

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
FIXTURES = panos_fixtures()
KEPT = ["any", "application-default", "web-browsing", "ssl", "dns", "allow", "deny", "tcp"]


def run(name: str) -> str:
    profile, _, _ = loader.select_profile("panos", None)
    assert profile.id == "panos-mcp"
    fixture = {k: v for k, v in FIXTURES[name].items() if not k.startswith("_")}
    out = pseudonymize_result(
        fixture, store=Store.ephemeral(KEY), profile=profile, config=Config(),
        server="panos", tool=name, is_error=False,
    )  # fmt: skip
    return json.dumps(out.result["structuredContent"])


@pytest.mark.parametrize("word", KEPT)
def test_vocabulary_value_is_not_replaced(word: str) -> None:
    quoted = json.dumps(word)
    for name, fixture in FIXTURES.items():
        before = json.dumps(fixture.get("structuredContent")).count(quoted)
        if before:
            assert run(name).count(quoted) == before, name


def test_numbers_and_timestamps_are_unchanged() -> None:
    items = json.loads(run("query_logs"))["items"]
    assert items[0]["dport"] == 443
    assert items[0]["receive_time"] == "2026-10-16T08:59:41"


def test_ha_states_of_a_firewall_pair_stay_readable() -> None:
    # live check 3: `ha` is an object, and `passive` came back as a stand-in
    profile, _, _ = loader.select_profile("panos", None)
    pair = {"structuredContent": {"items": [
        {"serial": "735312590148", "ha": {"local_state": "passive", "peer_serial": "961112851052"}},
        {"serial": "961112851052", "ha": {"local_state": "active", "peer_state": "suspended"}},
    ]}}  # fmt: skip
    out = pseudonymize_result(
        pair, store=Store.ephemeral(KEY), profile=profile, config=Config(),
        server="panos", tool="list_managed_devices", is_error=False,
    )  # fmt: skip
    first, second = out.result["structuredContent"]["items"]
    assert first["ha"]["local_state"] == "passive"
    assert second["ha"]["local_state"] == "active"
    assert second["ha"]["peer_state"] == "suspended"
    assert first["serial"] != "735312590148"  # identifying values are still replaced
    assert first["ha"]["peer_serial"] != "961112851052"
