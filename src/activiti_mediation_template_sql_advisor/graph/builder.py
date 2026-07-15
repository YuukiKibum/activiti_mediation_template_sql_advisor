from __future__ import annotations

import asyncio
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from activiti_mediation_template_sql_advisor.dsl_compiler.node import dsl_expression_node
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
from activiti_mediation_template_sql_advisor.graph.telemetry import timed_node


def route_after_template_resolution(state: AdvisorState) -> str:
    """
    Skip Oracle inspection and DSL compilation when template resolution fails.

    The pipeline still continues to SQL generation and final response so the
    user receives a blocked advisory with warnings/errors instead of partial
    output from downstream nodes.
    """
    template = state.get("template", {}) or {}

    if template.get("is_resolved"):
        return "oracle_inspection"

    return "sql_generation"


def build_advisor_graph():
    """
    Build the clean Activiti Mediation Template SQL Advisor graph.

    Safer flow:
        request_planner
          -> template_resolution
          -> [if resolved] oracle_inspection -> dsl_expression -> sql_generation
          -> [if unresolved] sql_generation (blocked)
          -> final_response

    Why Oracle before DSL?
    - Oracle MCP can fetch current working ATTRIBUTE_VALUE examples.
    - DSL compilation can pattern-match against real rows from the same TEMPLATE_ID.
    - This follows the project prompt guidance for ACT_MEDIATION_PARAMETER.
    """
    graph = StateGraph(AdvisorState)

    graph.add_node("request_planner", timed_node("request_planner", request_planner_node))
    graph.add_node(
        "template_resolution",
        timed_node("template_resolution", template_resolution_node),
    )
    graph.add_node(
        "oracle_inspection",
        timed_node("oracle_inspection", oracle_inspection_node),
    )
    graph.add_node("dsl_expression", timed_node("dsl_expression", dsl_expression_node))
    graph.add_node("sql_generation", timed_node("sql_generation", sql_generation_node))
    graph.add_node("final_response", timed_node("final_response", final_response_node))

    graph.add_edge(START, "request_planner")
    graph.add_edge("request_planner", "template_resolution")
    graph.add_conditional_edges(
        "template_resolution",
        route_after_template_resolution,
        {
            "oracle_inspection": "oracle_inspection",
            "sql_generation": "sql_generation",
        },
    )
    graph.add_edge("oracle_inspection", "dsl_expression")
    graph.add_edge("dsl_expression", "sql_generation")
    graph.add_edge("sql_generation", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile()


@lru_cache(maxsize=1)
def get_advisor_graph():
    return build_advisor_graph()


async def run_advisor(user_requirement: str) -> AdvisorState:
    graph = get_advisor_graph()
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
