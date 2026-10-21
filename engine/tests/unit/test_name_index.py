"""The known-names index used by the MIXED rule (research R4, R9)."""

from __future__ import annotations

from tests.conftest import KEY, OTHER_KEY

from mcp_privacy_guard.store import Store


def spans(store: Store, text: str) -> list[str]:
    return [text[s:e] for s, e in store.name_index().spans(text)]


def test_simple_names_match_whole_tokens_only() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("fw-paris-01", "NAME", "g", False)
    assert spans(store, "see fw-paris-01, then fw-paris-011 and xfw-paris-01") == ["fw-paris-01"]


def test_names_added_later_are_found_without_reloading() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("alpha", "NAME", "g", False)
    assert spans(store, "alpha beta") == ["alpha"]
    store.add_name("beta", "NAME", "g", False)
    assert spans(store, "alpha beta") == ["alpha", "beta"]


def test_common_words_are_not_names() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("system", "NAME", "g", True)
    assert spans(store, "the system works") == []


def test_names_with_spaces_or_dots_use_the_alternation_and_win_when_longer() -> None:
    store = Store.ephemeral(KEY)
    store.add_name("Allow Admin", "NAME", "g", False)
    store.add_name("Allow", "NAME", "g", False)
    store.add_name("web.v2", "NAME", "g", False)
    assert spans(store, "rule Allow Admin and web.v2 and Allow") == [
        "Allow Admin", "web.v2", "Allow",
    ]  # fmt: skip


def test_each_store_has_its_own_names() -> None:
    first, second = Store.ephemeral(KEY), Store.ephemeral(OTHER_KEY)
    first.add_name("only-here", "NAME", "g", False)
    assert spans(first, "only-here") == ["only-here"]
    assert spans(second, "only-here") == []
