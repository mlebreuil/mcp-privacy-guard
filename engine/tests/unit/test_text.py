"""T043: the MIXED rule for free text and plain-text lines."""

from __future__ import annotations

import re

from tests.conftest import KEY

from mcp_privacy_guard.classify.text import hide_block, mixed
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.store import Store

TEXT = re.compile(r"^text-[a-z2-7]{8}$")


def run(text: str, store: Store | None = None, config: Config | None = None) -> str:
    return mixed(
        text,
        store=store or Store.ephemeral(KEY),
        profile=loader.load_bundled("default"),
        config=config or Config(),
        server="gen",
    )


def test_embedded_shapes_are_replaced_in_place() -> None:
    out = run("Connection from 10.1.2.15 to app.corp.example.com was not allowed")
    assert "10.1.2.15" not in out and "app.corp.example.com" not in out
    assert out.startswith("Connection from 10.") and out.endswith("was not allowed")


def test_text_with_only_known_words_is_kept() -> None:
    assert run("The connection was not found") == "The connection was not found"
    assert run("") == ""


def test_known_names_are_replaced_in_place() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("web-srv-01", "RULE_NAME", "gen", False)
    out = run("Object web-srv-01 not found", store)
    assert re.fullmatch(r"Object n-[a-z2-7]{6} not found", out)


def test_an_unknown_word_hides_the_whole_unit() -> None:
    out = run("Object web-srv-01 not found")
    assert TEXT.match(out)
    assert run("Object web-srv-01 not found") == out  # deterministic
    assert TEXT.match(run("user jdoe opened the payroll workbook from laptop LAP-PARIS-0042"))


def test_a_name_that_is_a_common_word_is_not_replaced_inside_text() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("web", "ZONE", "gen", True)
    assert run("web traffic was not found", store) == "web traffic was not found"


def test_hide_list_values_hide_the_unit() -> None:
    assert TEXT.match(run("the connection was not found", config=Config(hide_values=("found",))))


def test_whole_mode_hides_a_block() -> None:
    block = "line one\nline two"
    out = hide_block(block, store=Store.ephemeral(KEY))
    assert TEXT.match(out) and out != block
