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


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures" / "panos-mcp"


def load_generic_results():  # type: ignore[no-untyped-def]
    """The generic test server's results module (testservers/generic/results.py)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generic_results", ROOT / "testservers" / "generic" / "results.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def panos_fixtures() -> dict[str, dict]:  # type: ignore[type-arg]
    skip = {"tools.json", "real_values.json"}
    return {
        p.stem: json.loads(p.read_text())
        for p in sorted(FIXTURES.glob("*.json"))
        if p.name not in skip
    }


def panos_real_values() -> list[str]:
    """Identifying values found in the panos-mcp fixtures (record_panos_fixtures.py)."""
    data = json.loads((FIXTURES / "real_values.json").read_text())
    kinds = ("IP", "FQDN", "DIGITS", "USER", "NAME")
    return sorted({v for kind in kinds for v in data[kind]})


def panos_unchanged_by_design() -> tuple[str, ...]:
    data = json.loads((FIXTURES / "real_values.json").read_text())
    return tuple(data["UNCHANGED_BY_DESIGN"])


def leaked(values: list[str], output: object, store, unchanged: tuple[str, ...] = ()) -> list[str]:  # type: ignore[no-untyped-def]
    """Real values still readable in `output` (whole tokens, hyphens and dots included).

    A value that is the stand-in of another real value in this session is no leak (a /24 is
    permuted within itself), and values the guard leaves as they are by design are removed
    first (`unchanged`).
    """
    import re

    text = json.dumps(output, ensure_ascii=False)
    for keep in sorted(unchanged, key=len, reverse=True):
        text = text.replace(keep, " ")
    found = []
    for value in values:
        if store.lookup_standin(value) is not None:
            continue
        pattern = r"(?<![\w\-.])" + re.escape(value) + r"(?![\w\-]|\.\w)"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(value)
    return found
