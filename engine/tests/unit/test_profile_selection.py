"""T080: user profiles, selection order and check-profile (FR-013-FR-016)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import Cli

from mcp_privacy_guard.profiles import loader

USER = """
[profile]
id = "{id}"
version = 1
servers = {servers}
{extra}
"""


def write(
    home: Path, name: str, *, id: str = "mine", servers: str = '["panos"]', extra: str = ""
) -> Path:  # noqa: A002
    folder = home / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(USER.format(id=id, servers=servers, extra=extra), encoding="utf-8")
    return path


WARMUP = '[[warmup]]\ntool = "list_device_groups"\nargs = {}\n'


def test_a_user_profile_beats_a_bundled_profile_with_matching_globs(home: Path) -> None:
    write(home, "mine.toml", extra=WARMUP)
    profile, state, reason = loader.select_profile("panos", None, home)
    assert (profile.id, state, reason) == ("mine", "valid", None)
    assert loader.select_profile("panos", None)[0].id == "panos-mcp"


def test_a_user_profile_applies_only_to_its_servers(home: Path) -> None:
    write(home, "mine.toml", servers='["notion"]')
    assert loader.select_profile("notion", None, home)[0].id == "mine"
    assert loader.select_profile("other", None, home)[0].id == "default"


def test_config_profile_beats_user_and_bundled(home: Path) -> None:
    write(home, "mine.toml", extra=WARMUP)
    write(home, "other.toml", id="other", servers='["panos"]', extra=WARMUP)
    assert loader.select_profile("panos", "other", home)[0].id == "other"
    assert loader.select_profile("panos", "panos-mcp", home)[0].id == "panos-mcp"
    assert loader.select_profile("panos", "nope", home)[1:] == ("invalid", "unknown-profile")


def test_an_invalid_user_profile_falls_back_to_default(home: Path) -> None:
    write(home, "mine.toml", servers='["notion"]', extra='[vocabulary]\nvalues = ["10.1.2.3"]')
    profile, state, reason = loader.select_profile("notion", None, home)
    assert (profile.id, state, reason) == ("default", "invalid", "identifying-vocabulary")
    assert loader.select_profile("elsewhere", None, home)[1] == "valid"


def test_an_unreadable_user_profile_is_invalid_for_every_server(home: Path) -> None:
    (home / "profiles").mkdir(parents=True)
    (home / "profiles" / "broken.toml").write_text("this is [ not toml", encoding="utf-8")
    profile, state, reason = loader.select_profile("anything", None, home)
    assert (profile.id, state, reason) == ("default", "invalid", "invalid-toml")


def test_a_user_profile_without_warmup_keeps_the_bundled_one(home: Path) -> None:
    write(home, "mine.toml")
    profile, state, reason = loader.select_profile("panos", None, home)
    assert (profile.id, state, reason) == ("panos-mcp", "invalid", "warmup-required")


def test_status_reports_the_invalid_state_and_reason(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    write(home, "mine.toml")
    out: Cli = cli("status", "--servers", "panos")
    entry = out.json["servers"]["panos"]
    assert entry["profile"] == "panos-mcp"
    assert entry["profile_state"] == "invalid" and entry["profile_reason"] == "warmup-required"


def test_check_profile_valid_and_invalid_both_exit_0(home: Path, cli, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    good = write(tmp_path / "g", "ok.toml", servers='["gen"]')
    out: Cli = cli("check-profile", str(good))
    assert out.code == 0 and out.json == {"valid": True}
    bad = write(
        tmp_path / "b", "bad.toml", servers='["gen"]', extra='[vocabulary]\nvalues = ["10.1.2.3"]'
    )
    out = cli("check-profile", str(bad))
    assert out.code == 0 and out.json["valid"] is False
    assert out.json["errors"] == [{"path": "", "message": "identifying-vocabulary"}]
    assert "10.1.2.3" not in out.stdout
    missing = cli("check-profile", str(tmp_path / "missing.toml"))
    assert missing.code == 0 and missing.json["errors"][0]["message"] == "unreadable"


def test_check_profile_applies_the_warmup_rule_against_bundled_profiles(
    cli, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    path = write(tmp_path, "mine.toml")
    out = cli("check-profile", str(path))
    assert out.json["valid"] is False and out.json["errors"][0]["message"] == "warmup-required"
