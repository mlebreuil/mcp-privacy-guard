"""T045 (panos-mcp part): no value of the recorded offline-demo results reaches the model."""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.conftest import (
    KEY,
    leaked,
    panos_fixtures,
    panos_real_values,
    panos_unchanged_by_design,
)

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
FIXTURES = panos_fixtures()
REAL = panos_real_values()


def profile(which: str) -> loader.Profile:
    if which == "panos-mcp":
        selected, state, _ = loader.select_profile("panos", None)
        assert selected.id == "panos-mcp" and state == "valid"  # the bundled profile applies
        return selected
    return loader.load_bundled("default")


def shown(store: Store, name: str, which: str) -> Any:
    fixture = FIXTURES[name]
    return pseudonymize_result(
        {k: v for k, v in fixture.items() if not k.startswith("_")},
        store=store,
        profile=profile(which),
        config=Config(),
        server="panos",
        tool=name.removesuffix("_with_users"),
        is_error=bool(fixture.get("isError")),
    ).result


def leaks(store: Store, output: Any) -> list[str]:
    return leaked(REAL, output, store, panos_unchanged_by_design())


def test_the_fixtures_were_recorded() -> None:
    assert len(FIXTURES) >= 14 and len(REAL) > 50


@pytest.mark.parametrize("which", ["panos-mcp", "default"])
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_real_value_survives(name: str, which: str) -> None:
    store = Store.ephemeral(KEY)
    assert leaks(store, shown(store, name, which)) == []


@pytest.mark.parametrize("which", ["panos-mcp", "default"])
def test_a_whole_session_leaks_nothing_and_stays_consistent(which: str) -> None:
    store = Store.ephemeral(KEY)
    outputs = [shown(store, name, which) for name in sorted(FIXTURES)]
    assert leaks(store, outputs) == []
    # the same real value has one stand-in however many tools return it
    first = store.lookup_real("IP", "10.20.1.10")
    assert first is not None
    assert sum(first["standin"] in json.dumps(o) for o in outputs) >= 2
