from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.rag.retriever import retrieve_context


def rag_retrieval_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: retrieve relevant Activiti documentation from Pinecone.

    Reads:
        rag_query
        user_requirement

    Writes:
        rag_context
        warnings
    """
    rag_query = state.get("rag_query", "").strip()
    user_requirement = state.get("user_requirement", "").strip()

    query = rag_query or user_requirement

    warnings = list(state.get("warnings", []))

    if not query:
        warnings.append("RAG retrieval skipped because no query was available.")
        return {
            "rag_context": [],
            "warnings": warnings,
        }

    context_items = retrieve_context(
        query=query,
        top_k=5,
        include_scores=True,
    )

    if not context_items:
        warnings.append("No relevant RAG documentation was retrieved.")

    return {
        "rag_context": context_items,
        "warnings": warnings,
    }


if __name__ == "__main__":
    test_state: AdvisorState = {
        "user_requirement": (
            "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"
        ),
        "rag_query": (
            "ACT_MEDIATION_PARAMETER ATTRIBUTE_NAME rename SQL update"
        ),
        "warnings": [],
    }

    result = rag_retrieval_node(test_state)

    print("Retrieved chunks:", len(result["rag_context"]))

    for item in result["rag_context"]:
        print("-" * 80)
        print("Source:", item.get("source"))
        print("Score:", item.get("score"))
        print("Text:", item.get("content", "")[:500])