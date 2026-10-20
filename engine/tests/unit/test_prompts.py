"""T064: questions get the same stand-ins as results (FR-017, FR-018, research R9)."""

from __future__ import annotations

import json
import re
from typing import Any

from tests.conftest import KEY

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.prompts import identifying, pseudonymize_prompt
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.standins import pseudonymize
from mcp_privacy_guard.store import Store


def learn(store: Store, body: Any, server: str = "gen", profile: str = "default") -> None:
    pseudonymize_result(
        {"content": [{"type": "text", "text": json.dumps(body)}], "isError": False},
        store=store,
        profile=loader.load_bundled(profile),
        config=Config(),
        server=server,
        tool="t",
    )


def ask(store: Store, text: str) -> Any:
    return pseudonymize_prompt(text, store=store, config=Config())


def test_shapes_get_the_stand_ins_the_results_use() -> None:
    store = Store.ephemeral(KEY)
    values = {
        "IP": "10.1.2.15", "network": "10.1.2.0/24", "FQDN": "app.corp.example.com",
        "EMAIL": "jane@corp.example.com", "MAC": "00:1b:17:aa:bb:cc", "DIGITS": "007951000123456",
        "USER": "CORP\\jdoe", "URL": "https://intranet.corp.example.com:8443/hr?id=3",
    }  # fmt: skip
    for real in values.values():
        learn(store, {"v": real})
    for kind, real in values.items():
        out = ask(store, f"why is {real} blocked?")
        known = store.lookup_standin(out.text.removeprefix("why is ").removesuffix(" blocked?"))
        assert known is not None and known["real"] == real, kind
        assert real not in out.text


def test_a_value_typed_before_any_result_gets_the_stand_in_a_result_would() -> None:
    store = Store.ephemeral(KEY)
    typed = ask(store, "look at 10.1.2.15 please").text
    learn(store, {"ip": "10.1.2.15"})
    returned = store.lookup_real("IP", "10.1.2.15")["standin"]  # type: ignore[index]
    assert returned in typed


def test_a_known_name_is_replaced_whole_token_and_case_sensitive() -> None:
    store = Store.ephemeral(KEY)
    learn(store, {"host": "fw-paris-01"})
    standin = pseudonymize("NAME", "fw-paris-01", store, KEY)
    out = ask(store, "why is fw-paris-01 down? not FW-PARIS-01, fw-paris-010 or my-fw-paris-01")
    assert out.text == f"why is {standin} down? not FW-PARIS-01, fw-paris-010 or my-fw-paris-01"
    assert [r["reason"] for r in out.replacements] == ["name"]


def test_offsets_refer_to_the_text_as_typed() -> None:
    store = Store.ephemeral(KEY)
    learn(store, {"host": "fw-paris-01"})
    text = "from 10.1.2.15 to fw-paris-01 and 10.1.2.15 again"
    out = ask(store, text)
    assert [text[r["start"] : r["end"]] for r in out.replacements] == [
        "10.1.2.15", "fw-paris-01", "10.1.2.15",
    ]  # fmt: skip
    for r in out.replacements:
        assert {"start", "end", "kind", "standin", "reason"} <= set(r)
    assert out.replacements[0]["reason"] == "shape" and out.replacements[0]["kind"] == "IP"


def test_a_common_word_name_is_replaced_only_when_it_clearly_refers_to_an_item() -> None:
    store = Store.ephemeral(KEY)
    learn(store, {"zone": "web", "other": "fw-paris-01"})
    standin = pseudonymize("NAME", "web", store, KEY)
    assert ask(store, "show web traffic to the dmz").text == "show web traffic to the dmz"
    assert ask(store, "show the 'web' zone").text == f"show the '{standin}' zone"
    assert ask(store, "show the `web` zone").text == f"show the `{standin}` zone"
    assert ask(store, "show the server web now").text == f"show the server {standin} now"
    assert ask(store, "any rule for the web please").text == f"any rule for the {standin} please"
    assert ask(store, "any rule in the big web zone").text == "any rule in the big web zone"
    reasons = {
        text: [r["reason"] for r in ask(store, text).replacements]
        for text in ("show the 'web' zone", "show the server web now")
    }
    assert reasons == {
        "show the 'web' zone": ["name+quote"],
        "show the server web now": ["name+cue"],
    }


def test_a_profile_cue_word_counts_for_its_kind() -> None:
    store = Store.ephemeral(KEY)
    profile, _, _ = loader.select_profile("panos", None)
    pseudonymize_result(
        {
            "content": [{"type": "text", "text": json.dumps({"items": [{"name": "web"}]})}],
            "isError": False,
        },
        store=store,
        profile=profile,
        config=Config(),
        server="panos",
        tool="get_objects",
    )
    standin = pseudonymize("NAME", "web", store, KEY)
    assert ask(store, "the address web is wrong").text == f"the address {standin} is wrong"


def test_text_without_identifying_values_is_unchanged() -> None:
    store = Store.ephemeral(KEY)
    learn(store, {"host": "fw-paris-01"})
    out = ask(store, "show me the rules with action allow on port 443")
    assert out.text == "show me the rules with action allow on port 443" and out.replacements == []


def test_the_same_value_twice_gets_the_same_stand_in() -> None:
    store = Store.ephemeral(KEY)
    out = ask(store, "10.1.2.15 and 10.1.2.15")
    first, second = re.findall(r"[\d.]+", out.text)
    assert first == second and first != "10.1.2.15"


def test_identifying_reports_without_replacing_anything() -> None:
    store = Store.ephemeral(KEY)
    learn(store, {"host": "fw-paris-01"})
    before = store.rev()
    assert identifying("check fw-paris-01", store=store, config=Config()) is True
    assert identifying("check 10.1.2.15", store=store, config=Config()) is True
    assert identifying("check the rules", store=store, config=Config()) is False
    assert store.rev() == before
