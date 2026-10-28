"""The generic server has one tool with an argument (live check 17: what a server receives)."""

from __future__ import annotations

import sys

import anyio
from tests.conftest import ROOT


def build():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(ROOT / "testservers" / "generic"))
    import server

    return server.build()


def test_echo_is_listed_and_returns_what_it_received() -> None:
    async def run() -> tuple[list[str], str]:
        srv = build()
        names = [t.name for t in await srv.list_tools()]
        out = await srv.call_tool("echo", {"value": "10.1.2.15"})
        return names, str(out)

    names, out = anyio.run(run)
    assert "echo" in names
    assert "received: 10.1.2.15" in out
