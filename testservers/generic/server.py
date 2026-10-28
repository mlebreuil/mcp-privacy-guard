"""Dev-only generic MCP server (stdio) for the guard's tests. It returns seeded "real" values.

Run: `uv run --project engine python testservers/generic/server.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult

sys.path.insert(0, str(Path(__file__).parent))
import results  # noqa: E402


def build() -> MCPServer:
    server = MCPServer(name="generic", instructions="Returns seeded values for guard tests.")

    def register(name: str) -> None:
        build_result = results.TOOLS[name]

        async def tool() -> CallToolResult:
            return CallToolResult.model_validate(build_result())

        server.add_tool(tool, name=name, description=f"{name} (test data)", structured_output=False)

    for tool_name in results.TOOLS:
        register(tool_name)

    @server.tool(name="echo", description="Returns the value it received (live check 17).")
    def echo(value: str) -> str:
        return f"received: {value}"

    return server


if __name__ == "__main__":
    anyio.run(build().run_stdio_async)
