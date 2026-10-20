"""T056: stand-ins in tool arguments become real values again (FR-011, FR-012, Story 2)."""

from __future__ import annotations

from typing import Any

from tests.conftest import KEY, OTHER_KEY

from mcp_privacy_guard.arguments import translate
from mcp_privacy_guard.standins import ip, pseudonymize
from mcp_privacy_guard.store import Store


def issue(store: Store, kind: str, real: str) -> str:
    return pseudonymize(kind, real, store, KEY)


def run(store: Store, args: dict[str, Any]) -> tuple[dict[str, Any], int]:
    out = translate(args, store=store)
    return out.args, out.translated


def test_an_issued_name_becomes_the_real_name() -> None:
    store = Store.ephemeral(KEY)
    standin = issue(store, "RULE_NAME", "Allow-Admin-Web")
    assert run(store, {"name": standin}) == ({"name": "Allow-Admin-Web"}, 1)


def test_ip_forms_are_inverted_with_the_session_key_issued_or_not() -> None:
    store = Store.ephemeral(KEY)
    issued = issue(store, "IP", "10.1.2.15")
    never_seen = ip.permute(KEY, "10.1.2.99")
    network = ip.permute(KEY, "10.1.2.0/24")
    span = ip.permute(KEY, "10.1.2.1-10.1.2.50")
    wildcard = ip.permute(KEY, "10.1.*.*")
    out, count = run(
        store,
        {
            "a": issued,
            "b": never_seen,
            "c": network,
            "d": span,
            "e": wildcard,
            "f": "255.255.255.0",
        },
    )
    assert out == {
        "a": "10.1.2.15", "b": "10.1.2.99", "c": "10.1.2.0/24", "d": "10.1.2.1-10.1.2.50",
        "e": "10.1.*.*", "f": "255.255.255.0",
    }  # fmt: skip
    assert count == 5


def test_stand_ins_of_other_kinds_go_through_the_session_table() -> None:
    store = Store.ephemeral(KEY)
    reals = {
        "FQDN": "app.corp.example.com",
        "EMAIL": "jane@corp.example.com",
        "USER": "CORP\\jdoe",
        "GROUP": "CORP\\net-admins",
        "URL": "https://intranet.corp.example.com:8443/hr?id=3",
        "TEXT": "Gateway of the Paris office",
        "MAC": "00:1b:17:aa:bb:cc",
        "DIGITS": "007951000123456",
    }
    args = {kind: issue(store, kind, real) for kind, real in reals.items()}
    out, count = run(store, args)
    assert out == reals and count == len(reals)


def test_a_parent_domain_seen_inside_a_child_translates() -> None:
    store = Store.ephemeral(KEY)
    child = issue(store, "FQDN", "app.corp.example.com")
    parent = child.split(".", 1)[1]
    assert run(store, {"d": parent})[0] == {"d": "corp.example.com"}


def test_mixed_strings_translate_each_stand_in_and_keep_the_rest() -> None:
    store = Store.ephemeral(KEY)
    name = issue(store, "RULE_NAME", "Allow-Admin-Web")
    addr = issue(store, "IP", "10.1.2.15")
    host = issue(store, "FQDN", "app.corp.example.com")
    text = f"(addr.src in {addr}) and (rule eq '{name}') or host = {host}; port eq 443"
    out, count = run(store, {"filter": text})
    assert out["filter"] == (
        "(addr.src in 10.1.2.15) and (rule eq 'Allow-Admin-Web') or host = app.corp.example.com;"
        " port eq 443"
    )
    assert count == 3


def test_an_unknown_name_stand_in_is_left_as_typed() -> None:
    store = Store.ephemeral(KEY)
    issue(store, "NAME", "known")
    out, count = run(store, {"a": "n-zzzzzz", "b": "show n-zzzzzz and text-zzzzzzzz"})
    assert out == {"a": "n-zzzzzz", "b": "show n-zzzzzz and text-zzzzzzzz"} and count == 0


def test_a_stand_in_of_another_session_is_unknown_here() -> None:
    other = Store.ephemeral(OTHER_KEY)
    foreign = pseudonymize("NAME", "fw-paris-01", other, OTHER_KEY)
    mine = Store.ephemeral(KEY)
    assert run(mine, {"name": foreign}) == ({"name": foreign}, 0)


def test_keys_and_non_strings_never_change() -> None:
    store = Store.ephemeral(KEY)
    standin = issue(store, "NAME", "fw-paris-01")
    out, count = run(
        store,
        {standin: standin, "n": 3, "t": True, "z": None, "list": [1, standin, {"deep": standin}]},
    )
    assert out == {
        standin: "fw-paris-01", "n": 3, "t": True, "z": None,
        "list": [1, "fw-paris-01", {"deep": "fw-paris-01"}],
    }  # fmt: skip
    assert count == 3


def test_the_reply_says_nothing_about_unknown_stand_ins() -> None:
    store = Store.ephemeral(KEY)
    out = translate({"a": "n-zzzzzz", "b": "plain"}, store=store)
    assert set(vars(out)) == {"args", "translated"}
    assert out.translated == 0
    assert "zzzzzz" not in repr({k: v for k, v in vars(out).items() if k != "args"})


def test_plain_text_is_unchanged() -> None:
    store = Store.ephemeral(KEY)
    value = {"q": "show me the rules with action allow on port 443"}
    assert run(store, value) == (value, 0)
