"""FQDN, URL, e-mail and user/group stand-ins (contracts/standin-formats.md).

The labels below the public suffix are replaced (`h-` for the leftmost, `d-` for the others),
each by a token of the label *and its parents*, so hosts under one parent share the parent's
stand-in. The public suffix stays.
"""

from __future__ import annotations

import re

from mcp_privacy_guard import suffix
from mcp_privacy_guard.standins import ip as ipmod
from mcp_privacy_guard.standins.names import token

LABEL = 6
_URL = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*)://([^/?#]*)(.*)$", re.DOTALL)


def _chain_token(key: bytes, chain: str) -> str:
    return token(key, "label", chain.lower(), LABEL)


def fqdn_labels(key: bytes, host: str) -> tuple[list[str], str] | None:
    """The stand-in labels (leftmost `h-`, the rest `d-`) and the suffix, or None if unlisted."""
    split = suffix.split_host(host)
    if split is None:
        return None
    below, tld = split
    labels = host.split(".")
    out = []
    for idx in range(len(below)):
        prefix = "h" if idx == 0 else "d"
        out.append(f"{prefix}-{_chain_token(key, '.'.join(labels[idx:]))}")
    return out, tld


def parent_forms(key: bytes, host: str) -> list[tuple[str, str]]:
    """(real parent, its `d-` stand-in) for each parent of a host: they appear inside children."""
    split = suffix.split_host(host)
    if split is None:
        return []
    below, tld = split
    labels = host.split(".")
    pairs = []
    for start in range(1, len(below)):
        parts = [f"d-{_chain_token(key, '.'.join(labels[i:]))}" for i in range(start, len(below))]
        pairs.append((".".join(labels[start:]), ".".join([*parts, tld])))
    return pairs


def fqdn(key: bytes, host: str) -> str:
    built = fqdn_labels(key, host)
    if built is None:
        # no listed suffix: hide every label, as a name would be
        return ".".join(
            f"d-{_chain_token(key, '.'.join(host.split('.')[i:]))}"
            for i in range(len(host.split(".")))
        )
    out, tld = built
    return ".".join([*out, tld])


def _host(key: bytes, host: str) -> str:
    if host.startswith("[") and host.endswith("]"):
        return f"[{ipmod.permute(key, host[1:-1])}]"
    mapped = ipmod.permute(key, host)
    if mapped != host:
        return mapped
    return fqdn(key, host)


def url(key: bytes, text: str) -> str:
    match = _URL.match(text)
    if match is None:
        return fqdn(key, text)
    scheme, netloc, rest = match.groups()
    userinfo, at, hostport = netloc.rpartition("@")
    host, port = hostport, ""
    if not hostport.startswith("[") and ":" in hostport:
        host, _, port_digits = hostport.rpartition(":")
        port = f":{port_digits}"
    elif hostport.startswith("[") and "]:" in hostport:
        host, _, port_digits = hostport.rpartition(":")
        port = f":{port_digits}"
    out = f"{scheme}://"
    if at:
        out += f"u-{token(key, 'user', userinfo.lower(), LABEL)}@"
    out += _host(key, host) + port
    if rest not in ("", "/"):
        out += f"/p-{token(key, 'path', rest, LABEL)}"
    else:
        out += rest
    return out


def email(key: bytes, text: str) -> str:
    local, _, domain = text.rpartition("@")
    return f"u-{token(key, 'user', local.lower(), LABEL)}@{fqdn(key, domain)}"


def _dom(key: bytes, domain: str) -> str:
    return f"dom-{token(key, 'dom', domain.lower(), LABEL)}"


def user(key: bytes, text: str) -> str:
    domain, sep, name = text.partition("\\")
    if not sep:
        return f"u-{token(key, 'user', text.lower(), LABEL)}"
    return f"{_dom(key, domain)}\\u-{token(key, 'user', name.lower(), LABEL)}"


def group(key: bytes, text: str) -> str:
    domain, sep, name = text.partition("\\")
    if not sep:
        return f"g-{token(key, 'group', text.lower(), LABEL)}"
    return f"{_dom(key, domain)}\\g-{token(key, 'group', name.lower(), LABEL)}"
