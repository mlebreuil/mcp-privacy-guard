"""The warm-up gate (FR-034, research R9): no question before the session's names have loaded.

The state lives in the session's `meta` table, one entry per server whose profile declares a
warm-up: `not-started` -> `running` -> `complete` or `failed` (with a reason code).
"""

from __future__ import annotations

from mcp_privacy_guard.errors import BadInput, Refused
from mcp_privacy_guard.store import Store

STATE = "warmup_state:"
REASON = "warmup_reason:"
STATES = ("not-started", "running", "complete", "failed")
REASONS = ("timeout", "tool-missing", "tool-error", "learn-failed")
FIX = "start a new conversation (/clear) to retry, fix the profile's warm-up, or exempt the server"


def register(store: Store, alias: str) -> None:
    if store.meta_get(STATE + alias) is None:
        store.meta_set(STATE + alias, "not-started")


def set_state(store: Store, alias: str, state: str, reason: str | None = None) -> None:
    if state not in STATES[1:]:
        raise BadInput("bad-state", "the warm-up state is not valid")
    if state == "failed" and reason not in REASONS:
        raise BadInput("bad-reason", "a failed warm-up needs a known reason")
    store.meta_set(STATE + alias, state)
    store.meta_set(REASON + alias, reason if state == "failed" and reason else "")


def summary(store: Store) -> tuple[list[str], list[str]]:
    """(servers still loading, servers whose warm-up failed), each sorted."""
    pending, failed = [], []
    for key, value in sorted(store.meta_items(STATE).items()):
        alias = key[len(STATE) :]
        if value in ("not-started", "running"):
            pending.append(alias)
        elif value == "failed":
            failed.append(alias)
    return pending, failed


def check_gate(store: Store) -> None:
    """Refuse (exit 4) while a warm-up is pending or after one failed; touch nothing."""
    pending, failed = summary(store)
    if failed:
        reason = store.meta_get(REASON + failed[0]) or "unknown"
        raise Refused(
            "warmup-failed",
            "loading the names of a server failed, so questions cannot be checked",
            FIX,
            {"servers": failed, "reason": reason},
        )
    if pending:
        raise Refused(
            "warmup-pending",
            "the names of a server are still loading",
            "try again in a moment",
            {"servers": pending},
        )
