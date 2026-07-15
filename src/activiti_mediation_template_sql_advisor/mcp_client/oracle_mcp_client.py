import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MCP_SERVER_SRC = PROJECT_ROOT / "mcp_server" / "src"


class OracleMCPClient:
    """
    Main application MCP client for the Oracle mediation MCP server.

    This class is used by the main LangGraph app to call MCP tools.

    Important:
    - This client does not connect to Oracle directly.
    - This client talks to the MCP server.
    - The MCP server talks to Oracle.
    """

    def __init__(self) -> None:
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "OracleMCPClient":
        """
        Start the MCP server process and open an MCP client session.
        """
        self._exit_stack = AsyncExitStack()

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "mediation_oracle_mcp.server",
            ],
            env={
                **os.environ,
                "PYTHONPATH": str(MCP_SERVER_SRC),
            },
        )

        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        await self._session.initialize()

        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        """
        Close the MCP client session and stop the server process.
        """
        if self._exit_stack:
            await self._exit_stack.aclose()

        self._session = None
        self._exit_stack = None

    def _require_session(self) -> ClientSession:
        """
        Make sure the client is being used inside an async context manager.

        Correct:
            async with OracleMCPClient() as client:
                await client.get_table_counts()

        Incorrect:
            client = OracleMCPClient()
            await client.get_table_counts()
        """
        if self._session is None:
            raise RuntimeError(
                "OracleMCPClient session is not initialized. "
                "Use it with: async with OracleMCPClient() as client:"
            )

        return self._session

    @staticmethod
    def _unwrap_tool_response(response: Any) -> Any:
        """
        Convert MCP CallToolResult into normal Python data.

        MCP responses usually contain:
            - content: text-friendly output
            - structuredContent: JSON-friendly output
            - isError: whether the tool failed

        Our LangGraph nodes should use the structured data.
        """
        response_dict = response.model_dump()

        if response_dict.get("isError"):
            raise RuntimeError(f"MCP tool returned an error: {response_dict}")

        structured_content = response_dict.get("structuredContent")

        if structured_content is not None:
            # FastMCP sometimes wraps optional/dynamic return values like:
            # {"result": {...}}
            if (
                isinstance(structured_content, dict)
                and set(structured_content.keys()) == {"result"}
            ):
                return structured_content["result"]

            return structured_content

        content_items = response_dict.get("content") or []

        if content_items:
            first_text = content_items[0].get("text")

            if first_text:
                try:
                    return json.loads(first_text)
                except json.JSONDecodeError:
                    return first_text

        return None

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call one MCP tool and return clean Python data.
        """
        session = self._require_session()

        response = await session.call_tool(
            tool_name,
            arguments=arguments,
        )

        return self._unwrap_tool_response(response)

    async def list_tools(self) -> list[str]:
        """
        Return available MCP tool names.
        """
        session = self._require_session()

        tools_response = await session.list_tools()

        return [tool.name for tool in tools_response.tools]

    async def get_table_counts(self) -> dict[str, int]:
        """
        Return row counts for ACT_MEDIATION_TEMPLATE and ACT_MEDIATION_PARAMETER.
        """
        return await self._call_tool(
            "get_table_counts",
            arguments={},
        )

    async def template_exists(self, template_id: str) -> dict[str, Any]:
        """
        Check whether a TEMPLATE_ID exists.
        """
        return await self._call_tool(
            "template_exists",
            arguments={
                "template_id": template_id,
            },
        )

    async def get_template(self, template_id: str) -> dict[str, Any] | None:
        """
        Fetch one ACT_MEDIATION_TEMPLATE row.
        """
        return await self._call_tool(
            "get_template",
            arguments={
                "template_id": template_id,
            },
        )

    async def list_parameters_for_template(
        self,
        template_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List ACT_MEDIATION_PARAMETER rows for one TEMPLATE_ID.
        """
        return await self._call_tool(
            "list_parameters_for_template",
            arguments={
                "template_id": template_id,
                "limit": limit,
            },
        )

    async def get_parameter(
        self,
        template_id: str,
        attribute_name: str,
    ) -> dict[str, Any] | None:
        """
        Fetch one ACT_MEDIATION_PARAMETER row.
        """
        return await self._call_tool(
            "get_parameter",
            arguments={
                "template_id": template_id,
                "attribute_name": attribute_name,
            },
        )

    async def search_templates(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_TEMPLATE.
        """
        return await self._call_tool(
            "search_templates",
            arguments={
                "keyword": keyword,
                "limit": limit,
            },
        )

    async def search_parameters(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_PARAMETER.
        """
        return await self._call_tool(
            "search_parameters",
            arguments={
                "keyword": keyword,
                "limit": limit,
            },
        )

    async def inspect_template_for_advisor(
        self,
        template_id: str,
        attribute_name: str = "",
        target_attribute_name: str = "",
        focus_attribute_name: str = "",
        sample_limit: int = 20,
    ) -> dict[str, Any]:
        """
        Fetch advisor inspection context in one MCP round-trip.
        """
        return await self._call_tool(
            "inspect_template_for_advisor",
            arguments={
                "template_id": template_id,
                "attribute_name": attribute_name,
                "target_attribute_name": target_attribute_name,
                "focus_attribute_name": focus_attribute_name,
                "sample_limit": sample_limit,
            },
        )


async def main() -> None:
    """
    Small manual test for this reusable client.

    Run with:
        uv run python -m activiti_mediation_template_sql_advisor.mcp_client.oracle_mcp_client
    """
    async with OracleMCPClient() as client:
        tools = await client.list_tools()
        print("Available MCP tools:")
        print(json.dumps(tools, indent=2))

        counts = await client.get_table_counts()
        print("\nTable counts:")
        print(json.dumps(counts, indent=2))

        exists = await client.template_exists("MT_ECM_PRE_BASEPLAN")
        print("\nTemplate exists:")
        print(json.dumps(exists, indent=2))

        parameter = await client.get_parameter(
            template_id="MT_ECM_PRE_BASEPLAN",
            attribute_name="poAttributes",
        )
        print("\nParameter:")
        print(json.dumps(parameter, indent=2))


if __name__ == "__main__":
    asyncio.run(main())