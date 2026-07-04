import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def pretty_print(title: str, value) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(json.dumps(value, indent=2, default=str))


async def main() -> None:
    """
    Starts our MCP server through stdio and calls a few tools.

    This test proves:
    1. The MCP server starts.
    2. The MCP client can connect.
    3. The client can discover tools.
    4. The client can call Oracle-backed MCP tools.
    """

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "mediation_oracle_mcp.server",
        ],
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT / "mcp_server" / "src"),
        },
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools_response = await session.list_tools()
            tool_names = [tool.name for tool in tools_response.tools]

            pretty_print("AVAILABLE MCP TOOLS", tool_names)

            counts_response = await session.call_tool(
                "get_table_counts",
                arguments={},
            )

            pretty_print(
                "get_table_counts RESPONSE",
                counts_response.model_dump(),
            )

            template_exists_response = await session.call_tool(
                "template_exists",
                arguments={
                    "template_id": "MT_ECM_PRE_BASEPLAN",
                },
            )

            pretty_print(
                "template_exists RESPONSE",
                template_exists_response.model_dump(),
            )

            parameter_response = await session.call_tool(
                "get_parameter",
                arguments={
                    "template_id": "MT_ECM_PRE_BASEPLAN",
                    "attribute_name": "poAttributes",
                },
            )

            pretty_print(
                "get_parameter RESPONSE",
                parameter_response.model_dump(),
            )


if __name__ == "__main__":
    asyncio.run(main())