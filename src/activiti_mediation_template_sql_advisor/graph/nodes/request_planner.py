from __future__ import annotations

import os
from dotenv import load_dotenv

from typing import Any, Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from activiti_mediation_template_sql_advisor.graph.state import (
    AdvisorState,
    OperationType,
    append_error,
)

load_dotenv()

REQUEST_PLANNER_SYSTEM_PROMPT = """
You are the request planner for an Activiti Mediation Template SQL Advisor.

Your job is to extract only the user's intent.

Do NOT generate:
- DSL expressions
- SQL
- TO_CLOB
- Oracle queries
- RAG queries

Return only structured intent.

Supported operation types:
- rename_attribute
- add_attribute
- update_attribute_value
- append_attribute_value
- delete_attribute
- unknown

Important operation distinction:

append_attribute_value:
Use this when the user wants to add a key/value pair inside an existing ATTRIBUTE_VALUE.
Common phrases:
- inside existing <attribute>
- inside <attribute>
- append to <attribute>
- add into <attribute>
- add under <attribute>
- add key/value inside <attribute>
- add <key> with value <value> inside existing <attribute>

For append_attribute_value:
- container_attribute_name = the existing container ATTRIBUTE_NAME, e.g. poAttributes
- append_key = the key being appended inside that container, e.g. CustomerType
- rhs_request = human-language value logic only, e.g. "if subscriberType is PREPAID show 1 else 0"

add_attribute:
Use this when the user wants a new row/attribute in ACT_MEDIATION_PARAMETER.
Common phrases:
- add a new attribute <name>
- create new attribute <name>
- insert attribute <name>

For add_attribute:
- attribute_name = the new ATTRIBUTE_NAME
- rhs_request = human-language value logic only

rename_attribute:
Use this when the user wants to rename an existing ATTRIBUTE_NAME.
- attribute_name = old name
- new_attribute_name = new name

update_attribute_value:
Use this when the user wants to replace the full ATTRIBUTE_VALUE of an existing ATTRIBUTE_NAME.
- attribute_name = existing ATTRIBUTE_NAME
- rhs_request = new full value logic

delete_attribute:
Use this when the user wants to remove an ATTRIBUTE_NAME.

Template extraction:
Extract the natural template phrase from the user.
Examples:
- "Prepaid Base Plan ECM request"
- "Prepaid Base Plan RTF request"

External system:
Extract if clearly present, e.g. ECM, RTF, COMS, BSCS.

Do not invent missing values.
If unsure, leave field empty and lower confidence.
"""


class RequestPlanDecision(BaseModel):
    operation_type: OperationType = Field(default="unknown")

    template_phrase: str = Field(default="")
    external_system: str = Field(default="")

    attribute_name: str = Field(default="")
    new_attribute_name: str = Field(default="")

    container_attribute_name: str = Field(default="")
    append_key: str = Field(default="")

    rhs_request: str = Field(default="")

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = Field(default="")


def _get_planner_llm():
    llm = init_chat_model(
        os.getenv("OPENAI_MODEL", "gpt-4.1-nano"),
        model_provider="openai",
        temperature=0,
    )
    return llm.with_structured_output(RequestPlanDecision)


def _normalize_plan(decision: RequestPlanDecision) -> dict[str, Any]:
    """
    Small deterministic cleanup only.

    No DSL syntax is generated here.
    """
    plan = decision.model_dump()

    operation_type = plan.get("operation_type", "unknown")

    if operation_type == "append_attribute_value":
        # For append, attribute_name should point to the container attribute.
        if not plan.get("attribute_name") and plan.get("container_attribute_name"):
            plan["attribute_name"] = plan["container_attribute_name"]

        if not plan.get("container_attribute_name") and plan.get("attribute_name"):
            plan["container_attribute_name"] = plan["attribute_name"]

        # New attribute name is not applicable for append.
        plan["new_attribute_name"] = ""

    elif operation_type == "add_attribute":
        # For add, attribute_name and new_attribute_name are the same target row.
        if not plan.get("new_attribute_name") and plan.get("attribute_name"):
            plan["new_attribute_name"] = plan["attribute_name"]

        if not plan.get("attribute_name") and plan.get("new_attribute_name"):
            plan["attribute_name"] = plan["new_attribute_name"]

        plan["container_attribute_name"] = ""
        plan["append_key"] = ""

    elif operation_type == "rename_attribute":
        plan["container_attribute_name"] = ""
        plan["append_key"] = ""
        plan["rhs_request"] = ""

    elif operation_type == "delete_attribute":
        plan["container_attribute_name"] = ""
        plan["append_key"] = ""
        plan["rhs_request"] = ""

    return plan


def request_planner_node(state: AdvisorState) -> dict[str, Any]:
    user_requirement = state.get("user_requirement", "")

    try:
        llm = _get_planner_llm()

        decision = llm.invoke(
            [
                {"role": "system", "content": REQUEST_PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Extract the request plan from this requirement:\n\n"
                        f"{user_requirement}"
                    ),
                },
            ]
        )

        plan = _normalize_plan(decision)

        warnings = list(state.get("warnings", []) or [])

        if plan.get("operation_type") == "unknown":
            warnings.append("Planner could not confidently determine operation_type.")

        if not plan.get("template_phrase"):
            warnings.append("Planner could not determine template_phrase.")

        return {
            "plan": plan,
            "warnings": warnings,
        }

    except Exception as exc:
        error = f"request_planner_node failed: {exc}"

        return {
            "plan": {
                "operation_type": "unknown",
                "template_phrase": "",
                "external_system": "",
                "attribute_name": "",
                "new_attribute_name": "",
                "container_attribute_name": "",
                "append_key": "",
                "rhs_request": "",
                "confidence": 0.0,
                "reason": error,
            },
            "errors": append_error(state, error),
        }