"""Engine command line (contracts/engine-cli.md).

Every subcommand reads at most one JSON object on stdin and writes one on stdout. On a
non-zero exit stdout is `{"error": {"code", "message", "hint"}}`; no message ever holds a
value from the input. There is no option that disables or bypasses anything (FR-027).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, NoReturn

from mcp_privacy_guard import __version__
from mcp_privacy_guard import reveal as revealing
from mcp_privacy_guard import warmup as gate
from mcp_privacy_guard.arguments import translate
from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.config import Config, load_config, resolve_home
from mcp_privacy_guard.errors import BadInput, GuardError, StoreUnavailable
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.prompts import identifying, pseudonymize_prompt
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.standins import ip
from mcp_privacy_guard.store import Store, check_sid

RECOGNISE = r"\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b"
KINDS = [
    "IP", "FQDN", "URL", "MAC", "EMAIL", "USER", "GROUP", "NAME", "DIGITS", "TEXT", "MIXED",
]  # fmt: skip
WARMUP_PREFIX = gate.STATE
WARMUP_REASON_PREFIX = gate.REASON

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
    alias: str, config: Config, store: Store | None, home: Path
) -> tuple[dict[str, Any], bool, bool]:
    """(status entry, protected, has warm-up) for one server alias."""
    entry_cfg = config.server(alias)
    profile, state, reason = loader.select_profile(alias, entry_cfg.profile, home)
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
            entry["warmup_reason"] = store.meta_get(WARMUP_REASON_PREFIX + alias) or None
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
    out["servers"] = {a: server_view(a, config, store, home)[0] for a in args.servers}
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
            _, protected, has_warmup = server_view(alias, config, None, home)
            if protected and has_warmup:
                gate.register(store, alias)
                warmup.append(alias)
        for value in (*config.keep_values, *config.keep_files):
            if shapes.classify_whole(value) == "IP":
                store.fix(value)
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


def _strings_of(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings_of(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings_of(item)


def record_fixed(result: dict[str, Any], store: Store) -> int:
    """Exempt server: its IP forms reach the model unchanged, so they are fixed (R15)."""
    seen: set[str] = set()
    for text in _strings_of(result):
        for start, end, kind in shapes.find_embedded(text):
            piece = text[start:end]
            if kind == "IP" and ip.permute(store.key, piece) != piece:
                seen.add(piece)
    for piece in seen:
        store.fix(piece)
    return len(seen)


def cmd_result(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    body = read_stdin_json()
    result = body.get("result")
    if not isinstance(result, dict):
        raise BadInput("bad-json", "stdin needs a `result` object")
    config = load_config(home)
    store = Store.open(home, args.session)
    try:
        if args.exempt:
            return {"fixed": record_fixed(result, store)}
        profile, _, _ = loader.select_profile(args.server, config.server(args.server).profile, home)
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


def cmd_args(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    body = read_stdin_json()
    given = body.get("args")
    if not isinstance(given, dict):
        raise BadInput("bad-json", "stdin needs an `args` object")
    store = Store.open(home, args.session)
    try:
        out = translate(given, store=store)
        return {
            "args": out.args,
            "translated": out.translated,
            "table": table_reply(store, args.since),
        }
    finally:
        store.close()


def cmd_prompt(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    body = read_stdin_json()
    text = body.get("text")
    if not isinstance(text, str):
        raise BadInput("bad-json", "stdin needs a `text` string")
    config = load_config(home)
    store = Store.open(home, args.session)
    try:
        gate.check_gate(store)
        if args.command:
            return {"identifying": identifying(text, store=store, config=config, home=home)}
        out = pseudonymize_prompt(text, store=store, config=config, home=home)
        return {
            "text": out.text,
            "replacements": out.replacements,
            "warnings": out.warnings,
            "table": table_reply(store, args.since),
        }
    finally:
        store.close()


def cmd_learn(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    body = read_stdin_json()
    result = body.get("result")
    if not isinstance(result, dict):
        raise BadInput("bad-json", "stdin needs a `result` object")
    config = load_config(home)
    store = Store.open(home, args.session)
    try:
        profile, _, _ = loader.select_profile(args.server, config.server(args.server).profile, home)
        pseudonymize_result(
            result, store=store, profile=profile, config=config, server=args.server, tool=args.tool
        )
        return {"names": len(store.names())}
    finally:
        store.close()


def cmd_warmup(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    store = Store.open(home, args.session)
    try:
        gate.register(store, args.server)
        gate.set_state(store, args.server, args.state, args.reason)
        pending, failed = gate.summary(store)
        return {"pending": pending, "failed": failed}
    finally:
        store.close()


def cmd_observe(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    text = read_stdin_json().get("text")
    if not isinstance(text, str):
        raise BadInput("bad-json", "stdin needs a `text` string")
    store = Store.open(home, args.session)
    try:
        revealing.observe(text, store=store)
        return {"table": table_reply(store, args.since)}
    finally:
        store.close()


def cmd_reveal(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    raw = sys.stdin.read()
    text = raw
    if raw.lstrip().startswith("{"):
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("text"), str):
            text = body["text"]
    sid = args.session or revealing.only_live_session(home)
    store = Store.open(home, sid)
    try:
        out = revealing.reveal(text, store=store)
    finally:
        store.close()
    if args.json:
        return {"text": out.text, "revealed": out.revealed, "unknown": out.unknown}
    return {"_raw": out.text}


def cmd_check_profile(args: argparse.Namespace, home: Path) -> dict[str, Any]:
    errors = loader.check_file(Path(args.file))
    return {"valid": False, "errors": errors} if errors else {"valid": True}


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
    result.add_argument("--exempt", action="store_true")
    call = add("args", cmd_args)
    call.add_argument("--server", required=True, type=_alias)
    call.add_argument("--tool", required=True, type=_alias)
    call.add_argument("--since", type=int, default=0)
    prompt = add("prompt", cmd_prompt)
    prompt.add_argument("--since", type=int, default=0)
    prompt.add_argument("--command", action="store_true")
    learn = add("learn", cmd_learn)
    learn.add_argument("--server", required=True, type=_alias)
    learn.add_argument("--tool", required=True, type=_alias)
    warm = add("warmup", cmd_warmup)
    warm.add_argument("--server", required=True, type=_alias)
    warm.add_argument("--state", required=True, choices=["running", "complete", "failed"])
    warm.add_argument("--reason")
    observe = add("observe", cmd_observe)
    observe.add_argument("--since", type=int, default=0)
    shown = add("reveal", cmd_reveal, required=False)
    shown.add_argument("--json", action="store_true")
    add("check-profile", cmd_check_profile, session=False).add_argument("file")
    return parser


def _error(exc: GuardError) -> dict[str, Any]:
    return {"error": {"code": exc.code, "message": exc.message, "hint": exc.hint, **exc.details}}


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
    if "_raw" in result:  # reveal prints plain text unless --json
        print(result["_raw"])
    else:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
