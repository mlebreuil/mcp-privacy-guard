"""Free text: the MIXED rule (research R4), shared by results, prompts and errors.

Embedded values of a known shape and known names are replaced in place. The unit is kept
only when every other word is a plain one (vocabulary or common word); otherwise the whole
unit becomes a `text-…` stand-in. A unit is a JSON string or one line of plain text.
"""

from __future__ import annotations

import re

from mcp_privacy_guard.classify import shapes
from mcp_privacy_guard.classify.vocabulary import is_common_word, is_safe_word
from mcp_privacy_guard.config import Config
from mcp_privacy_guard.profiles.loader import Profile
from mcp_privacy_guard.standins import pseudonymize
from mcp_privacy_guard.store import Store

_PUNCT = ".,;:!?()[]{}<>\"'`*"
_PARTS = re.compile(r"[=:|]")  # not - _ /: a hyphenated token is a name unless it is known


def _plain(part: str, profile: Profile) -> bool:
    if part == "" or is_safe_word(part) or is_common_word(part):
        return True
    if part.lower() in profile.vocabulary or shapes.is_safe_form(part):
        return True
    return False


_QUOTED = re.compile(r"""^[(\[{]*(['"`])(.+)\1[)\]},.;:!?]*$""")


def _quoted_plain(inner: str, profile: Profile) -> bool:
    """A quoted word names an item, so only vocabulary may stay quoted."""
    return is_safe_word(inner) or inner.lower() in profile.vocabulary or shapes.is_safe_form(inner)


def plain_words(text: str, profile: Profile) -> bool:
    """True when every word of `text` is vocabulary, a common word or a safe form."""
    for token in text.split():
        quoted = _QUOTED.match(token)
        if quoted is not None:
            if not _quoted_plain(quoted.group(2), profile):
                return False
            continue
        core = token.strip(_PUNCT)
        if core and not (
            _plain(core, profile) or all(_plain(p, profile) for p in _PARTS.split(core))
        ):
            return False
    return True


def hide_block(text: str, *, store: Store) -> str:
    return pseudonymize("TEXT", text, store, store.key)


def mixed(text: str, *, store: Store, profile: Profile, config: Config, server: str) -> str:
    if not text.strip():
        return text
    hidden = [*config.hide_values, *config.hide_files]
    if any(value and value in text for value in hidden):
        return hide_block(text, store=store)

    spans: list[tuple[int, int, str]] = list(shapes.find_embedded(text))
    for start, end in store.name_index().spans(text):
        if all(end <= s or start >= e for s, e, _ in spans):
            spans.append((start, end, "NAME"))
    spans.sort()

    rest, last = [], 0
    for start, end, _ in spans:
        rest.append(text[last:start])
        last = end
    rest.append(text[last:])
    if not plain_words(" ".join(rest), profile):
        return hide_block(text, store=store)

    out, last = [], 0
    for start, end, kind in spans:
        out.append(text[last:start])
        out.append(pseudonymize(kind, text[start:end], store, store.key))
        last = end
    out.append(text[last:])
    return "".join(out)
