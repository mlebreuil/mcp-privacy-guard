"""Stand-in generation: `pseudonymize` computes a stand-in and records it in the session."""

from __future__ import annotations

from mcp_privacy_guard.errors import Refused
from mcp_privacy_guard.standins import domains, ip, misc, names
from mcp_privacy_guard.store import Store

# Every other kind (a profile's name kinds: RULE_NAME, DEVICE_NAME...) is a NAME (FR-009).
CORE_KINDS = frozenset(
    {"IP", "FQDN", "URL", "MAC", "EMAIL", "USER", "GROUP", "NAME", "DIGITS", "TEXT"}
)
NAME_ATTEMPTS = 4


def core_kind(kind: str) -> str:
    return kind if kind in CORE_KINDS else "NAME"


def _record(store: Store, kind: str, real: str, standin: str) -> str:
    if standin == real:
        return standin  # an unchanged value (any, 0.0.0.0/0...) needs no mapping
    return store.issue(kind, real, standin)


def _record_fqdn_parts(store: Store, key: bytes, host: str) -> None:
    for real, standin in domains.parent_forms(key, host):
        _record(store, "FQDN_PARENT", real, standin)


def _name(store: Store, key: bytes, real: str) -> str:
    for _ in range(NAME_ATTEMPTS):
        standin, _attempt = names.make(key, real, store.token_taken)
        try:
            return store.issue("NAME", real, standin, token=standin[2:])
        except Refused as exc:
            if exc.code != "standin-collision":
                raise
    raise Refused("standin-collision", "no free stand-in could be found")


def pseudonymize(kind: str, real: str, store: Store, key: bytes) -> str:
    """The stand-in of `real` for `kind`, recorded in the session's mapping."""
    core = core_kind(kind)
    known = store.lookup_real(core, real)
    if known is not None:
        return str(known["standin"])
    if core == "NAME":
        return _name(store, key, real)
    if core == "IP":
        standin = ip.permute(key, real)
        clash = store.lookup_standin(standin)
        if standin != real and clash is not None and clash["fixed"]:
            # the stand-in would read as a fixed value the model saw unchanged (research R15)
            return _record(store, "TEXT", real, misc.text(key, real))
        return _record(store, "IP", real, standin)
    if core == "FQDN":
        _record_fqdn_parts(store, key, real)
        return _record(store, "FQDN", real, domains.fqdn(key, real))
    if core == "URL":
        return _record(store, "URL", real, domains.url(key, real))
    if core == "EMAIL":
        _record_fqdn_parts(store, key, real.rpartition("@")[2])
        return _record(store, "EMAIL", real, domains.email(key, real))
    if core == "USER":
        return _record(store, "USER", real, domains.user(key, real))
    if core == "GROUP":
        return _record(store, "GROUP", real, domains.group(key, real))
    if core == "MAC":
        return _record(store, "MAC", real, misc.mac(key, real))
    if core == "DIGITS":
        return _record(store, "DIGITS", real, misc.digits(key, real))
    return _record(store, "TEXT", real, misc.text(key, real))
