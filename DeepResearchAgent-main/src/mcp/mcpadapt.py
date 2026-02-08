"""Core module for the MCPAdapt library.

This module contains the core functionality for the MCPAdapt library. It provides the
basic interfaces and classes for adapting tools from MCP to the desired Agent framework.
"""
import asyncio
from typing import Any, Dict, Optional
try:
    from fastmcp import Client
except ImportError:
    Client = None

from src.mcp.adapter import AsyncToolAdapter, ToolAdapter

class MCPAdapt():
    def __init__(
        self,
        config: Dict[str, Any],
        adapter: Optional[ToolAdapter] = None,
    ):
        """
        Manage the MCP server / client lifecycle and expose tools adapted with the adapter.
        """

        if adapter is None:
            adapter = AsyncToolAdapter()

        self.config = config
        self.adapter = adapter
        
        if Client is None:
             # Just a placeholder if fastmcp is missing
             self.client = None
        else:
             self.client = Client(config)

    async def tools(self):
        if self.client is None:
            return {}

        async with self.client as client:
            mcp_tools = await client.list_tools()

        mcp_tools = await asyncio.gather(*[
            self.adapter.adapt(client, tool)
            for tool in mcp_tools
        ])

        mcp_tools = {
            tool.name: tool
            for tool in mcp_tools
        }

        return mcp_tools

async def main():
    config = {
        "mcpServers": {
            # Local stdio server
            "weather": {
                "command": "python",
                "args": ["server.py"],
                "env": {"DEBUG": "true"}
            },
        }
    }

    mcpadapt = MCPAdapt(
        config,
        AsyncToolAdapter()
    )

    tools = await mcpadapt.tools()
    for name, tool in tools.items():
        print(f"Tool Name: {name}")
        print(f"Tool Description: {tool.description}")
        print("-" * 40)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())