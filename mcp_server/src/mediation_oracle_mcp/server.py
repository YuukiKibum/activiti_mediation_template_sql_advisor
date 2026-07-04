from mcp.server.fastmcp import FastMCP

from mediation_oracle_mcp.config import get_settings
from mediation_oracle_mcp.tools import register_tools


settings = get_settings()

mcp = FastMCP(settings.server_name)

register_tools(mcp)


def main() -> None:
    """
    Start the Activiti Mediation Oracle MCP server.

    For local development, we use stdio transport.

    With stdio, the MCP server communicates through standard input/output.
    It may look like the terminal is waiting silently. That is normal.
    """
    mcp.run(transport=settings.transport)


if __name__ == "__main__":
    main()