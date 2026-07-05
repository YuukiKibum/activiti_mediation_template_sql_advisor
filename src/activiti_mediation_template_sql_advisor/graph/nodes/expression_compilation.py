import os
from dotenv import load_dotenv
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState

load_dotenv()


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")


class ExpressionCompilationDecision(BaseModel):
    """
    Structured output from the expression compiler.

    This node converts business/plain-English values into Activiti mediation
    ATTRIBUTE_VALUE expressions.
    """

    did_compile: bool = Field(
        description=(
            "True if the compiler produced or confirmed an Activiti mediation expression."
        )
    )

    compiled_new_attribute_value: str = Field(
        default="",
        description=(
            "Compiled ATTRIBUTE_VALUE for add_attribute or update_attribute_value. "
            "Example: plain value 123 becomes VAL_123."
        ),
    )

    compiled_value_to_append: str = Field(
        default="",
        description=(
            "Compiled fragment for append_attribute_value. "
            "Example: add ccat_sample_value as Sample becomes ccat_sample_value=VAL_Sample;"
        ),
    )

    confidence: float = Field(
        default=0.0,
        description="Compiler confidence from 0.0 to 1.0.",
    )

    reasoning: str = Field(
        default="",
        description="Brief reason explaining the expression conversion.",
    )

    warnings: list[str] = Field(
        default_factory=list,
        description="Warnings from expression compilation.",
    )


EXPRESSION_COMPILER_SYSTEM_PROMPT = """
You are the expression compiler for an Activiti Mediation Template SQL Advisor.

Your job:
Convert user-friendly values or business rules into valid ACT_MEDIATION_PARAMETER.ATTRIBUTE_VALUE expressions.

You are NOT generating SQL.
You are ONLY compiling ATTRIBUTE_VALUE strings or append fragments.

You will receive:
1. User requirement
2. Operation type
3. Attribute name
4. Current extracted value from the planner
5. RAG context from Activiti expression documentation

Supported operation types:
- add_attribute
- update_attribute_value
- append_attribute_value
- rename_attribute

For rename_attribute:
- Do not compile anything.
- Return did_compile = false.

Core Activiti expression rules:

1. Static values use VAL_
   If the user gives a plain static literal, convert it to VAL_<literal>.

   Examples:
   - "with value 123" -> VAL_123
   - "static value 123" -> VAL_123
   - "static value Sample" -> VAL_Sample
   - "change POType from Add-on to Base Plan" -> VAL_Base Plan
   - "with value Base Plan" -> VAL_Base Plan

2. Do not double-prefix VAL_
   If the value already starts with VAL_, keep it unchanged.

   Examples:
   - VAL_123 -> VAL_123
   - VAL_Sample -> VAL_Sample

3. Do not convert existing expressions
   If the value already contains expression syntax, keep it unchanged unless user clearly asks for a different expression.

   Expression indicators:
   - starts with $
   - contains #
   - contains |
   - contains =
   - contains ;
   - starts with VAL_

   Examples:
   - addToBill#false|false,true|true -> keep as is
   - $LONG_allowances.otherAllowances.thirdPartySubscription.enabled#true|1,false|0 -> keep as is
   - ccat_sample_value=VAL_Sample; -> keep as is

4. Dictionary mapping uses # syntax
   For natural-language mappings:
   - "if addToBill is false set false, otherwise true"
     -> addToBill#false|false,true|true

   Pattern:
   <sourceField>#<sourceValue1>|<targetValue1>,<sourceValue2>|<targetValue2>

5. Long numeric mapping uses $LONG_
   If user explicitly says "as a long value", use $LONG_ prefix.

   Example:
   "third party subscription enabled true maps to 1 and false maps to 0 as a long value"
   -> $LONG_allowances.otherAllowances.thirdPartySubscription.enabled#true|1,false|0

6. Append fragments
   For append_attribute_value, compile a complete key-value fragment ending with semicolon.

   Example:
   "add ccat_sample_value as Sample inside poAttributes"
   -> ccat_sample_value=VAL_Sample;

   Example:
   "append ccat_sample_value=VAL_Sample; to poAttributes"
   -> ccat_sample_value=VAL_Sample;

7. Attribute names are not expressions
   Do not add "/" to attribute names.
   Do not modify ATTRIBUTE_NAME.
   Only compile ATTRIBUTE_VALUE or append fragments.

Output rules:
- For add_attribute and update_attribute_value:
  put result in compiled_new_attribute_value.
- For append_attribute_value:
  put result in compiled_value_to_append.
- If no compilation is needed because the value is already valid, return the same value.
- If you are unsure, keep the planner value and add a warning.
- Never invent TEMPLATE_ID.
- Never generate SQL.
"""


def _get_expression_compiler_llm():
    """
    Create a structured-output LLM for expression compilation.
    """
    model = init_chat_model(
        OPENAI_MODEL,
        model_provider="openai",
    )

    return model.with_structured_output(ExpressionCompilationDecision)


