"""T044: MCP tool-result handling (contracts/engine-cli.md `result`)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from tests.conftest import KEY

from mcp_privacy_guard.config import Config
from mcp_privacy_guard.errors import Refused
from mcp_privacy_guard.profiles import loader
from mcp_privacy_guard.results import pseudonymize_result
from mcp_privacy_guard.store import Store


def run(result: dict[str, Any], **kw: Any) -> Any:
    return pseudonymize_result(
        result,
        store=kw.pop("store", None) or Store.ephemeral(KEY),
        profile=kw.pop("profile", None) or loader.load_bundled("default"),
        config=Config(),
        server="gen",
        tool="t",
        **kw,
    )


def text(body: str, *, error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": body}], "isError": error}


def test_json_text_is_walked_and_keeps_its_style() -> None:
    data = {"host": "app.corp.example.com", "ip": "10.1.2.15", "state": "allow"}
    for dump in (
        json.dumps(data, separators=(",", ":")),
        json.dumps(data),
        json.dumps(data, indent=2),
        json.dumps(data, indent=4),
    ):
        out = run(text(dump)).result["content"][0]["text"]
        parsed = json.loads(out)
        assert "corp" not in out and "10.1.2.15" not in out and parsed["state"] == "allow"
        assert ("\n" in out) == ("\n" in dump) and (", " in out) == (", " in dump)


def test_indentation_is_kept() -> None:
    out = run(text(json.dumps({"ip": "10.1.2.15"}, indent=2))).result["content"][0]["text"]
    assert out.startswith('{\n  "ip": "')


def test_a_summary_line_followed_by_json_is_handled_line_by_line() -> None:
    body = 'Found 1 device\n{"name":"fw-paris-01","ip":"10.1.2.15","count":3}'
    out = run(text(body)).result["content"][0]["text"]
    first, second = out.split("\n")
    assert first == "Found 1 device"
    parsed = json.loads(second)
    assert parsed["count"] == 3 and parsed["name"].startswith("n-") and "10.1.2.15" not in second


def test_plain_text_lines_use_the_mixed_rule() -> None:
    body = "connection from 10.1.2.15 allowed\nsecret handshake with fw-paris-01"
    out = run(text(body)).result["content"][0]["text"].split("\n")
    assert out[0].startswith("connection from 10.") and out[0].endswith("allowed")
    assert re.fullmatch(r"text-[a-z2-7]{8}", out[1])


def test_structured_content_is_walked() -> None:
    result = {
        "content": [{"type": "text", "text": "ok"}],
        "structuredContent": {"devices": [{"name": "fw-paris-01", "ip": "10.1.2.15"}]},
        "isError": False,
    }
    out = run(result).result
    device = out["structuredContent"]["devices"][0]
    assert device["name"].startswith("n-") and device["ip"] != "10.1.2.15"
    assert out["isError"] is False


def test_non_text_blocks_are_replaced_by_one_notice() -> None:
    result = {
        "content": [
            {"type": "text", "text": "topology"},
            {"type": "image", "data": "AAAA", "mimeType": "image/png"},
            {"type": "resource", "resource": {"uri": "file:///x", "text": "secret"}},
        ],
        "isError": False,
    }
    out = run(result)
    assert out.withheld == 2
    blocks = out.result["content"]
    assert [b["type"] for b in blocks] == ["text", "text"]
    assert blocks[-1]["text"] == "[privacy-guard: 2 non-text item(s) withheld]"
    assert "AAAA" not in json.dumps(out.result) and "secret" not in json.dumps(out.result)
    assert out.notices


def test_error_results_are_pseudonymized_too() -> None:
    out = run(text("Object x1 not found on 10.20.30.40", error=True), is_error=True)
    assert out.result["isError"] is True
    assert "10.20.30.40" not in out.result["content"][0]["text"]


def test_a_result_over_two_megabytes_is_refused() -> None:
    big = text("10.1.2.15 ok\n" * (2 * 1024 * 1024 // 12 + 10))
    with pytest.raises(Refused) as err:
        run(big)
    assert err.value.code == "too-large"


def test_a_result_that_takes_too_long_is_refused() -> None:
    with pytest.raises(Refused) as err:
        run(text("\n".join(f"10.1.{i % 250}.{i % 200} ok" for i in range(500))), time_limit=0.0)
    assert err.value.code == "timeout"


def test_same_real_value_same_stand_in_across_results() -> None:
    store = Store.ephemeral(KEY)
    a = run(text('{"ip":"10.1.2.15"}'), store=store).result["content"][0]["text"]
    b = run(text("seen 10.1.2.15 again"), store=store).result["content"][0]["text"]
    stand_in = json.loads(a)["ip"]
    assert stand_in in b


def test_the_reply_carries_the_withheld_count_and_notices() -> None:
    out = run(text("fine"))
    assert out.withheld == 0 and out.notices == []
