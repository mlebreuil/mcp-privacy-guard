"""T045 (generic part): no seeded real value reaches the model (Story 1, SC-001)."""

from __future__ import annotations

import ipaddress as ia
import json
from typing import Any

import pytest
from tests.conftest import KEY, load_generic_results

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
generic = load_generic_results()
TOOLS = [name for name in generic.TOOLS if name != "big"]


def run(store: Store, name: str, server: str = "generic") -> dict[str, Any]:
    out = pseudonymize_result(
        generic.TOOLS[name](),
        store=store,
        profile=loader.load_bundled("default"),
        config=Config(),
        server=server,
        tool=name,
        is_error=name == "failing",
    )
    result: dict[str, Any] = out.result
    return result


def leaks(output: Any) -> list[str]:
    text = json.dumps(output, ensure_ascii=False).lower()
    # JSON escapes backslashes, so look for the escaped form as well
    return [
        v
        for v in generic.all_values()
        if v.lower() in text or json.dumps(v).strip('"').lower() in text
    ]


@pytest.mark.parametrize("tool", TOOLS)
def test_no_seeded_value_survives(tool: str) -> None:
    assert leaks(run(Store.ephemeral(KEY), tool)) == []


def test_the_whole_session_leaks_nothing() -> None:
    store = Store.ephemeral(KEY)
    assert leaks([run(store, tool) for tool in TOOLS]) == []


def test_the_default_profile_keeps_structure() -> None:
    out = run(Store.ephemeral(KEY), "list_devices")
    devices = out["structuredContent"]["devices"]
    assert len(devices) == 3 and out["structuredContent"]["count"] == 3
    assert devices[0]["port"] == 443 and devices[0]["last_seen"] == "2026-10-20T10:15:00Z"
    assert set(devices[0]) >= {"name", "hostname", "serial", "ip", "mac", "owner", "description"}


def test_same_value_same_stand_in_across_tools_and_servers_but_not_across_values() -> None:
    store = Store.ephemeral(KEY)
    first = run(store, "list_devices", "generic")
    second = run(store, "keyed", "other-server")
    stand_in = store.lookup_real("IP", "10.1.2.15")["standin"]  # type: ignore[index]
    assert stand_in in json.dumps(first) and stand_in in json.dumps(second)
    for tool in TOOLS:
        run(store, tool)
    reals = [r for r in generic.seed()["ips"] if store.lookup_real("IP", r)]
    assert len(reals) >= 4
    stand_ins = {store.lookup_real("IP", r)["standin"] for r in reals}  # type: ignore[index]
    assert len(stand_ins) == len(reals)


def test_a_network_contains_the_stand_in_of_its_hosts() -> None:
    store = Store.ephemeral(KEY)
    run(store, "list_devices")
    net = ia.ip_network(store.lookup_real("IP", "10.1.2.0/24")["standin"])  # type: ignore[index]
    host = ia.ip_address(store.lookup_real("IP", "10.1.2.15")["standin"])  # type: ignore[index]
    assert host in net


def test_a_new_session_gives_new_stand_ins() -> None:
    a, b = Store.ephemeral(KEY), Store.ephemeral(bytes(range(7, 39)))
    run(a, "list_devices")
    run(b, "list_devices")
    assert (
        a.lookup_real("IP", "10.1.2.15")["standin"] != b.lookup_real("IP", "10.1.2.15")["standin"]
    )  # type: ignore[index]


def test_a_failure_is_not_a_pass_through() -> None:
    from mcp_privacy_guard.errors import Refused

    with pytest.raises(Refused):
        pseudonymize_result(
            generic.TOOLS["big"](),
            store=Store.ephemeral(KEY),
            profile=loader.load_bundled("default"),
            config=Config(),
            server="generic",
            tool="big",
        )
