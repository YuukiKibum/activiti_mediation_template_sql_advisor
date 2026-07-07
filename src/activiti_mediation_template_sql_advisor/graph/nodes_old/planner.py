import os
from dotenv import load_dotenv
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

import re

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
You are the planning node for the Activiti Mediation Template SQL Advisor.

Your job is to read the user's natural-language requirement and extract a structured plan.
You do not generate SQL.
You do not validate Oracle data.
You do not compile Activiti expressions fully.
You only identify the operation, template clue, attribute names, raw values, and a useful RAG query.

The system supports these operation types:

1. rename_attribute
   The user wants to rename an existing ATTRIBUTE_NAME.
   Example:
   "rename poAttributes to poAttributeList"

2. append_attribute_value
   The user wants to append a key-value fragment inside an existing ATTRIBUTE_VALUE.
   Example:
   "add ccat_sample_value as Sample inside existing poAttributes"

3. update_attribute_value
   The user wants to replace the full ATTRIBUTE_VALUE for an existing ATTRIBUTE_NAME.
   Example:
   "set AddToBillFlag value to addToBill false means false true means true"

4. add_attribute
   The user wants to insert a new ATTRIBUTE_NAME row into an existing TEMPLATE_ID.
   Example:
   "add new attribute AddToBillFlag with value if addToBill is false set false otherwise true"

5. unknown
   Use this only if the request cannot be understood.

Append-vs-add disambiguation:

If the user says:
- inside existing <ATTRIBUTE_NAME>
- inside <ATTRIBUTE_NAME>
- append to <ATTRIBUTE_NAME>
- add into <ATTRIBUTE_NAME>
- add under <ATTRIBUTE_NAME>
- add key/value inside <ATTRIBUTE_NAME>
- add <key> attribute inside existing <ATTRIBUTE_NAME>
- add <key> with value <value> inside existing <ATTRIBUTE_NAME>

Then operation_type must be append_attribute_value, not add_attribute.

For append_attribute_value:
- attribute_name is the existing ATTRIBUTE_NAME being modified.
- value_to_append is the new key/value phrase to append.
- Do not set attribute_name to the new key.
- Do not treat the new key as a new ACT_MEDIATION_PARAMETER row.

Example:
User:
"For Prepaid Base Plan ECM request, add ccat_sample_value attribute with value as sample dto variable inside existing poAttributes."

Correct output:
operation_type: append_attribute_value
attribute_name: poAttributes
value_to_append: ccat_sample_value from DTO variable sample

Wrong output:
operation_type: add_attribute
attribute_name: ccat_sample_value
Extraction rules:

- template_id:
  Extract a TEMPLATE_ID only if the user explicitly gives a real-looking template id such as MT_ECM_PRE_BASEPLAN.
  If the user gives a business phrase like "Prepaid Base Plan ECM request", leave template_id empty.
  The template_resolution_node will resolve the business phrase using the template registry.

- attribute_name:
  For rename_attribute, this is the old/current ATTRIBUTE_NAME.
  For append_attribute_value, this is the existing ATTRIBUTE_NAME that will be appended into.
  For update_attribute_value, this is the existing ATTRIBUTE_NAME whose value will be replaced.
  For add_attribute, this is the new ATTRIBUTE_NAME to insert.

- new_attribute_name:
  Only used for rename_attribute.

- new_attribute_value:
  Used for add_attribute and update_attribute_value.
  Keep this as the raw user-friendly value or logic.
  Do not add VAL_, # mapping, $LONG_, $EVAL_, or other Activiti syntax here unless the user already wrote it explicitly.

- value_to_append:
  Used for append_attribute_value.
  Keep this as the raw user-friendly append phrase or raw fragment.
  Example user phrase:
  "ccat_sample_value as Sample"
  Do not convert it to ccat_sample_value=VAL_Sample here.
  The expression_compilation_node will do that using the Master RAG Guide.

rag_query generation rules:

The rag_query must be useful for retrieving the Master RAG Guide sections.
For expression-related requests, do not make the RAG query only the user's phrase.

Instead, include the likely expression intent and these retrieval anchors:
- User Phrase to Expression Pattern Dictionary
- Deterministic Validation Rules
- SQL Advisor Examples
- Java-Verified Token Dictionary

Examples:

User:
"For Prepaid Base Plan ECM request, add ccat_sample_value as Sample inside existing poAttributes."

