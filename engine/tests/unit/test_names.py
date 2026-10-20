"""T014: one type-independent name stand-in (FR-009, contracts/standin-formats.md)."""

from __future__ import annotations

import re

from mcp_privacy_guard.store import Store
from tests.conftest import KEY, OTHER_KEY

from mcp_privacy_guard.standins import names, pseudonymize

NAME = re.compile(r"^n-[a-z2-7]{6}$")


def make(key: bytes, real: str, taken: set[str] | None = None) -> tuple[str, int]:
    return names.make(key, real, lambda token: token in (taken or set()))


def test_shape_and_determinism() -> None:
    standin, attempt = make(KEY, "fw-paris-01")
    assert NAME.match(standin) and attempt == 0
    assert make(KEY, "fw-paris-01") == (standin, 0)
    assert make(KEY, "fw-paris-02")[0] != standin


def test_different_secret_gives_different_standin() -> None:
    assert make(KEY, "fw-paris-01")[0] != make(OTHER_KEY, "fw-paris-01")[0]


def test_collision_bumps_attempt_and_lengthens_token() -> None:
    first, _ = make(KEY, "fw-paris-01")
    standin, attempt = make(KEY, "fw-paris-01", taken={first[2:]})
    assert attempt == 1
    assert re.match(r"^n-[a-z2-7]{8}$", standin)
    assert standin != first


def test_token_length_and_alphabet() -> None:
    assert re.match(r"^[a-z2-7]{6}$", names.token(KEY, "name", "x", 6))
    assert len(names.token(KEY, "text", "x", 8)) == 8
    assert names.token(KEY, "name", "x", 6) != names.token(KEY, "text", "x", 6)


def test_same_stand_in_whatever_the_kind() -> None:
    store = Store.ephemeral(KEY)
    a = pseudonymize("RULE_NAME", "fw-paris-01", store, KEY)
    b = pseudonymize("DEVICE_NAME", "fw-paris-01", store, KEY)
    c = pseudonymize("NAME", "fw-paris-01", store, KEY)
    assert a == b == c and NAME.match(a)
    row = store.lookup_standin(a)
    assert row is not None and row["kind"] == "NAME" and row["real"] == "fw-paris-01"


def test_distinct_names_never_share_a_stand_in() -> None:
    store = Store.ephemeral(KEY)
    out = {pseudonymize("NAME", f"host-{i}", store, KEY) for i in range(2000)}
    assert len(out) == 2000
