from __future__ import annotations

import asyncio

from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.builder import get_advisor_graph
from activiti_mediation_template_sql_advisor.mcp_client.shared_client import (
    OracleMCPClientManager,
)


async def warmup_application() -> None:
    """
    Preload expensive startup work for the web app and advisor runtime.

    - Compiled LangGraph
    - Cached ATTRIBUTE_VALUE rulebook prompt summary
    - Shared Oracle MCP subprocess/session
    """
    get_advisor_graph()
    get_rulebook_prompt_summary()
    await OracleMCPClientManager.start()


async def shutdown_application() -> None:
    await OracleMCPClientManager.stop()
