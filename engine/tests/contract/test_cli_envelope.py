"""T019: the engine CLI envelope (contracts/engine-cli.md): JSON, exit codes, no values."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

SECRET_SID = "SENTINELSESSIONID"


def tree(path: Path) -> list[str]:
    return sorted(str(p) for p in path.rglob("*")) if path.exists() else []


def test_status_creates_nothing_and_reports_the_store(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    out = cli("status")
    assert out.code == 0
    data = out.json
    assert data["store"] == "ready" and data["home"] == str(home)
    assert "session" not in data and "rev" not in data
    assert not home.exists()


def test_status_with_a_session(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    assert cli("status", "--session", "s1").json["session"] == "none"
    assert cli("begin", "--session", "s1", "--servers", "a").code == 0
    data = cli("status", "--session", "s1").json
    assert (data["session"], data["rev"], data["swept"]) == ("live", 0, 0)
    secret = home / "store" / "sessions" / "s1" / "secret.key"
    assert cli("status").stdout.find(secret.read_bytes().hex()) == -1


def test_status_flags_a_permissive_session(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "s1", "--servers", "a")
    os.chmod(home / "store" / "sessions" / "s1" / "secret.key", 0o644)
    assert cli("status", "--session", "s1").json["session"] == "too-permissive"


def test_begin_end_table(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    begun = cli("begin", "--session", "s1", "--servers", "a,b")
    assert begun.code == 0
    assert begun.json == {"session": "live", "swept": 0, "warmup": []}
    folder = home / "store" / "sessions" / "s1"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert cli("table", "--session", "s1", "--since", "0").json == {
        "table": {"rev": 0, "entries": []}
    }
    ended = cli("end", "--session", "s1")
    assert (ended.code, ended.json) == (0, {"deleted": True, "swept": 0})
    assert not folder.exists()
    again = cli("end", "--session", "s1")
    assert (again.code, again.json["deleted"]) == (0, False)


def test_begin_on_a_live_session_is_refused(cli) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "s1", "--servers", "a")
    out = cli("begin", "--session", "s1", "--servers", "a")
    assert out.code == 4 and out.json["error"]["code"] == "session-live"


def test_missing_session_exits_3_and_creates_nothing(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    out = cli("table", "--session", "nope", "--since", "0")
    assert out.code == 3 and out.json["error"]["code"] == "session-missing"
    assert not home.exists()


@pytest.mark.parametrize("sid", ["../x", "a b", "a" * 129])
def test_malformed_session_exits_2(cli, sid: str) -> None:  # type: ignore[no-untyped-def]
    for args in (
        ("status", "--session", sid),
        ("begin", "--session", sid, "--servers", "a"),
        ("end", "--session", sid),
        ("table", "--session", sid, "--since", "0"),
    ):
        out = cli(*args)
        assert out.code == 2, args
        assert set(out.json["error"]) == {"code", "message", "hint"}


@pytest.mark.parametrize("sub", ["status", "begin", "end", "table"])
def test_errors_carry_no_input_value(cli, sub: str) -> None:  # type: ignore[no-untyped-def]
    args = {
        "status": ["status", "--session", SECRET_SID + "/x"],
        "begin": ["begin", "--session", SECRET_SID + "/x", "--servers", "a"],
        "end": ["end", "--session", SECRET_SID + "/x"],
        "table": ["table", "--session", SECRET_SID, "--since", "0"],
    }[sub]
    out = cli(*args)
    assert out.code != 0
    assert SECRET_SID not in out.stdout and SECRET_SID not in out.stderr
    assert json.loads(out.stdout)["error"]["code"]


def test_error_exit_codes_are_the_documented_ones(cli) -> None:  # type: ignore[no-untyped-def]
    codes = {
        cli("table", "--session", "nope", "--since", "0").code,
        cli("status", "--session", "../x").code,
        cli("begin", "--session", "s1", "--servers", "a").code,
    }
    assert codes == {3, 2, 0}
