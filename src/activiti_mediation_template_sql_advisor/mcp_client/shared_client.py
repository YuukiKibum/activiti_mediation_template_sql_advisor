from __future__ import annotations

import asyncio
from typing import Any

from activiti_mediation_template_sql_advisor.mcp_client.oracle_mcp_client import (
    OracleMCPClient,
)


class OracleMCPClientManager:
    """
    Keep one MCP subprocess/session alive for the web app process.

    MCP stdio transport is effectively single-flight, so tool calls are
    serialized with an asyncio lock while still avoiding per-request process
    startup cost.
    """

    _client: OracleMCPClient | None = None
    _lifecycle_lock = asyncio.Lock()
    _tool_lock = asyncio.Lock()

    @classmethod
    async def start(cls) -> None:
        async with cls._lifecycle_lock:
            if cls._client is None:
                client = OracleMCPClient()
                await client.__aenter__()
                cls._client = client

    @classmethod
    async def stop(cls) -> None:
        async with cls._lifecycle_lock:
            if cls._client is not None:
                await cls._client.__aexit__(None, None, None)
                cls._client = None

    @classmethod
    async def get(cls) -> OracleMCPClient:
        if cls._client is None:
            await cls.start()

        if cls._client is None:
            raise RuntimeError("Shared Oracle MCP client failed to start.")

        return cls._client

    @classmethod
    async def call_tool(cls, tool_name: str, arguments: dict[str, Any]) -> object:
        client = await cls.get()

        async with cls._tool_lock:
            return await client._call_tool(tool_name, arguments)
