"""Engine command line (contracts/engine-cli.md).

Every subcommand reads at most one JSON object on stdin and writes one on stdout. On a
non-zero exit stdout is `{"error": {"code", "message", "hint"}}`; no message ever holds a
value from the input. There is no option that disables or bypasses anything (FR-027).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from mcp_privacy_guard import __version__
from mcp_privacy_guard.config import Config, load_config, resolve_home
from mcp_privacy_guard.errors import BadInput, GuardError, StoreUnavailable
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store, check_sid

RECOGNISE = r"\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b"
KINDS = [
    "IP", "FQDN", "URL", "MAC", "EMAIL", "USER", "GROUP", "NAME", "DIGITS", "TEXT", "MIXED",
]  # fmt: skip
WARMUP_PREFIX = "warmup_state:"
WARMUP_REASON_PREFIX = "warmup_reason:"

Handler = Callable[[argparse.Namespace, Path], dict[str, Any]]


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # never echo the offending argument
        raise BadInput("bad-arguments", "the command line is invalid", "see --help")


def _servers(text: str) -> list[str]:
    return [s for s in (part.strip() for part in text.split(",")) if s]


def _session(text: str) -> str:
    return check_sid(text)


def _alias(text: str) -> str:
    if not text or len(text) > 256:
        raise argparse.ArgumentTypeError("bad name")
    return text


# -- helpers -----------------------------------------------------------------------------


def server_view(
    alias: str, config: Config, store: Store | None
) -> tuple[dict[str, Any], bool, bool]:
    """(status entry, protected, has warm-up) for one server alias."""
    entry_cfg = config.server(alias)
    profile, state, reason = loader.select_profile(alias, entry_cfg.profile)
    entry: dict[str, Any] = {
        "profile": profile.id,
        "profile_state": state,
        "exempt": entry_cfg.exempt,
    }
    if reason is not None:
        entry["profile_reason"] = reason
    protected = not entry_cfg.exempt
    has_warmup = protected and bool(profile.warmup)
    if has_warmup:
        entry["warmup"] = [{"tool": w.tool, "args": w.args} for w in profile.warmup]
        if store is not None:
            entry["warmup_state"] = store.meta_get(WARMUP_PREFIX + alias) or "not-started"
            entry["warmup_reason"] = store.meta_get(WARMUP_REASON_PREFIX + alias)
    return entry, protected, has_warmup


# -- subcommands -------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    config = load_config(home)
    out: dict[str, Any] = {
        "engine": __version__,
        "home": str(home),
        "store": Store.state(home),
    }
    store: Store | None = None
    if args.session is not None:
        sid = args.session
        out["swept"] = Store.sweep(home, sid)
        try:
            store = Store.open(home, sid)
            out["session"] = "live"
            out["rev"] = store.rev()
        except StoreUnavailable as exc:
            out["session"] = (
                "none" if exc.code == "session-missing"
                else "too-permissive" if exc.code == "too-permissive"
                else "unreadable"
            )  # fmt: skip
    out["servers"] = {a: server_view(a, config, store)[0] for a in args.servers}
    if store is not None:
        store.close()
    out["recognise"] = RECOGNISE
    out["kinds"] = KINDS
    out["keep_entries"] = len(config.keep_values) + len(config.keep_files)
    out["hide_entries"] = len(config.hide_values) + len(config.hide_files)
    return out


def cmd_begin(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    config = load_config(home)
    swept = Store.sweep(home, args.session)
    store = Store.begin(home, args.session)
    try:
        warmup = []
        for alias in args.servers:
            _, protected, has_warmup = server_view(alias, config, None)
            if protected and has_warmup:
                store.meta_set(WARMUP_PREFIX + alias, "not-started")
                warmup.append(alias)
    except BaseException:
        store.close()
        Store.end(home, args.session)
        raise
    store.close()
    return {"session": "live", "swept": swept, "warmup": warmup}


def cmd_end(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    deleted = Store.end(home, args.session)
    return {"deleted": deleted, "swept": Store.sweep(home, args.session)}


def cmd_table(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    store = Store.open(home, args.session)
    try:
        rev, entries = store.table(args.since)
    finally:
        store.close()
    return {"table": {"rev": rev, "entries": entries}}


def read_stdin_json() -> dict[str, Any]:
    try:
        data = json.loads(sys.stdin.read())
    except ValueError as exc:
        raise BadInput("bad-json", "stdin is not valid JSON") from exc
    if not isinstance(data, dict):
        raise BadInput("bad-json", "stdin must be a JSON object")
    return data


def table_reply(store: Store, since: int) -> dict[str, Any]:
    rev, entries = store.table(since)
    return {"rev": rev, "entries": entries}


def cmd_result(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    body = read_stdin_json()
    result = body.get("result")
    if not isinstance(result, dict):
        raise BadInput("bad-json", "stdin needs a `result` object")
    config = load_config(home)
    store = Store.open(home, args.session)
    try:
        profile, _, _ = loader.select_profile(args.server, config.server(args.server).profile)
        out = pseudonymize_result(
            result,
            store=store,
            profile=profile,
            config=config,
            server=args.server,
            tool=args.tool,
            is_error=bool(body.get("is_error", False)),
        )
        return {
            "result": out.result,
            "withheld": out.withheld,
            "notices": out.notices,
            "table": table_reply(store, args.since),
        }
    finally:
        store.close()


def _not_built(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    raise GuardError("not-implemented", "this subcommand is not built yet")


# -- parser and entry point --------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="mcp-privacy-guard", description="Pseudonymization engine")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

    def add(name: str, handler: Handler, *, session: bool = True, required: bool = True) -> Any:
        p = sub.add_parser(name)
        p.set_defaults(handler=handler)
        if session:
            p.add_argument("--session", type=_session, required=required)
        return p

    status = add("status", cmd_status, required=False)
    status.add_argument("--servers", type=_servers, default=[])
    begin = add("begin", cmd_begin)
    begin.add_argument("--servers", type=_servers, default=[])
    add("end", cmd_end)
    table = add("table", cmd_table)
    table.add_argument("--since", type=int, default=0)
    result = add("result", cmd_result)
    result.add_argument("--server", required=True, type=_alias)
    result.add_argument("--tool", required=True, type=_alias)
    result.add_argument("--since", type=int, default=0)
    for name in ("args", "prompt", "learn", "warmup", "observe"):
        p = add(name, _not_built)
        p.add_argument("rest", nargs="*")
    add("reveal", _not_built, session=False).add_argument("rest", nargs="*")
    add("check-profile", _not_built, session=False).add_argument("rest", nargs="*")
    return parser


def _error(exc: GuardError) -> dict[str, Any]:
    return {"error": {"code": exc.code, "message": exc.message, "hint": exc.hint}}


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.handler(args, resolve_home())
    except GuardError as exc:
        print(json.dumps(_error(exc)))
        return exc.exit_code
    except SystemExit as exc:  # --help
        return int(exc.code or 0) if isinstance(exc.code, int) else 0
    except Exception:  # noqa: BLE001 - nothing from the input may reach the output
        print(json.dumps(_error(GuardError("internal", "internal error"))))
        return 5
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