def _format_rag_context_for_compiler(rag_context: list[dict[str, Any]]) -> str:
    """
    Convert retrieved RAG chunks into compact prompt context.
    """
    if not rag_context:
        return "No RAG context was retrieved."

    formatted_chunks: list[str] = []

    for index, item in enumerate(rag_context, start=1):
        source = item.get("source", "Unknown")
        content = str(item.get("content") or "")
        score = item.get("score")

        formatted_chunks.append(
            "\n".join(
                [
                    f"[Chunk {index}]",
                    f"Source: {source}",
                    f"Score: {score}",
                    "Content:",
                    content[:1800],
                ]
            )
        )

    return "\n\n".join(formatted_chunks)


def expression_compilation_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: compile plain values/business rules into Activiti expressions.

    Reads:
        user_requirement
        operation_type
        attribute_name
        new_attribute_value
        value_to_append
        rag_context

    Writes:
        new_attribute_value
        value_to_append
        expression_compilation_did_compile
        expression_compilation_confidence
        expression_compilation_reason
        expression_compilation_warnings
        warnings
    """
    operation_type = state.get("operation_type", "unknown")

    warnings = list(state.get("warnings", []))

    if operation_type == "rename_attribute":
        return {
            "expression_compilation_did_compile": False,
            "expression_compilation_confidence": 1.0,
            "expression_compilation_reason": (
                "No ATTRIBUTE_VALUE compilation required for rename_attribute."
            ),
            "expression_compilation_warnings": [],
            "warnings": warnings,
        }

    if operation_type not in {
        "add_attribute",
        "update_attribute_value",
        "append_attribute_value",
    }:
        warnings.append(
            f"Expression compilation skipped for unsupported operation_type: {operation_type}"
        )

        return {
            "expression_compilation_did_compile": False,
            "expression_compilation_confidence": 0.0,
            "expression_compilation_reason": "Operation type does not require compilation.",
            "expression_compilation_warnings": [],
            "warnings": warnings,
        }

    compiler_llm = _get_expression_compiler_llm()

    rag_context_text = _format_rag_context_for_compiler(
        state.get("rag_context", [])
    )

    user_payload = f"""
User requirement:
{state.get("user_requirement", "")}

Operation type:
{operation_type}

Attribute name:
{state.get("attribute_name", "")}

Planner new_attribute_value:
{state.get("new_attribute_value", "")}

Planner value_to_append:
{state.get("value_to_append", "")}

RAG context from Activiti expression documentation:
{rag_context_text}
"""

    decision = compiler_llm.invoke(
        [
            {
                "role": "system",
                "content": EXPRESSION_COMPILER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_payload,
            },
        ]
    )

    expression_warnings = list(decision.warnings or [])

    for warning in expression_warnings:
        warnings.append(f"Expression compiler: {warning}")

    updates: dict[str, Any] = {
        "expression_compilation_did_compile": decision.did_compile,
        "expression_compilation_confidence": decision.confidence,
        "expression_compilation_reason": decision.reasoning,
        "expression_compilation_warnings": expression_warnings,
        "warnings": warnings,
    }

    if operation_type in {"add_attribute", "update_attribute_value"}:
        compiled_value = decision.compiled_new_attribute_value.strip()

        if compiled_value:
            updates["new_attribute_value"] = compiled_value
        else:
            warnings.append(
                "Expression compiler did not return compiled_new_attribute_value."
            )

    if operation_type == "append_attribute_value":
        compiled_append = decision.compiled_value_to_append.strip()

        if compiled_append:
            updates["value_to_append"] = compiled_append
        else:
            warnings.append(
                "Expression compiler did not return compiled_value_to_append."
            )

    if decision.confidence < 0.6:
        warnings.append(
            f"Expression compiler confidence is low: {decision.confidence}"
        )

    return updates


if __name__ == "__main__":
    examples: list[AdvisorState] = [
        {
            "user_requirement": (
                "For prepaid base plan rtf template, add a new attribute "
                "gundu with value 123"
            ),
            "operation_type": "add_attribute",
            "attribute_name": "gundu",
            "new_attribute_value": "123",
            "value_to_append": "",
            "rag_context": [],
            "warnings": [],
        },
        {
            "user_requirement": (
                "For Prepaid STK Notify Store request, change POType from "
                "Add-on to Base Plan."
            ),
            "operation_type": "update_attribute_value",
            "attribute_name": "POType",
            "new_attribute_value": "Base Plan",
            "value_to_append": "",
            "rag_context": [],
            "warnings": [],
        },
        {
            "user_requirement": (
                "For Prepaid Base Plan ECM request, add ccat_sample_value "
                "as Sample inside poAttributes."
            ),
            "operation_type": "append_attribute_value",
            "attribute_name": "poAttributes",
            "new_attribute_value": "",
            "value_to_append": "ccat_sample_value Sample",
            "rag_context": [],
            "warnings": [],
        },
        {
            "user_requirement": (
                "For Prepaid Base Plan RTF request, add a new attribute "
                "AddToBillFlagCopy. If addToBill is false set false, otherwise true."
            ),
            "operation_type": "add_attribute",
            "attribute_name": "AddToBillFlagCopy",
            "new_attribute_value": "addToBill false false true true",
            "value_to_append": "",
            "rag_context": [],
            "warnings": [],
        },
    ]

    for example in examples:
        result = expression_compilation_node(example)

        print("=" * 100)
        print("Requirement:", example["user_requirement"])
        print("Result:", result)