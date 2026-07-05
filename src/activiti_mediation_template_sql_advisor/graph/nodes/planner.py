import os
from dotenv import load_dotenv
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState, OperationType

load_dotenv()


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")


class PlannerDecision(BaseModel):
    """
    Structured output from the planner LLM.

    This object extracts the important details from the user's natural-language
    requirement.
    """

    operation_type: OperationType = Field(
        description=(
            "The type of configuration change requested by the user. "
            "Use rename_attribute, append_attribute_value, update_attribute_value, "
            "add_attribute, or unknown."
        )
    )

    template_id: str = Field(
        default="",
        description="The ACT_MEDIATION_TEMPLATE.TEMPLATE_ID mentioned by the user.",
    )

    attribute_name: str = Field(
        default="",
        description=(
            "The existing ACT_MEDIATION_PARAMETER.ATTRIBUTE_NAME involved in the change."
        ),
    )

    new_attribute_name: str = Field(
        default="",
        description=(
            "The new ATTRIBUTE_NAME, used mainly for rename_attribute operations."
        ),
    )

    new_attribute_value: str = Field(
        default="",
        description=(
            "The full new ATTRIBUTE_VALUE, used for update_attribute_value or add_attribute."
        ),
    )

    value_to_append: str = Field(
        default="",
        description=(
            "The value fragment to append to an existing ATTRIBUTE_VALUE, "
            "used for append_attribute_value."
        ),
    )

    rag_query: str = Field(
        default="",
        description=(
            "A concise search query for retrieving relevant Activiti mediation "
            "documentation from RAG."
        ),
    )

    confidence: float = Field(
        default=0.0,
        description="Planner confidence from 0.0 to 1.0.",
    )

    reasoning: str = Field(
        default="",
        description="Brief explanation of why this operation type was selected.",
    )


PLANNER_SYSTEM_PROMPT = """
You are the planner for an Activiti Mediation Template SQL Advisor.

Your job is to extract structured fields from the user's requirement.

The system works with two Oracle tables:
1. ACT_MEDIATION_TEMPLATE
   - TEMPLATE_ID
   - TEMPLATE_DESCRIPTION

2. ACT_MEDIATION_PARAMETER
   - PARAM_ID
   - TEMPLATE_ID
   - ATTRIBUTE_NAME
   - ATTRIBUTE_VALUE

Supported operation types:

1. rename_attribute
   The user wants to rename an existing ATTRIBUTE_NAME.
   Example:
   "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"

2. append_attribute_value
   The user wants to append a fragment to an existing ATTRIBUTE_VALUE.
   Example:
   "Append ccat_sample_value=VAL_Sample; to poAttributes for MT_ECM_PRE_BASEPLAN"

3. update_attribute_value
   The user wants to replace the full ATTRIBUTE_VALUE of an existing attribute.
   Example:
   "Update AddToBillFlag value to addToBill#false|false,true|true for MT_RTF_TC_PREP_PLAN"

4. add_attribute
   The user wants to insert a new ATTRIBUTE_NAME and ATTRIBUTE_VALUE for an existing TEMPLATE_ID.
   Example:
   "Add attribute AddToBillFlag with value addToBill#false|false,true|true for MT_RTF_TC_PREP_PLAN"

5. unknown
   Use this only when the requirement is too unclear.

Rules:
- Extract TEMPLATE_ID exactly if present, usually values like MT_ECM_PRE_BASEPLAN.
- For rename_attribute:
  - attribute_name = old name
  - new_attribute_name = new name
- For append_attribute_value:
  - attribute_name = existing attribute
  - value_to_append = fragment to append
- For update_attribute_value:
  - attribute_name = existing attribute
  - new_attribute_value = replacement value
- For add_attribute:
  - attribute_name = new attribute name
  - new_attribute_value = new attribute value
- Always create a useful rag_query for documentation retrieval.
- Do not generate SQL here.
- Do not inspect Oracle here.
"""


def _get_planner_llm():
    """
    Create a structured-output LLM for planning.

    We keep this in a function so importing planner.py does not immediately
    create the model.
    """
    model = init_chat_model(
        OPENAI_MODEL,
        model_provider="openai",
    )

    return model.with_structured_output(PlannerDecision)


def _fallback_rag_query(requirement: str, decision: PlannerDecision) -> str:
    """
    Create a useful RAG query if the LLM did not provide one.
    """
    if decision.rag_query.strip():
        return decision.rag_query.strip()

    if decision.operation_type == "rename_attribute":
        return "ACT_MEDIATION_PARAMETER ATTRIBUTE_NAME rename SQL update"

    if decision.operation_type == "append_attribute_value":
        return "ACT_MEDIATION_PARAMETER ATTRIBUTE_VALUE append expression syntax"

    if decision.operation_type == "update_attribute_value":
        return "ACT_MEDIATION_PARAMETER ATTRIBUTE_VALUE update expression syntax"

    if decision.operation_type == "add_attribute":
        return "ACT_MEDIATION_PARAMETER add new attribute ATTRIBUTE_VALUE expression syntax"

    return requirement


def planner_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: classify and extract the user's requirement.

    Reads:
        user_requirement

    Writes:
        operation_type
        template_id
        attribute_name
        new_attribute_name
        new_attribute_value
        value_to_append
        rag_query
        warnings
    """
    requirement = state.get("user_requirement", "").strip()

    if not requirement:
        return {
            "operation_type": "unknown",
            "warnings": ["User requirement is empty."],
        }

    planner_llm = _get_planner_llm()

    decision = planner_llm.invoke(
        [
            {
                "role": "system",
                "content": PLANNER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": requirement,
            },
        ]
    )

    rag_query = _fallback_rag_query(requirement, decision)

    warnings = list(state.get("warnings", []))

    if decision.operation_type == "unknown":
        warnings.append(
            "Planner could not confidently classify the requested operation."
        )

    if decision.confidence < 0.5:
        warnings.append(
            f"Planner confidence is low: {decision.confidence}"
        )

    return {
        "operation_type": decision.operation_type,
        "template_id": decision.template_id.strip(),
        "attribute_name": decision.attribute_name.strip(),
        "new_attribute_name": decision.new_attribute_name.strip(),
        "new_attribute_value": decision.new_attribute_value.strip(),
        "value_to_append": decision.value_to_append.strip(),
        "rag_query": rag_query,
        "warnings": warnings,
    }


if __name__ == "__main__":
    test_state: AdvisorState = {
        "user_requirement": (
            "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"
        ),
        "warnings": [],
    }

    result = planner_node(test_state)

    print(result)