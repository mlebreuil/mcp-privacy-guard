"""T017: shape detection, whole values and embedded in text."""

from __future__ import annotations

import pytest

from mcp_privacy_guard.classify import shapes


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("10.1.2.15", "IP"),
        ("10.1.2.0/24", "IP"),
        ("10.1.2.1-10.1.2.50", "IP"),
        ("10.1.*.*", "IP"),
        ("2a01:e0a::5", "IP"),
        ("2a01:e0a::/32", "IP"),
        ("https://intranet.corp.example.com/hr", "URL"),
        ("jdoe@corp.example.com", "EMAIL"),
        ("00:1b:17:aa:bb:cc", "MAC"),
        ("00-1B-17-AA-BB-CC", "MAC"),
        ("CORP\\jdoe", "USER"),
        ("app.corp.example.com", "FQDN"),
        ("1234567", "DIGITS"),
        ("007951000123456", "DIGITS"),
    ],
)
def test_whole_value_kinds(value: str, kind: str) -> None:
    assert shapes.classify_whole(value) == kind


@pytest.mark.parametrize(
    "value",
    ["fw-paris-01", "app.local", "300.1.1.1", "1.2.3", "123456", "allow", "", "web server"],
)
def test_whole_values_without_an_identifying_shape(value: str) -> None:
    assert shapes.classify_whole(value) is None


def test_fqdn_needs_a_public_suffix() -> None:
    assert shapes.classify_whole("host.example.co.uk") == "FQDN"
    assert shapes.classify_whole("host.internal") is None


def test_embedded_spans() -> None:
    text = (
        "Connection from 10.1.2.15 to app.corp.example.com by CORP\\jdoe "
        "(jdoe@corp.example.com) mac 00:1b:17:aa:bb:cc see https://wiki.corp.example.com/x"
    )
    found = {(text[s:e], kind) for s, e, kind in shapes.find_embedded(text)}
    assert found == {
        ("10.1.2.15", "IP"),
        ("app.corp.example.com", "FQDN"),
        ("CORP\\jdoe", "USER"),
        ("jdoe@corp.example.com", "EMAIL"),
        ("00:1b:17:aa:bb:cc", "MAC"),
        ("https://wiki.corp.example.com/x", "URL"),
    }


def test_embedded_spans_do_not_overlap() -> None:
    text = "mail jdoe@corp.example.com or open https://a.example.com/p?q=10.1.2.3 now"
    spans = sorted(shapes.find_embedded(text))
    for (_, end, _), (start, _, _) in zip(spans, spans[1:], strict=False):
        assert end <= start


def test_embedded_none() -> None:
    assert shapes.find_embedded("The rule allows web traffic on port 443") == []


@pytest.mark.parametrize(
    "value",
    ["2026-10-20T10:15:00Z", "2026-10-20T10:15:00+02:00", "2026-10-20", "2026/10/20 10:15:00",
     "PT5M", "1h30m", "00:05:30", "42", "123456"],
)  # fmt: skip
def test_safe_forms(value: str) -> None:
    assert shapes.is_safe_form(value)


@pytest.mark.parametrize("value", ["1234567", "10.1.2.3", "fw-1", "jdoe@corp.example.com"])
def test_not_safe_forms(value: str) -> None:
    assert not shapes.is_safe_form(value)
