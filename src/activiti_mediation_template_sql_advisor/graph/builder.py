from __future__ import annotations

import asyncio

from langgraph.graph import END, START, StateGraph

from activiti_mediation_template_sql_advisor.graph.nodes.dsl_expression import (
    dsl_expression_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.final_response import (
    final_response_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.oracle_inspection import (
    oracle_inspection_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.request_planner import (
    request_planner_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.sql_generation import (
    sql_generation_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.template_resolution import (
    template_resolution_node,
)
from activiti_mediation_template_sql_advisor.graph.state import (
    AdvisorState,
    create_initial_state,
)


def build_advisor_graph():
    """
    Build the clean Activiti Mediation Template SQL Advisor graph.

    Safer flow:
        request_planner
          -> template_resolution
          -> oracle_inspection
          -> dsl_expression
          -> sql_generation
          -> final_response

    Why Oracle before DSL?
    - Oracle MCP can fetch current working ATTRIBUTE_VALUE examples.
    - DSL compilation can pattern-match against real rows from the same TEMPLATE_ID.
    - This follows the project prompt guidance for ACT_MEDIATION_PARAMETER.
    """
    graph = StateGraph(AdvisorState)

    graph.add_node("request_planner", request_planner_node)
    graph.add_node("template_resolution", template_resolution_node)
    graph.add_node("oracle_inspection", oracle_inspection_node)
    graph.add_node("dsl_expression", dsl_expression_node)
    graph.add_node("sql_generation", sql_generation_node)
    graph.add_node("final_response", final_response_node)

    graph.add_edge(START, "request_planner")
    graph.add_edge("request_planner", "template_resolution")
    graph.add_edge("template_resolution", "oracle_inspection")
    graph.add_edge("oracle_inspection", "dsl_expression")
    graph.add_edge("dsl_expression", "sql_generation")
    graph.add_edge("sql_generation", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile()


async def run_advisor(user_requirement: str) -> AdvisorState:
    graph = build_advisor_graph()
    initial_state = create_initial_state(user_requirement)
    final_state = await graph.ainvoke(initial_state)
    return final_state


async def main() -> None:
    requirement = (
        "For Prepaid Base Plan ECM request, rename attribute poAttributes "
        "to poAttributes_Test."
    )

    final_state = await run_advisor(requirement)

    print(final_state.get("final_answer", ""))


if __name__ == "__main__":
    asyncio.run(main())