"""T063: the warm-up gate (FR-034, research R9), through the CLI as the plugin uses it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.conftest import Cli


def begin(cli, servers: str = "panos,generic") -> Cli:  # type: ignore[no-untyped-def]
    out = cli("begin", "--session", "s1", "--servers", servers)
    assert out.code == 0, out.stdout
    return out


def prompt(cli, *extra: str, text: str = "why is 10.1.2.15 blocked?") -> Cli:  # type: ignore[no-untyped-def]
    return cli("prompt", "--session", "s1", *extra, stdin=json.dumps({"text": text}))


def warmup(cli, server: str, state: str, reason: str | None = None) -> Cli:  # type: ignore[no-untyped-def]
    args = ["warmup", "--session", "s1", "--server", server, "--state", state]
    if reason is not None:
        args += ["--reason", reason]
    return cli(*args)


def test_begin_records_only_protected_servers_whose_profile_has_a_warmup(cli) -> None:  # type: ignore[no-untyped-def]
    assert begin(cli).json["warmup"] == ["panos"]
    servers = cli("status", "--session", "s1", "--servers", "panos,generic").json["servers"]
    assert servers["panos"]["warmup_state"] == "not-started"
    assert servers["panos"]["warmup"][0]["tool"] == "list_device_groups"
    assert "warmup" not in servers["generic"]


def test_an_exempt_server_is_not_held(cli, home: Path) -> None:  # type: ignore[no-untyped-def]
    home.mkdir(parents=True)
    (home / "config.toml").write_text("[servers.panos]\nexempt = true\n")
    assert begin(cli).json["warmup"] == []
    assert prompt(cli).code == 0


def test_questions_wait_while_a_warmup_is_pending_or_running(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    for state_args in ((), ("--command",)):
        out = prompt(cli, *state_args)
        assert out.code == 4
        error = out.json["error"]
        assert error["code"] == "warmup-pending" and error["servers"] == ["panos"]
        assert "10.1.2.15" not in out.stdout and "10.1.2.15" not in out.stderr
    assert warmup(cli, "panos", "running").json == {"pending": ["panos"], "failed": []}
    assert prompt(cli).json["error"]["code"] == "warmup-pending"


def test_nothing_is_recorded_while_the_gate_is_closed(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    prompt(cli)
    assert cli("table", "--session", "s1", "--since", "0").json["table"]["entries"] == []


def test_complete_opens_the_gate(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    assert warmup(cli, "panos", "complete").json == {"pending": [], "failed": []}
    out = prompt(cli)
    assert out.code == 0 and "10.1.2.15" not in out.json["text"]


def test_a_failed_warmup_keeps_questions_blocked_with_its_reason(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    assert warmup(cli, "panos", "failed", "timeout").json == {"pending": [], "failed": ["panos"]}
    for extra in ((), ("--command",)):
        error = prompt(cli, *extra).json["error"]
        assert error["code"] == "warmup-failed"
        assert error["servers"] == ["panos"] and error["reason"] == "timeout"
        assert error["hint"]


@pytest.mark.parametrize("reason", ["timeout", "tool-missing", "tool-error", "learn-failed"])
def test_every_failure_reason_is_accepted(cli, reason: str) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    assert warmup(cli, "panos", "failed", reason).code == 0


def test_failed_needs_a_known_reason(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    assert warmup(cli, "panos", "failed").code == 2
    assert warmup(cli, "panos", "failed", "because").code == 2
    assert warmup(cli, "panos", "failed", "not-connected").code == 2  # removed with R9


def test_running_registers_a_server_that_was_not_listed(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli, "generic")
    assert prompt(cli).code == 0
    assert warmup(cli, "late-server", "running").json == {"pending": ["late-server"], "failed": []}
    assert prompt(cli).json["error"]["code"] == "warmup-pending"
    warmup(cli, "late-server", "complete")
    assert prompt(cli).code == 0


def test_the_state_is_per_session(cli) -> None:  # type: ignore[no-untyped-def]
    begin(cli)
    assert cli("begin", "--session", "s2", "--servers", "generic").code == 0
    out = cli("prompt", "--session", "s2", stdin=json.dumps({"text": "hello"}))
    assert out.code == 0