Good rag_query:
"User Phrase to Expression Pattern Dictionary append key value fragment static literal value inside existing ATTRIBUTE_VALUE VAL_ Deterministic Validation Rules SQL Advisor Examples ccat_sample_value Sample poAttributes"

Bad rag_query:
"add ccat_sample_value as Sample"

User:
"For prepaid base plan rtf template, add a new attribute gundu with value 123"

Good rag_query:
"User Phrase to Expression Pattern Dictionary static value hardcoded value fixed value with value VAL_ add_attribute Deterministic Validation Rules SQL Advisor Examples gundu 123"

User:
"For Prepaid Base Plan RTF request, add AddToBillFlag. If addToBill is false set false, otherwise true."

Good rag_query:
"User Phrase to Expression Pattern Dictionary boolean mapping if field is false set value otherwise true mapping suffix # Deterministic Validation Rules SQL Advisor Examples addToBill AddToBillFlag"

Confidence:
Use confidence between 0 and 1.

Return only the structured output.
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

def _extract_append_inside_existing(user_requirement: str) -> dict[str, str] | None:
    """
    Detect requests like:

    "add ccat_sample_value attribute with value as sample dto variable
     inside existing poAttributes"

    This is not expression hardcoding.
    It only fixes operation routing:
    inside existing <ATTRIBUTE_NAME> => append_attribute_value.
    """
    text = (user_requirement or "").strip()

    pattern = re.compile(
        r"""
        add\s+
        (?P<key>[A-Za-z_][A-Za-z0-9_]*)
        (?:\s+attribute)?
        (?:
            \s+
            (?:with\s+)?value
            \s+(?:as\s+)?
            (?P<raw_value>.*?)
        )?
        \s+
        inside
        \s+
        (?:existing\s+)?
        (?P<target_attribute>[A-Za-z_][A-Za-z0-9_]*)
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)

    if not match:
        return None

    key = match.group("key").strip()
    raw_value = (match.group("raw_value") or "").strip()
    target_attribute = match.group("target_attribute").strip()

    if not key or not target_attribute:
        return None

    value_to_append = key

    if raw_value:
        raw_value_lower = raw_value.lower()

        if "dto" in raw_value_lower or "json" in raw_value_lower or "payload" in raw_value_lower:
            cleaned_value = (
                raw_value.replace("DTO", "")
                .replace("dto", "")
                .replace("JSON", "")
                .replace("json", "")
                .replace("variable", "")
                .replace("varaible", "")
                .replace("varibale", "")
                .replace("field", "")
                .strip()
            )

            if cleaned_value:
                value_to_append = f"{key} from DTO variable {cleaned_value}"
            else:
                value_to_append = f"{key} from DTO variable"
        else:
            value_to_append = f"{key} as {raw_value}"

    return {
        "operation_type": "append_attribute_value",
        "attribute_name": target_attribute,
        "value_to_append": value_to_append,
        "new_attribute_value": "",
        "new_attribute_name": "",
    }


def _apply_planner_guardrails(
    user_requirement: str,
    planner_updates: dict,
) -> dict:
    """
    Apply deterministic routing corrections after LLM planning.

    This keeps SQL/expression generation safer.
    """
    append_inside_existing = _extract_append_inside_existing(user_requirement)

    if append_inside_existing:
        planner_updates.update(append_inside_existing)

        warnings = list(planner_updates.get("warnings", []) or [])
        warnings.append(
            "Planner guardrail changed operation_type to append_attribute_value "
            "because the user requested adding a key/value inside an existing ATTRIBUTE_NAME."
        )
        planner_updates["warnings"] = warnings

    return planner_updates

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

    updates = {
    "operation_type": decision.operation_type,
    "template_id": decision.template_id,
    "attribute_name": decision.attribute_name,
    "new_attribute_name": decision.new_attribute_name,
    "new_attribute_value": decision.new_attribute_value,
    "value_to_append": decision.value_to_append,
    "rag_query": decision.rag_query,
    "warnings": warnings,
}

    updates = _apply_planner_guardrails(
        user_requirement=state.get("user_requirement", ""),
        planner_updates=updates,
    )

    return updates


if __name__ == "__main__":
    test_state: AdvisorState = {
        "user_requirement": (
            "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"
        ),
        "warnings": [],
    }

    result = planner_node(test_state)

    print(result)