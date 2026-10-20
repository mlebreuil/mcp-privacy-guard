"""T088: operator keep and hide lists and exemptions (FR-002, FR-028)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import KEY

from mcp_privacy_guard.config import Config, parse_config
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store

PROFILE = """
[profile]
id = "gen"
version = 1
servers = ["gen"]

[vocabulary]
values = ["connected"]

[[fields]]
path = "state"
enum = ["connected"]
"""


def run(config: Config, payload: dict) -> dict:  # type: ignore[type-arg]
    out = pseudonymize_result(
        {"content": [{"type": "text", "text": json.dumps(payload)}], "isError": False},
        store=Store.ephemeral(KEY),
        profile=loader.load_profile(PROFILE),
        config=config,
        server="gen",
        tool="t",
    )
    return json.loads(out.result["content"][0]["text"])  # type: ignore[no-any-return]


def test_keep_values_pass_unchanged() -> None:
    config = Config(keep_values=("8.8.8.8", "Contoso-Core"))
    out = run(config, {"dns": "8.8.8.8", "site": "Contoso-Core", "other": "10.1.2.15"})
    assert out["dns"] == "8.8.8.8" and out["site"] == "Contoso-Core"
    assert out["other"] != "10.1.2.15"


def test_keep_files_pass_unchanged(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_text("# public\n9.9.9.9\n", encoding="utf-8")
    config = parse_config({"keep": {"files": ["keep.txt"]}}, tmp_path)
    assert run(config, {"dns": "9.9.9.9"})["dns"] == "9.9.9.9"
    assert config.keep_files == ("9.9.9.9",)


def test_hide_values_and_files_become_text_even_where_a_profile_would_keep_them(
    tmp_path: Path,
) -> None:
    assert run(Config(), {"state": "connected"})["state"] == "connected"
    out = run(Config(hide_values=("connected",)), {"state": "connected"})
    assert out["state"].startswith("text-")
    (tmp_path / "hide.txt").write_text("connected\n", encoding="utf-8")
    config = parse_config({"hide": {"files": ["hide.txt"]}}, tmp_path)
    assert run(config, {"state": "connected"})["state"].startswith("text-")


def test_a_hidden_value_inside_text_hides_the_block() -> None:
    out = run(Config(hide_values=("Project Falcon",)), {"note": "see Project Falcon status"})
    assert out["note"].startswith("text-")


def test_status_reports_entries_and_exemptions(home: Path, cli) -> None:  # type: ignore[no-untyped-def]
    home.mkdir(parents=True)
    (home / "hide.txt").write_text("a\nb\n", encoding="utf-8")
    (home / "config.toml").write_text(
        '[keep]\nvalues = ["8.8.8.8"]\n[hide]\nvalues = ["x"]\nfiles = ["hide.txt"]\n'
        "[servers.notion]\nexempt = true\n",
        encoding="utf-8",
    )
    data = cli("status", "--servers", "notion,panos").json
    assert (data["keep_entries"], data["hide_entries"]) == (1, 3)
    assert data["servers"]["notion"]["exempt"] is True
    assert data["servers"]["panos"]["exempt"] is False
