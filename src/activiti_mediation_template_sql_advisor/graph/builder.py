import asyncio

from langgraph.graph import END, START, StateGraph

from activiti_mediation_template_sql_advisor.graph.nodes.final_response import (
    final_response_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.oracle_inspection import (
    oracle_inspection_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.planner import planner_node
from activiti_mediation_template_sql_advisor.graph.nodes.rag_retrieval import (
    rag_retrieval_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.sql_generation import (
    sql_generation_node,
)
from activiti_mediation_template_sql_advisor.graph.state import (
    AdvisorState,
    create_initial_state,
)


def build_advisor_graph():
    """
    Build and compile the Activiti Mediation Template SQL Advisor graph.

    Flow:
        planner
          -> rag_retrieval
          -> oracle_inspection
          -> sql_generation
          -> final_response
    """
    graph = StateGraph(AdvisorState)

    graph.add_node("planner", planner_node)
    graph.add_node("rag_retrieval", rag_retrieval_node)
    graph.add_node("oracle_inspection", oracle_inspection_node)
    graph.add_node("sql_generation", sql_generation_node)
    graph.add_node("final_response", final_response_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "rag_retrieval")
    graph.add_edge("rag_retrieval", "oracle_inspection")
    graph.add_edge("oracle_inspection", "sql_generation")
    graph.add_edge("sql_generation", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile()


async def run_advisor(user_requirement: str) -> AdvisorState:
    """
    Run the full advisor workflow for one user requirement.

    Because oracle_inspection_node uses async MCP calls, we run the graph with
    ainvoke instead of invoke.
    """
    graph = build_advisor_graph()

    initial_state = create_initial_state(user_requirement)

    final_state = await graph.ainvoke(initial_state)

    return final_state


async def main() -> None:
    """
    Manual end-to-end test.

    Run with:
        uv run python -m activiti_mediation_template_sql_advisor.graph.builder
    """
    requirement = "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"

    final_state = await run_advisor(requirement)

    print(final_state["final_answer"])


if __name__ == "__main__":
    asyncio.run(main())