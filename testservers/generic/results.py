"""The generic test server's results, built from seed.json, as MCP tool-result dicts.

Pure functions, so the engine tests use them without starting the server.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).parent / "seed.json"
BIG_BYTES = 3 * 1024 * 1024


def seed() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def all_values() -> list[str]:
    """Every seed value, for the leak tests."""
    return [value for values in seed().values() for value in values]


def _text(text: str, is_error: bool = False) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def devices_data() -> dict[str, Any]:
    s = seed()
    rows = []
    for i, name in enumerate(s["devices"]):
        rows.append(
            {
                "name": name,
                "hostname": s["fqdns"][i % len(s["fqdns"])],
                "serial": s["serials"][i % len(s["serials"])],
                "ip": s["ips"][i % len(s["ips"])],
                "network": s["networks"][i % len(s["networks"])],
                "mac": s["macs"][i % len(s["macs"])],
                "owner": s["emails"][0],
                "admin": s["users"][i % len(s["users"])],
                "group": s["groups"][0],
                "url": s["urls"][0],
                "description": s["descriptions"][i % len(s["descriptions"])],
                "state": "connected",
                "severity": "info",
                "port": 443,
                "last_seen": "2026-10-20T10:15:00Z",
            }
        )
    return {"devices": rows, "count": len(rows)}


def list_devices() -> dict[str, Any]:
    """Structured JSON, as a tool with an output schema returns it."""
    data = devices_data()
    return {
        "content": [{"type": "text", "text": json.dumps(data, separators=(",", ":"))}],
        "structuredContent": data,
        "isError": False,
    }


def get_config() -> dict[str, Any]:
    """JSON inside a text block, indented."""
    s = seed()
    config = {
        "rules": [
            {
                "name": s["objects"][2],
                "source": [s["ips"][0], s["networks"][0]],
                "destination": [s["fqdns"][0], s["objects"][0]],
                "action": "allow",
                "description": s["descriptions"][0],
            },
            {
                "name": s["objects"][1],
                "source": [s["networks"][1]],
                "destination": [s["ips"][4]],
                "action": "deny",
                "description": s["descriptions"][1],
            },
        ]
    }
    return _text(json.dumps(config, indent=2))


def get_logs() -> dict[str, Any]:
    """Plain-text log lines."""
    s = seed()
    lines = [
        f"2026-10-20T10:15:00Z {s['users'][0]} {s['ips'][0]} -> {s['fqdns'][1]} allowed by "
        f"{s['objects'][2]} from {s['macs'][0]}",
        f"2026-10-20T10:15:03Z {s['users'][1]} {s['ips'][2]} -> {s['urls'][0]} blocked, "
        f"mail to {s['emails'][0]}",
        f"2026-10-20T10:16:09Z device {s['devices'][0]} serial {s['serials'][0]}: "
        f"{s['log_free_text'][0]}",
        f"2026-10-20T10:17:41Z {s['log_free_text'][1]}",
    ]
    return _text("\n".join(lines))


def failing() -> dict[str, Any]:
    """An error result that quotes real values."""
    s = seed()
    return _text(f"Object {s['objects'][0]} not found on {s['devices'][1]} ({s['ips'][1]})", True)


def image() -> dict[str, Any]:
    pixel = base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d4944415478da63fcffff3f0005fe02fea7d6e6d90000000049454e44ae426082"
        )
    ).decode()
    return {
        "content": [
            {"type": "text", "text": "topology"},
            {"type": "image", "data": pixel, "mimeType": "image/png"},
        ],
        "isError": False,
    }


def big() -> dict[str, Any]:
    line = f"{seed()['ips'][0]} ok\n"
    return _text(line * (BIG_BYTES // len(line) + 1))


def keyed() -> dict[str, Any]:
    """An object keyed by host names and addresses."""
    s = seed()
    data: dict[str, Any] = {}
    for fqdn, ip in zip(s["fqdns"], s["ips"], strict=False):
        data[fqdn] = {"address": ip, "state": "up"}
        data[ip] = {"hostname": fqdn, "state": "up"}
    data["summary"] = {"hosts": len(s["fqdns"]), "state": "up"}
    return _text(json.dumps(data))


TOOLS = {
    "list_devices": list_devices,
    "get_config": get_config,
    "get_logs": get_logs,
    "failing": failing,
    "image": image,
    "big": big,
    "keyed": keyed,
}
