"""T057: every stand-in a result gave the model translates back to its real value (SC-003)."""

from __future__ import annotations

import pytest
from tests.conftest import KEY, load_generic_results, panos_fixtures

from mcp_privacy_guard.arguments import translate
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
generic = load_generic_results()
FIXTURES = panos_fixtures()


def process_everything(store: Store) -> None:
    for name, build in generic.TOOLS.items():
        if name == "big":
            continue
        for server in ("generic", "second-alias"):
            pseudonymize_result(
                build(),
                store=store,
                profile=loader.load_bundled("default"),
                config=Config(),
                server=server,
                tool=name,
                is_error=name == "failing",
            )
    profile, _, _ = loader.select_profile("panos", None)
    for name, fixture in FIXTURES.items():
        pseudonymize_result(
            {k: v for k, v in fixture.items() if not k.startswith("_")},
            store=store,
            profile=profile,
            config=Config(),
            server="panos",
            tool=name.removesuffix("_with_users"),
        )


def test_every_issued_stand_in_translates_back() -> None:
    store = Store.ephemeral(KEY)
    process_everything(store)
    _, entries = store.table(0)
    assert len(entries) > 150
    wrong = [
        e["kind"]
        for e in entries
        if translate({"v": e["standin"]}, store=store).args["v"] != e["real"]
    ]
    assert wrong == []


def test_the_same_holds_inside_a_filter_string() -> None:
    store = Store.ephemeral(KEY)
    process_everything(store)
    _, entries = store.table(0)
    names = [e for e in entries if e["kind"] in {"NAME", "IP", "FQDN"}][:150]
    for entry in names:
        filtered = translate({"f": f"(x eq '{entry['standin']}') and y"}, store=store).args["f"]
        assert filtered == f"(x eq '{entry['real']}') and y", entry["kind"]


def test_an_unrelated_name_stays_untouched_after_the_whole_session() -> None:
    store = Store.ephemeral(KEY)
    process_everything(store)
    assert translate({"v": "n-zzzzzz"}, store=store).args == {"v": "n-zzzzzz"}
