"""T097 (SC-004): the same value gets the same stand-in within a session and only there."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from tests.conftest import Cli, load_generic_results

generic = load_generic_results()


def sessions(home: Path) -> Path:
    return home / "store" / "sessions"


def result(cli, sid: str, tool: str = "list_devices") -> Cli:  # type: ignore[no-untyped-def]
    body = {"result": generic.TOOLS[tool](), "is_error": False}
    return cli(
        "result", "--session", sid, "--server", "generic", "--tool", tool,
        stdin=json.dumps(body),
    )  # fmt: skip


def reply(out: Cli) -> Any:
    assert out.code == 0, out.stdout
    return out.json["result"]


def test_two_processes_of_one_session_give_identical_stand_ins(cli) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "a", "--servers", "generic")
    assert reply(result(cli, "a")) == reply(result(cli, "a"))
    assert reply(result(cli, "a", "get_config")) == reply(result(cli, "a", "get_config"))


def test_two_sessions_give_different_stand_ins(cli) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "a", "--servers", "generic")
    cli("begin", "--session", "b", "--servers", "generic")
    first = reply(result(cli, "a"))["structuredContent"]["devices"][0]
    second = reply(result(cli, "b"))["structuredContent"]["devices"][0]
    for key in ("name", "hostname", "ip", "serial", "owner"):
        assert first[key] != second[key], key


def test_after_end_nothing_remains_and_old_stand_ins_mean_nothing(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "a", "--servers", "generic")
    devices = reply(result(cli, "a"))["structuredContent"]["devices"]
    name, address = devices[0]["name"], devices[0]["ip"]
    folder = sessions(home) / "a"
    assert (folder / "secret.key").exists() and (folder / "mapping.sqlite").exists()

    assert cli("end", "--session", "a").json["deleted"] is True
    assert not folder.exists()
    assert not any(p.name.startswith("mapping") for p in sessions(home).rglob("*"))
    assert cli("table", "--session", "a", "--since", "0").code == 3

    cli("begin", "--session", "later", "--servers", "generic")
    revealed = cli("reveal", "--session", "later", "--json", stdin=f"{name} {address}")
    assert revealed.json["unknown"] == [name]  # the name stand-in means nothing now
    assert generic.seed()["devices"][0] not in revealed.stdout
    args = cli(
        "args", "--session", "later", "--server", "generic", "--tool", "t",
        stdin=json.dumps({"args": {"n": name}}),
    )  # fmt: skip
    assert args.json["args"] == {"n": name} and args.json["translated"] == 0


def test_a_stale_folder_is_swept_by_the_next_begin(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    cli("begin", "--session", "old", "--servers", "generic")
    cli("begin", "--session", "fresh", "--servers", "generic")
    old = time.time() - 25 * 3600
    folder = sessions(home) / "old"
    for path in (*folder.iterdir(), folder):
        os.utime(path, (old, old))
    begun = cli("begin", "--session", "new", "--servers", "generic")
    assert begun.json["swept"] == 1
    assert not folder.exists()
    assert (sessions(home) / "fresh").exists() and (sessions(home) / "new").exists()
