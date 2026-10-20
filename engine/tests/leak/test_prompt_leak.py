"""T065 and T105: no real value of a question reaches the model, and every stand-in matches
the one tool results use (SC-007). Slash-command arguments and skill text go through the same
engine call, so they are covered here too."""

from __future__ import annotations

import pytest
from tests.conftest import (
    KEY,
    leaked,
    load_generic_results,
    panos_fixtures,
    panos_real_values,
)

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.prompts import pseudonymize_prompt
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

pytestmark = pytest.mark.leak
generic = load_generic_results()
SEED = generic.seed()
# the categories a question can carry (spec Story 3): shapes and known names
GENERIC_CATEGORIES = ["ips", "networks", "fqdns", "urls", "devices", "serials", "users",
                      "groups", "emails", "macs", "objects"]  # fmt: skip


def session() -> Store:
    """A session after the tool results of both reference servers went through."""
    store = Store.ephemeral(KEY)
    for name, build in generic.TOOLS.items():
        if name != "big":
            pseudonymize_result(
                build(), store=store, profile=loader.load_bundled("default"), config=Config(),
                server="generic", tool=name, is_error=name == "failing",
            )  # fmt: skip
    profile, _, _ = loader.select_profile("panos", None)
    for name, fixture in panos_fixtures().items():
        pseudonymize_result(
            {k: v for k, v in fixture.items() if not k.startswith("_")},
            store=store, profile=profile, config=Config(), server="panos",
            tool=name.removesuffix("_with_users"),
        )  # fmt: skip
    return store


STORE = session()
VALUES = [v for cat in GENERIC_CATEGORIES for v in SEED[cat]] + panos_real_values()
# a name that is a plain English word is replaced only when it is quoted
COMMON = {r["real"] for r in STORE.names() if r["common_word"]}


def sentence(value: str) -> str:
    shown = f"'{value}'" if value in COMMON else value
    return f"why is {shown} blocked when it goes to the firewall?"


def run(text: str):  # type: ignore[no-untyped-def]
    return pseudonymize_prompt(text, store=STORE, config=Config())


@pytest.mark.parametrize("value", sorted(set(VALUES)))
def test_a_question_leaks_nothing(value: str) -> None:
    out = run(sentence(value))
    assert leaked([value], out.text, STORE) == []


def test_every_replacement_is_the_stand_in_results_use() -> None:
    for value in sorted(set(VALUES)):
        out = run(sentence(value))
        assert out.replacements, value
        for r in out.replacements:
            known = STORE.lookup_standin(r["standin"])
            assert known is not None and known["real"] == sentence(value)[
                r["start"] : r["end"]
            ].strip("'")


def test_one_big_question_with_every_category() -> None:
    text = "check " + ", ".join(sorted(f"'{v}'" if v in COMMON else v for v in set(VALUES)))
    assert leaked(VALUES, run(text).text, STORE) == []


# -- slash-command arguments and skill text (T105) ----------------------------------------


@pytest.mark.parametrize("value", sorted(set(VALUES))[::7])
def test_command_arguments_and_skill_text_leak_nothing(value: str) -> None:
    shown = f"'{value}'" if value in COMMON else value
    for text in (f"{shown} --verbose", f"Please review the change on {shown} and report."):
        assert leaked([value], run(text).text, STORE) == []
