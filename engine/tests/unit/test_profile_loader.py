"""T018: profile loading, validation and path patterns (contracts/profile-format.md)."""

from __future__ import annotations

import json

import pytest

from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.profiles.loader import ProfileError

HEAD = """
[profile]
id = "{id}"
version = {version}
servers = ["gen", "gen-*"]
"""


def profile(body: str = "", id: str = "gen-profile", version: int = 1) -> str:  # noqa: A002
    return HEAD.format(id=id, version=version) + body


def refused(text: str, **kw: object) -> str:
    with pytest.raises(ProfileError) as err:
        loader.load_profile(text, **kw)  # type: ignore[arg-type]
    return str(err.value.reason)


def test_bundled_default_loads() -> None:
    default = loader.load_bundled("default")
    assert default.id == "default" and default.version == 1
    assert default.fields == [] and default.warmup == []


def test_minimal_profile_loads() -> None:
    p = loader.load_profile(profile())
    assert p.id == "gen-profile" and p.servers == ["gen", "gen-*"]


@pytest.mark.parametrize(
    "value",
    ["10.1.2.3", "10.1.2.0/24", "corp.example.com", "jdoe@corp.example.com",
     "00:11:22:33:44:55", "https://x.example.com", "CORP\\jdoe", "1234567"],
)  # fmt: skip
def test_identifying_vocabulary_and_enum_values_are_refused(value: str) -> None:
    vocab = profile(f'[vocabulary]\nvalues = ["ok", {json.dumps(value)}]')
    assert refused(vocab) == "identifying-vocabulary"
    enum = profile(f'[[fields]]\npath = "a"\nenum = ["ok", {json.dumps(value)}]')
    assert refused(enum) == "identifying-vocabulary"


def test_kind_names() -> None:
    assert refused(profile('[kinds.rule_name]\ncues = ["rule"]')) == "bad-kind-name"
    assert refused(profile("[kinds.IP]\n")) == "core-kind-redefined"
    ok = loader.load_profile(profile('[kinds.RULE_NAME]\ncues = ["rule", "policy"]'))
    assert ok.kinds["RULE_NAME"].cues == ["rule", "policy"]


def test_id_and_version() -> None:
    assert refused(profile(id="Bad ID")) == "bad-id"
    assert refused(profile(version=2)) == "bad-version"


def test_each_field_rule_has_exactly_one_action() -> None:
    assert refused(profile('[[fields]]\npath = "a"')) == "field-rule"
    assert refused(profile('[[fields]]\npath = "a"\nkind = "NAME"\nenum = ["x"]')) == "field-rule"
    assert refused(profile('[[fields]]\npath = "a"\nkeys = "peek"')) == "bad-keys"
    assert (
        loader.load_profile(profile('[[fields]]\npath = "a"\nkeys = "keep"')).fields[0].keys
        == "keep"
    )


@pytest.mark.parametrize("pattern", ["a..b", "a[", "", "a.[]b", "**.**.x"])
def test_invalid_path_patterns(pattern: str) -> None:
    assert refused(profile(f'[[fields]]\npath = "{pattern}"\nkind = "NAME"')) == "bad-path"


@pytest.mark.parametrize(
    ("pattern", "steps", "expected"),
    [
        ("name", ("name",), True),
        ("name", ("x", "name"), False),
        ("rules[].name", ("rules", "[]", "name"), True),
        ("rules[].name", ("rules", "name"), False),
        ("rules[].source[]", ("rules", "[]", "source", "[]"), True),
        ("data.*.hostname", ("data", "web", "hostname"), True),
        ("data.*.hostname", ("data", "hostname"), False),
        ("**.name", ("name",), True),
        ("**.name", ("a", "b", "[]", "name"), True),
        ("**.rules[].name", ("data", "rules", "[]", "name"), True),
        ("**.rules[].name", ("data", "rule", "[]", "name"), False),
        ("entries[].*", ("entries", "[]", "src"), True),
    ],
)
def test_path_patterns(pattern: str, steps: tuple[str, ...], expected: bool) -> None:
    assert loader.compile_path(pattern).matches(steps) is expected


def test_tool_specific_rules_come_first_then_file_order() -> None:
    p = loader.load_profile(
        profile(
            '[[fields]]\npath = "**.x"\nkind = "TEXT"\n'
            '[[fields]]\npath = "**.x"\nkind = "NAME"\n'
            '[[fields]]\npath = "e[].x"\ntools = ["query_logs"]\nkeys = "keep"\n'
        )
    )
    steps = ("e", "[]", "x")
    assert p.match_field("other_tool", steps).kind == "TEXT"  # type: ignore[union-attr]
    assert p.match_field("query_logs", steps).keys == "keep"  # type: ignore[union-attr]
    assert p.match_field("other_tool", ("nothing",)) is None


def test_warmup_entries() -> None:
    p = loader.load_profile(profile('[[warmup]]\ntool = "list_device_groups"\nargs = {}'))
    assert (p.warmup[0].tool, p.warmup[0].args) == ("list_device_groups", {})


def test_a_profile_may_not_drop_a_bundled_warmup() -> None:
    bundled = loader.load_profile(
        HEAD.format(id="bundled", version=1).replace('["gen", "gen-*"]', '["gen"]')
        + '[[warmup]]\ntool = "list_all"\nargs = {}'
    )
    assert refused(profile(), bundled=[bundled]) == "warmup-required"
    keeps = profile('[[warmup]]\ntool = "list_other"\nargs = {}')
    assert loader.load_profile(keeps, bundled=[bundled]).warmup[0].tool == "list_other"


def test_unreadable_toml_is_a_profile_error() -> None:
    assert refused("[profile\nid = 1") == "invalid-toml"
