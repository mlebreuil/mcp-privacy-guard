"""T016: MAC, DIGITS and TEXT stand-ins."""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st
from tests.conftest import KEY, OTHER_KEY

from mcp_privacy_guard.standins import misc

MAC = st.binary(min_size=6, max_size=6).map(lambda b: ":".join(f"{x:02x}" for x in b))


def test_mac_form() -> None:
    out = misc.mac(KEY, "00:1b:17:aa:bb:cc")
    assert re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", out)
    assert misc.mac(KEY, "00-1B-17-AA-BB-CC") == misc.mac(KEY, "00-1b-17-aa-bb-cc")
    assert "-" in misc.mac(KEY, "00-1b-17-aa-bb-cc")


def test_mac_is_locally_administered_unicast() -> None:
    # Bits 0-1 of the first octet are fixed (locally administered, unicast), the other 46
    # are permuted, so the map stays a bijection (Principle IV).
    for mac in ["00:1b:17:aa:bb:cc", "ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:01"]:
        assert int(misc.mac(KEY, mac)[:2], 16) & 0b11 == 0b10


@given(st.lists(MAC, min_size=2, max_size=40, unique=True))
def test_mac_is_injective(macs: list[str]) -> None:
    assert len({misc.mac(KEY, m) for m in macs}) == len(macs)


def test_mac_hides_the_vendor_prefix() -> None:
    assert misc.mac(KEY, "00:1b:17:aa:bb:cc")[:8] != "00:1b:17"
    assert misc.mac(KEY, "00:1b:17:aa:bb:cc") != misc.mac(OTHER_KEY, "00:1b:17:aa:bb:cc")


@given(
    st.integers(7, 20).flatmap(
        lambda n: st.lists(
            st.text("0123456789", min_size=n, max_size=n), min_size=2, max_size=30, unique=True
        )
    )
)
def test_digits_keep_length_and_never_collide(values: list[str]) -> None:
    outs = [misc.digits(KEY, v) for v in values]
    assert all(len(o) == len(values[0]) and o.isdigit() for o in outs)
    assert len(set(outs)) == len(values)


def test_digits_are_keyed_and_deterministic() -> None:
    assert misc.digits(KEY, "007951000123456") == misc.digits(KEY, "007951000123456")
    assert misc.digits(KEY, "007951000123456") != misc.digits(OTHER_KEY, "007951000123456")
    assert misc.digits(KEY, "007951000123456") != "007951000123456"


def test_text() -> None:
    out = misc.text(KEY, "Gateway of the Paris office")
    assert re.fullmatch(r"text-[a-z2-7]{8}", out)
    assert misc.text(KEY, "Gateway of the Paris office") == out
    assert misc.text(KEY, "Another description") != out
