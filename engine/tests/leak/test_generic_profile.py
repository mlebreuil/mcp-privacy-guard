"""T081: a profile makes results more readable without leaking (FR-014, analysis H3, Story 5)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from tests.conftest import KEY, ROOT, load_generic_results

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.profiles.loader import ProfileError
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
generic = load_generic_results()
TOOLS = [name for name in generic.TOOLS if name != "big"]
EXAMPLE = ROOT / "testservers" / "generic" / "profile.example.toml"


def run(store: Store, name: str, profile: loader.Profile) -> dict[str, Any]:
    out = pseudonymize_result(
        generic.TOOLS[name](),
        store=store,
        profile=profile,
        config=Config(),
        server="generic",
        tool=name,
        is_error=name == "failing",
    )
    result: dict[str, Any] = out.result
    return result


def leaks(output: Any) -> list[str]:
    text = json.dumps(output, ensure_ascii=False).lower()
    return [
        v
        for v in generic.all_values()
        if v.lower() in text or json.dumps(v).strip('"').lower() in text
    ]


def names_in(output: Any) -> int:
    return len(re.findall(r"\bn-[a-z2-7]{6,}\b", json.dumps(output)))


def test_the_example_profile_is_valid() -> None:
    profile = loader.load_file(EXAMPLE)
    assert profile.applies_to("generic")


def test_no_seed_value_leaks_with_the_profile() -> None:
    profile = loader.load_file(EXAMPLE)
    store = Store.ephemeral(KEY)
    assert leaks([run(store, tool, profile) for tool in TOOLS]) == []


def test_the_profile_gives_fewer_name_stand_ins_than_the_default() -> None:
    profile = loader.load_file(EXAMPLE)
    default = loader.load_bundled("default")
    tools = ["list_devices", "get_config"]
    with_profile = names_in([run(Store.ephemeral(KEY), t, profile) for t in tools])
    without = names_in([run(Store.ephemeral(KEY), t, default) for t in tools])
    assert with_profile < without


def test_a_profile_listing_shape_identifying_values_is_refused() -> None:
    head = '[profile]\nid = "x"\nversion = 1\nservers = ["generic"]\n'
    for body in (
        '[vocabulary]\nvalues = ["fw-paris-01", "app.corp.example.com"]',
        '[[fields]]\npath = "a"\nenum = ["10.1.2.15"]',
    ):
        with pytest.raises(ProfileError) as err:
            loader.load_profile(head + body)
        assert err.value.reason == "identifying-vocabulary"


def test_keys_keep_still_hides_identifying_keys() -> None:
    profile = loader.load_file(EXAMPLE)
    out = run(Store.ephemeral(KEY), "keyed", profile)
    assert leaks(out) == []
    data = json.loads(out["content"][0]["text"])
    assert "summary" in data  # the plain key is kept
    real_keys = {*generic.seed()["fqdns"], *generic.seed()["ips"]}
    assert not real_keys & set(data)
