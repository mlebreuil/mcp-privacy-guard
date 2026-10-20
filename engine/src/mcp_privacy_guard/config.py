"""Operator configuration: `<home>/config.toml` (data-model "Operator config").

There is no key that disables pseudonymization (FR-027): unknown keys are an error.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from mcp_privacy_guard.errors import BadInput

HOME_ENV = "MCP_PRIVACY_GUARD_HOME"


def resolve_home() -> Path:
    override = os.environ.get(HOME_ENV)
    return Path(override) if override else Path.home() / ".config" / "mcp-privacy-guard"


@dataclass(frozen=True)
class ServerConfig:
    profile: str | None = None
    exempt: bool = False


@dataclass(frozen=True)
class Config:
    keep_values: tuple[str, ...] = ()
    keep_files: tuple[str, ...] = ()
    hide_values: tuple[str, ...] = ()
    hide_files: tuple[str, ...] = ()
    servers: dict[str, ServerConfig] = field(default_factory=dict)

    def server(self, alias: str) -> ServerConfig:
        return self.servers.get(alias, ServerConfig())


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BadInput("bad-config", f"{where} must be a list of strings")
    return tuple(value)


def _only(table: dict[str, object], allowed: set[str], where: str) -> None:
    unknown = set(table) - allowed
    if unknown:
        raise BadInput("bad-config", f"unknown key in {where}", "remove it from config.toml")


def _read_list_files(names: tuple[str, ...], base: Path | None, where: str) -> tuple[str, ...]:
    out: list[str] = []
    for name in names:
        path = Path(name) if base is None else base / name
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise BadInput("bad-config", f"cannot read a {where} file") from exc
        out += [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]
    return tuple(out)


def parse_config(data: dict[str, object], base: Path | None = None) -> Config:
    _only(data, {"keep", "hide", "servers"}, "config")
    lists: dict[str, tuple[str, ...]] = {}
    for section in ("keep", "hide"):
        table = data.get(section, {})
        if not isinstance(table, dict):
            raise BadInput("bad-config", f"{section} must be a table")
        _only(table, {"values", "files"}, section)
        lists[f"{section}_values"] = _strings(table.get("values", []), f"{section}.values")
        files = _strings(table.get("files", []), f"{section}.files")
        lists[f"{section}_files"] = _read_list_files(files, base, section)
    servers: dict[str, ServerConfig] = {}
    raw = data.get("servers", {})
    if not isinstance(raw, dict):
        raise BadInput("bad-config", "servers must be a table")
    for alias, entry in raw.items():
        if not isinstance(entry, dict):
            raise BadInput("bad-config", "a server entry must be a table")
        _only(entry, {"profile", "exempt"}, "servers")
        profile = entry.get("profile")
        exempt = entry.get("exempt", False)
        if (profile is not None and not isinstance(profile, str)) or not isinstance(exempt, bool):
            raise BadInput("bad-config", "bad server entry")
        servers[alias] = ServerConfig(profile, exempt)
    return Config(
        lists["keep_values"],
        lists["keep_files"],
        lists["hide_values"],
        lists["hide_files"],
        servers,
    )


def load_config(home: Path) -> Config:
    path = home / "config.toml"
    if not path.exists():
        return Config()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BadInput("bad-config", "config.toml cannot be read", "fix or remove it") from exc
    return parse_config(data, path.parent)
