"""Shared helpers: a throwaway home and a way to run the engine CLI as the plugin does."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

KEY = bytes(range(32))
OTHER_KEY = bytes(range(1, 33))


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """`<home>`: it does not exist yet, so a test can see what the engine creates."""
    return tmp_path / "guard"


@dataclass
class Cli:
    code: int
    stdout: str
    stderr: str

    @property
    def json(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.stdout)  # type: ignore[no-any-return]


def run_cli(home: Path, *args: str, stdin: str | None = None) -> Cli:
    env = {k: v for k, v in os.environ.items() if not k.startswith("MCP_PRIVACY_GUARD")}
    env["MCP_PRIVACY_GUARD_HOME"] = str(home)
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "mcp_privacy_guard", *args],
        input=stdin if stdin is not None else "",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    return Cli(done.returncode, done.stdout, done.stderr)


@pytest.fixture
def cli(home: Path):  # type: ignore[no-untyped-def]
    def run(*args: str, stdin: str | None = None) -> Cli:
        return run_cli(home, *args, stdin=stdin)

    return run
