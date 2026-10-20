"""T042: the JSON walker and its decision order (research R4)."""

from __future__ import annotations

import re
from typing import Any

from tests.conftest import KEY

from mcp_privacy_guard.classify.walker import walk_json
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.store import Store

NAME = re.compile(r"^n-[a-z2-7]{6}$")
TEXT = re.compile(r"^text-[a-z2-7]{8}$")

HEAD = '[profile]\nid = "p"\nversion = 1\nservers = ["*"]\n'


def profile(body: str = "") -> loader.Profile:
    return loader.load_profile(HEAD + body)


def walk(value: Any, prof: loader.Profile | None = None, config: Config | None = None) -> Any:
    return walk_json(
        value,
        store=Store.ephemeral(KEY),
        profile=prof or loader.load_bundled("default"),
        config=config or Config(),
        server="gen",
        tool="t",
    )


def test_scalars_other_than_strings_are_unchanged() -> None:
    assert walk({"a": 1, "b": 2.5, "c": True, "d": None, "e": [1, False]}) == {
        "a": 1, "b": 2.5, "c": True, "d": None, "e": [1, False],
    }  # fmt: skip


def test_whole_value_shapes_become_their_stand_ins() -> None:
    out = walk(
        {
            "ip": "10.1.2.15",
            "fqdn": "app.corp.example.com",
            "mail": "jane@corp.example.com",
            "mac": "00:1b:17:aa:bb:cc",
            "serial": "007951000123456",
            "user": "CORP\\jdoe",
        }
    )
    assert out["ip"] != "10.1.2.15" and re.match(r"^10\.", out["ip"])
    assert out["fqdn"].endswith(".com") and "corp" not in out["fqdn"]
    assert re.match(r"^u-[a-z2-7]{6}@", out["mail"])
    assert out["mac"] != "00:1b:17:aa:bb:cc"
    assert len(out["serial"]) == 15 and out["serial"] != "007951000123456"
    assert out["user"].startswith("dom-")


def test_safe_forms_and_built_in_vocabulary_pass() -> None:
    values = ["allow", "deny", "tcp", "info", "2026-10-20T10:15:00Z", "PT5M", "443", "true"]
    assert walk({"v": values}) == {"v": values}


def test_a_single_unknown_token_is_a_name_and_text_is_hidden() -> None:
    out = walk({"x": "fw-paris-01", "y": "Gateway for the Paris payroll office"})
    assert NAME.match(out["x"])
    assert TEXT.match(out["y"])


def test_the_same_value_gets_the_same_stand_in_everywhere() -> None:
    out = walk({"a": "fw-paris-01", "b": ["fw-paris-01"], "c": {"d": "fw-paris-01"}})
    assert out["a"] == out["b"][0] == out["c"]["d"]


def test_hide_list_then_keep_list_come_first() -> None:
    prof = profile('[[fields]]\npath = "mode"\nenum = ["fast", "slow"]')
    config = Config(keep_values=("fw-paris-01", "10.9.9.9"), hide_values=("fast",))
    out = walk(
        {"mode": "fast", "other": "fw-paris-01", "ip": "10.9.9.9", "slow": "slow"}, prof, config
    )
    assert TEXT.match(out["mode"])  # hidden even though the enum would keep it
    assert out["other"] == "fw-paris-01" and out["ip"] == "10.9.9.9"  # kept
    # hide beats keep
    both = Config(keep_values=("x1",), hide_values=("x1",))
    assert TEXT.match(walk({"v": "x1"}, config=both)["v"])


def test_profile_kind_and_enum_rules() -> None:
    prof = profile(
        '[kinds.RULE_NAME]\ncues = ["rule"]\n'
        '[[fields]]\npath = "**.rules[].name"\nkind = "RULE_NAME"\n'
        '[[fields]]\npath = "**.rules[].action"\nenum = ["allow", "deny"]\n'
        '[[fields]]\npath = "**.description"\nkind = "TEXT"\n'
    )
    out = walk(
        {"d": {"rules": [{"name": "allow", "action": "allow", "x": 1},
                         {"name": "r2", "action": "reset-both"}],
               "description": "ok"}},
        prof,
    )  # fmt: skip
    rules = out["d"]["rules"]
    assert NAME.match(rules[0]["name"])  # a name rule hides even a vocabulary word
    assert rules[0]["action"] == "allow"
    assert NAME.match(rules[1]["action"])  # a value outside the enum becomes a NAME
    assert TEXT.match(out["d"]["description"])


def test_vocabulary_of_the_profile_passes() -> None:
    prof = profile('[vocabulary]\nvalues = ["application-default", "ethernet1/1"]')
    out = walk({"a": "application-default", "i": "ethernet1/1", "z": "other-thing"}, prof)
    assert out["a"] == "application-default" and out["i"] == "ethernet1/1"
    assert NAME.match(out["z"])


def test_object_keys_are_kept_only_when_plain_words() -> None:
    out = walk({"name": 1, "source_address": 2, "createdAt": 3, "fw-paris-01": 4,
                "10.1.2.15": 5, "host1": 6, "a_b_c_d_e": 7})  # fmt: skip
    keys = list(out)
    assert keys[0] == "name" and keys[1] == "source_address" and keys[2] == "createdAt"
    assert NAME.match(keys[3])  # a name used as a key is hidden
    assert keys[4] != "10.1.2.15" and re.match(r"^10\.", keys[4])
    assert NAME.match(keys[5])  # digits in a key: not a plain word
    assert NAME.match(keys[6])  # more than four words


def test_keys_hide_hides_every_key_and_keep_never_keeps_an_identifying_key() -> None:
    hide = profile('[[fields]]\npath = "data.*"\nkeys = "hide"\n')
    hidden = walk({"data": {"name": "x1", "state": "x2"}}, hide)
    assert all(NAME.match(k) for k in hidden["data"])

    keep = profile('[[fields]]\npath = "data.*"\nkeys = "keep"\n')
    config = Config(hide_values=("secretword",))
    out = walk({"data": {"web-srv-01": 1, "10.1.2.15": 2, "app.corp.example.com": 3,
                         "jane@corp.example.com": 4, "007951000123456": 5, "secretword": 6}},
               keep, config)  # fmt: skip
    kept = list(out["data"])
    assert kept[0] == "web-srv-01"  # a kept key: no identifying shape
    for original, key in zip(
        [
            "10.1.2.15",
            "app.corp.example.com",
            "jane@corp.example.com",
            "007951000123456",
            "secretword",
        ],
        kept[1:],
        strict=True,
    ):
        assert key != original
