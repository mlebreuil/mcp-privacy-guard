"""T015: FQDN, URL, e-mail, user and group stand-ins."""

from __future__ import annotations

import re

from tests.conftest import KEY

from mcp_privacy_guard.standins import domains

H = r"h-[a-z2-7]{6}"
D = r"d-[a-z2-7]{6}"


def test_fqdn_labels_replaced_suffix_kept() -> None:
    out = domains.fqdn(KEY, "app.corp.example.com")
    assert re.fullmatch(rf"{H}\.{D}\.{D}\.com", out)
    assert re.fullmatch(rf"{H}\.{D}\.{D}\.co\.uk", domains.fqdn(KEY, "app.corp.example.co.uk"))


def test_hosts_under_one_parent_share_the_parent() -> None:
    a = domains.fqdn(KEY, "app.corp.example.com")
    b = domains.fqdn(KEY, "db.corp.example.com")
    assert a != b
    assert a.split(".", 1)[1] == b.split(".", 1)[1]


def test_same_input_same_output() -> None:
    assert domains.fqdn(KEY, "app.corp.example.com") == domains.fqdn(KEY, "app.corp.example.com")


def test_url_keeps_scheme_and_port_and_hides_path() -> None:
    out = domains.url(KEY, "https://intranet.corp.example.com:8443/hr?id=3#top")
    host = domains.fqdn(KEY, "intranet.corp.example.com")
    assert out == f"https://{host}:8443/" + out.rsplit("/", 1)[1]
    assert re.fullmatch(r"p-[a-z2-7]{6}", out.rsplit("/", 1)[1])
    assert "hr" not in out and "id=3" not in out


def test_url_without_path_has_none_added() -> None:
    host = domains.fqdn(KEY, "intranet.corp.example.com")
    assert domains.url(KEY, "http://intranet.corp.example.com") == f"http://{host}"


def test_email_uses_the_fqdn_stand_in() -> None:
    out = domains.email(KEY, "jdoe@corp.example.com")
    assert re.fullmatch(rf"u-[a-z2-7]{{6}}@{D}\.{D}\.com", out) or re.fullmatch(
        rf"u-[a-z2-7]{{6}}@{H}\.{D}\.com", out
    )
    assert out.split("@")[1] == domains.fqdn(KEY, "corp.example.com")
    assert domains.email(KEY, "jdoe@corp.example.com") != domains.email(
        KEY, "asmith@corp.example.com"
    )


def test_user_and_group_share_the_domain_part() -> None:
    user = domains.user(KEY, "CORP\\jdoe")
    group = domains.group(KEY, "CORP\\net-admins")
    assert re.fullmatch(r"dom-[a-z2-7]{6}\\u-[a-z2-7]{6}", user)
    assert re.fullmatch(r"dom-[a-z2-7]{6}\\g-[a-z2-7]{6}", group)
    assert user.split("\\")[0] == group.split("\\")[0]
    assert domains.user(KEY, "OTHER\\jdoe").split("\\")[0] != user.split("\\")[0]


def test_user_without_domain() -> None:
    assert re.fullmatch(r"u-[a-z2-7]{6}", domains.user(KEY, "jdoe"))
