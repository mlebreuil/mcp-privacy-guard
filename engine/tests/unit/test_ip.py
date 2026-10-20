"""T013: keyed Crypto-PAn for IP stand-ins (contracts/standin-formats.md)."""

from __future__ import annotations

import ipaddress as ia

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests.conftest import KEY, OTHER_KEY

from mcp_privacy_guard.standins import ip

V4 = st.integers(0, 2**32 - 1).map(ia.IPv4Address)
V6 = st.integers(0, 2**128 - 1).map(ia.IPv6Address)
ADDR = st.one_of(V4, V6)

SPECIAL_V4 = [
    "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24",
    "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
]  # fmt: skip
SPECIAL_V6 = ["::1/128", "fc00::/7", "fe80::/10", "ff00::/8", "2001:db8::/32"]
SPECIAL = [ia.ip_network(n) for n in SPECIAL_V4 + SPECIAL_V6]


def special_block(addr: ia.IPv4Address | ia.IPv6Address) -> ia.IPv4Network | ia.IPv6Network | None:
    for net in SPECIAL:
        if addr.version == net.version and addr in net:
            return net
    return None


def common_prefix(a: ia.IPv4Address | ia.IPv6Address, b: ia.IPv4Address | ia.IPv6Address) -> int:
    width = a.max_prefixlen
    diff = int(a) ^ int(b)
    return width if diff == 0 else width - diff.bit_length()


def permute(addr: ia.IPv4Address | ia.IPv6Address) -> ia.IPv4Address | ia.IPv6Address:
    return ia.ip_address(ip.permute(KEY, str(addr)))


@given(ADDR)
def test_round_trip_and_bijection(addr: ia.IPv4Address | ia.IPv6Address) -> None:
    out = ip.permute(KEY, str(addr))
    assert ip.invert(KEY, out) == str(addr)


@given(ADDR, ADDR)
def test_shared_prefix_length_is_preserved(a: ia.IPv4Address, b: ia.IPv4Address) -> None:
    if a.version != b.version:
        return
    assert common_prefix(permute(a), permute(b)) == common_prefix(a, b)


@given(ADDR)
def test_distinct_inputs_give_distinct_outputs(a: ia.IPv4Address | ia.IPv6Address) -> None:
    b = type(a)(int(a) ^ 1)
    assert permute(a) != permute(b)


@pytest.mark.parametrize("block", SPECIAL_V4 + SPECIAL_V6)
def test_special_blocks_keep_their_block(block: str) -> None:
    net = ia.ip_network(block)
    first = int(net.network_address)
    step = max(1, net.num_addresses // 50)
    for offset in range(0, net.num_addresses, step):
        addr = type(net.network_address)(first + offset)
        assert permute(addr) in net


@given(V4)
def test_public_v4_keeps_first_octet_and_publicness(addr: ia.IPv4Address) -> None:
    if special_block(addr):
        return
    out = permute(addr)
    assert int(out) >> 24 == int(addr) >> 24
    assert special_block(out) is None


@given(st.integers(0x2000 << 112, (0x4000 << 112) - 1).map(ia.IPv6Address))
def test_public_v6_keeps_first_16_bits_and_publicness(addr: ia.IPv6Address) -> None:
    if special_block(addr):
        return
    out = permute(addr)
    assert int(out) >> 112 == int(addr) >> 112
    assert special_block(out) is None


@pytest.mark.parametrize(
    "value",
    ["0.0.0.0/0", "0.0.0.0", "255.255.255.0", "255.255.0.0", "255.255.255.255", "any", "::", "::1"],  # noqa: S104
)
def test_unchanged_values(value: str) -> None:
    assert ip.permute(KEY, value) == value
    assert ip.invert(KEY, value) == value


@given(V4, st.integers(8, 30))
def test_prefix_contains_the_stand_in_of_its_hosts(host: ia.IPv4Address, length: int) -> None:
    net = ia.ip_network(f"{host}/{length}", strict=False)
    out_net = ia.ip_network(ip.permute(KEY, str(net)))  # strict: host bits must be zero
    assert out_net.prefixlen == length
    assert permute(host) in out_net
    assert ip.invert(KEY, str(out_net)) == str(net)


@given(V4, st.integers(8, 30))
def test_interface_address_with_prefix_round_trips(host: ia.IPv4Address, length: int) -> None:
    text = f"{host}/{length}"
    if ia.ip_interface(text).network.network_address == host:
        return  # that one is a network, covered above
    out = ip.permute(KEY, text)
    assert out.endswith(f"/{length}")
    assert ia.ip_address(out.split("/")[0]) != ia.ip_network(out, strict=False).network_address
    assert ip.invert(KEY, out) == text


def test_documented_prefix_example() -> None:
    net = ia.ip_network(ip.permute(KEY, "10.1.2.0/24"))
    assert ia.ip_address(ip.permute(KEY, "10.1.2.15")) in net
    assert str(net).endswith("/24") and net.network_address in ia.ip_network("10.0.0.0/8")


@given(V4, V4)
def test_ranges_stay_ordered_and_round_trip(a: ia.IPv4Address, b: ia.IPv4Address) -> None:
    lo, hi = sorted([a, b])
    text = f"{lo}-{hi}"
    out = ip.permute(KEY, text)
    out_lo, out_hi = (ia.ip_address(p) for p in out.split("-"))
    assert out_lo <= out_hi
    assert ip.invert(KEY, out) == text


def test_wildcards_keep_the_known_octets_consistent() -> None:
    out = ip.permute(KEY, "10.1.*.*")
    assert out.endswith(".*.*")
    host = ip.permute(KEY, "10.1.2.15")
    assert host.split(".")[:2] == out.split(".")[:2]
    assert ip.invert(KEY, out) == "10.1.*.*"


def test_a_different_key_gives_a_different_permutation() -> None:
    sample = [f"52.10.{i}.7" for i in range(64)]
    same = [ip.permute(KEY, s) == ip.permute(OTHER_KEY, s) for s in sample]
    assert not all(same)


def test_not_an_address_is_left_alone() -> None:
    for value in ["fw-paris-01", "300.1.1.1", "1.2.3", ""]:
        assert ip.permute(KEY, value) == value
