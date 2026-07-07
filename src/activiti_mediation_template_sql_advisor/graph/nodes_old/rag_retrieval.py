from __future__ import annotations

from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.rag.retriever import retrieve_context

MASTER_GUIDE_RETRIEVAL_ANCHORS = """
Master RAG Guide sections to retrieve:
- User Phrase to Expression Pattern Dictionary
- Value Source Classification Rules
- Static Literal Rules
- DTO JSON Path Extraction Rules
- Session Variable Rules
- Conditional Mapping Rules
- Typed and Transformed Value Rules
- Deterministic Validation Rules
- SQL Advisor Examples
- Java-Verified Token Dictionary
- Business objective and ACT_MEDIATION_TEMPLATE / ACT_MEDIATION_PARAMETER table rules
"""


def _build_expression_intent_terms(state: AdvisorState) -> str:
    """
    Add intent-specific search terms so Pinecone retrieves the best section
    from the consolidated Master RAG Guide.
    """
    operation_type = state.get("operation_type", "unknown")
    user_requirement = state.get("user_requirement", "")

    raw_parts = [
        user_requirement,
        state.get("attribute_name", ""),
        state.get("new_attribute_name", ""),
        state.get("new_attribute_value", ""),
        state.get("value_to_append", ""),
    ]

    base = " ".join(str(part) for part in raw_parts if part)

    value_source_terms = """
Value source classification:
static literal
hardcoded value
fixed value
literal value
with value
VAL_

DTO variable
DTO field
JSON variable
JSON field
Bespoke JSON
payload field
source field
direct field extraction
from DTO field
from JSON path
from payload
map from field
populate from field
take from field
read from field
do not use VAL_ for DTO JSON path

session variable
workflow variable
runtime variable

explicit Activiti expression
conditional mapping
mapping suffix #
boolean mapping
type conversion
transformation directive
"""

    if operation_type == "append_attribute_value":
        return f"""
{base}

Expression intent:
append key value fragment
append expression RHS
add key as static value
add key from DTO field
add key from JSON path
key=value;
append fragment validation
static literal right hand side
DTO JSON path right hand side

{value_source_terms}
"""

    if operation_type in {"add_attribute", "update_attribute_value"}:
        return f"""
{base}

Expression intent:
compile full ATTRIBUTE_VALUE
static value
DTO JSON field value
session variable value
explicit expression value
conditional mapping value
typed or transformed value
validation rules

{value_source_terms}
"""

    if operation_type == "rename_attribute":
        return f"""
{base}

Advisor intent:
rename existing ATTRIBUTE_NAME
update attribute name
ACT_MEDIATION_PARAMETER
pre-check current attribute
rollback SQL
"""

    return f"""
{base}

Advisor intent:
understand Activiti mediation template change request
expression pattern dictionary
value source classification
validation rules
SQL advisor examples

{value_source_terms}
"""


def build_master_rag_query(state: AdvisorState) -> str:
    """
    Build the final RAG query for the consolidated master document.

    The planner already creates rag_query, but this function enriches it
    with stable section names from the Master RAG Guide so retrieval is better.
    """
    planner_query = state.get("rag_query", "") or ""
    expression_terms = _build_expression_intent_terms(state)

    return f"""
{planner_query}

{expression_terms}

{MASTER_GUIDE_RETRIEVAL_ANCHORS}
""".strip()


def rag_retrieval_node(state: AdvisorState) -> dict[str, Any]:
    """
    Retrieve context from the consolidated Activiti Mediation Master RAG Guide.
    """
    query = build_master_rag_query(state)

    context = retrieve_context(
        query=query,
        top_k=6,
        include_scores=True,
    )

    return {
        "rag_query": query,
        "rag_context": context,
    }


if __name__ == "__main__":
    sample_state: AdvisorState = {
        "user_requirement": (
            "For Prepaid Base Plan ECM request, add ccat_sample_value "
            "as Sample inside existing poAttributes."
        ),
        "operation_type": "append_attribute_value",
        "template_id": "MT_ECM_PRE_BASEPLAN",
        "attribute_name": "poAttributes",
        "new_attribute_name": "",
        "new_attribute_value": "",
        "value_to_append": "ccat_sample_value as Sample",
        "rag_query": "add ccat_sample_value as Sample",
    }

    result = rag_retrieval_node(sample_state)
    print("RAG query:")
    print(result["rag_query"])
    print("\nRetrieved chunks:")
    for item in result["rag_context"]:
        print(item)