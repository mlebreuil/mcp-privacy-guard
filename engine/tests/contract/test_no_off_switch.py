"""T089: nothing turns the guard off (FR-027)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests.conftest import Cli

from mcp_privacy_guard.cli import build_parser
from mcp_privacy_guard.config import parse_config
from mcp_privacy_guard.errors import BadInput

SRC = Path(__file__).resolve().parents[2] / "src" / "mcp_privacy_guard"
FORBIDDEN = re.compile(r"--[\w-]*(disable|off|passthrough|bypass|skip|unsafe)", re.IGNORECASE)


def subcommands() -> list[str]:
    parser = build_parser()
    for action in parser._actions:  # noqa: SLF001
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            return list(choices)
    raise AssertionError("no subcommands")


def test_help_lists_no_disabling_option(cli) -> None:  # type: ignore[no-untyped-def]
    texts = [cli("--help")]
    texts += [cli(name, "--help") for name in subcommands()]
    for out in texts:
        assert out.code == 0
        assert FORBIDDEN.search(out.stdout) is None, out.stdout


def test_every_known_subcommand_is_checked() -> None:
    assert {"begin", "result", "args", "prompt", "reveal", "observe", "end"} <= set(subcommands())


@pytest.mark.parametrize("key", ["disable", "disabled", "off", "passthrough", "bypass", "enabled"])
def test_the_config_schema_rejects_any_such_key(key: str) -> None:
    with pytest.raises(BadInput):
        parse_config({key: True})
    with pytest.raises(BadInput):
        parse_config({"servers": {"a": {key: True}}})
    with pytest.raises(BadInput):
        parse_config({"keep": {key: True}})


def test_a_config_with_such_a_key_stops_the_engine(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    home.mkdir(parents=True)
    (home / "config.toml").write_text("disable = true\n", encoding="utf-8")
    out: Cli = cli("status", "--servers", "a")
    assert out.code == 2


def test_no_environment_variable_but_home_is_read() -> None:
    seen = set()
    for path in SRC.rglob("*.py"):
        seen |= set(re.findall(r"MCP_PRIVACY_GUARD_\w+", path.read_text(encoding="utf-8")))
    assert seen <= {"MCP_PRIVACY_GUARD_HOME"}
    reads = [
        p.name
        for p in SRC.rglob("*.py")
        if re.search(r"os\.(environ|getenv)", p.read_text(encoding="utf-8"))
    ]
    assert reads == ["config.py"]


def test_no_plugin_option_disables_the_guard() -> None:
    import json

    manifest = SRC.parents[2] / "plugin" / ".claude-plugin" / "plugin.json"
    options = json.loads(manifest.read_text(encoding="utf-8")).get("userConfig", {})
    assert list(options) == ["enginePath"]
