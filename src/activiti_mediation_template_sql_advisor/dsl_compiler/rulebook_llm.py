from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    ALLOWED_EVALUATORS,
    ALLOWED_OPERATION_KINDS,
    APPEND_VALUE_OPERATION_KINDS,
    CONDITIONAL_SIGNALS,
    SOURCE_FIELD_SIGNALS,
    UNIT_CONVERSION_SIGNALS,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import (
    format_oracle_samples_for_dsl,
    structured_output_contract,
    text_has_any_signal,
)
from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState

load_dotenv()


def build_dsl_query(
    state: AdvisorState,
    *,
    correction_note: str = "",
) -> str:
    plan = state.get("plan", {}) or {}
    template = state.get("template", {}) or {}
    oracle = state.get("oracle", {}) or {}

    user_requirement = str(
        state.get("user_requirement", "")
        or state.get("requirement", "")
        or ""
    )

    operation_type = str(plan.get("operation_type", "") or "")
    attribute_name = str(plan.get("attribute_name", "") or "")
    new_attribute_name = str(plan.get("new_attribute_name", "") or "")
    container_attribute_name = str(plan.get("container_attribute_name", "") or "")
    append_key = str(plan.get("append_key", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")

    try:
        rulebook_summary = get_rulebook_prompt_summary()
    except Exception as exc:
        rulebook_summary = f"ATTRIBUTE_VALUE rulebook could not be loaded: {exc}"

    oracle_samples_text = format_oracle_samples_for_dsl(state)

    parts = [
        "You are compiling ONLY the RHS ATTRIBUTE_VALUE expression for ACT_MEDIATION_PARAMETER.",
        "Use the merged ATTRIBUTE_VALUE rulebook as the source of truth.",
        "Do not use evaluator A/B/C. Do not mention old DSL KB records.",
        "Return evaluator='RULEBOOK'.",
        "",
        structured_output_contract(),
        "",
        "ATTRIBUTE_VALUE rulebook summary:",
        rulebook_summary,
        "",
        "Current request context:",
        f"Full user requirement: {user_requirement}",
        f"Planner operation_type: {operation_type}",
        f"Template ID: {template.get('template_id', '')}",
        f"Template external system: {template.get('external_system', '')}",
        f"Attribute name: {attribute_name}",
        f"New attribute name: {new_attribute_name}",
        f"RHS request from planner: {rhs_request}",
    ]

    if operation_type == "append_attribute_value":
        current_attribute_value = str(
            oracle.get("current_attribute_value", "") or ""
        )

        parts.extend(
            [
                "",
                "Append/composite attribute context:",
                "The SQL row is the existing container attribute.",
                "Return operation_kind='append_subkey'.",
                "Return expression as ONLY the value side for the new sub-key.",
                "Do not include append_key= in expression.",
                "Do not include trailing semicolon in expression.",
                f"Existing container attribute: {container_attribute_name}",
                f"Append key: {append_key}",
                f"Current full ATTRIBUTE_VALUE preview: {current_attribute_value[:1500]}",
            ]
        )

    elif operation_type in {"add_attribute", "update_attribute_value"}:
        parts.extend(
            [
                "",
                "Add/update ATTRIBUTE_VALUE context:",
                "Return the final concrete RHS expression.",
                "Do not return placeholders such as VAL_<literal>.",
                "Do not return SQL.",
            ]
        )

    else:
        parts.extend(
            [
                "",
                "This operation does not require DSL RHS compilation.",
            ]
        )

    if oracle_samples_text:
        parts.extend(["", oracle_samples_text])

    if correction_note:
        parts.extend(
            [
                "",
                "CORRECTION FROM A PREVIOUS ATTEMPT:",
                correction_note,
            ]
        )

    return "\n".join(parts)


def call_rulebook_llm(dsl_query: str) -> str:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The openai package is required for rulebook fallback generation. Install it with: uv add openai"
        ) from exc

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict rulebook-only compiler for "
                    "ACT_MEDIATION_PARAMETER.ATTRIBUTE_VALUE. Return JSON only."
                ),
            },
            {"role": "user", "content": dsl_query},
        ],
    )

    return response.choices[0].message.content or ""


def strip_json_fences(raw_answer: str) -> str:
    text = (raw_answer or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


def parse_structured_answer(raw_answer: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_answer, dict):
        data = raw_answer
    else:
        text = strip_json_fences(raw_answer)

        if not text:
            raise ValueError("Rulebook compiler returned an empty response; expected JSON object.")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Rulebook compiler did not return valid JSON: {exc.msg}. Raw answer: {raw_answer}"
            ) from exc

    if not isinstance(data, dict):
        raise ValueError("Rulebook compiler JSON must be an object.")

    required_keys = {
        "evaluator",
        "selected_record_ids",
        "operation_kind",
        "is_supported",
        "expression",
        "reason",
        "confidence",
    }

    missing_keys = sorted(required_keys - set(data.keys()))

    if missing_keys:
        raise ValueError(
            "Rulebook compiler JSON is missing required keys: " + ", ".join(missing_keys)
        )

    evaluator = data["evaluator"]

    if not isinstance(evaluator, str) or evaluator not in ALLOWED_EVALUATORS:
        raise ValueError(
            f"Rulebook compiler JSON has invalid evaluator={evaluator!r}; expected 'RULEBOOK'."
        )

    selected_record_ids = data["selected_record_ids"]

    if not isinstance(selected_record_ids, list) or not all(
        isinstance(item, str) for item in selected_record_ids
    ):
        raise ValueError("Rulebook compiler JSON selected_record_ids must be a list of strings.")

    operation_kind = data["operation_kind"]

    if not isinstance(operation_kind, str) or operation_kind not in ALLOWED_OPERATION_KINDS:
        raise ValueError(
            f"Rulebook compiler JSON has invalid operation_kind={operation_kind!r}; "
            f"expected one of {sorted(ALLOWED_OPERATION_KINDS)}."
        )

    is_supported = data["is_supported"]

    if not isinstance(is_supported, bool):
        raise ValueError("Rulebook compiler JSON is_supported must be a boolean.")

    expression = data["expression"]

    if not isinstance(expression, str):
        raise ValueError("Rulebook compiler JSON expression must be a string.")

    reason = data["reason"]

    if not isinstance(reason, str):
        raise ValueError("Rulebook compiler JSON reason must be a string.")

    confidence = data["confidence"]

    if not isinstance(confidence, (int, float)):
        raise ValueError("Rulebook compiler JSON confidence must be a number.")

    confidence_float = float(confidence)

    if confidence_float < 0.0 or confidence_float > 1.0:
        raise ValueError("Rulebook compiler JSON confidence must be between 0.0 and 1.0.")

    expression = expression.strip()

    if operation_kind == "unsupported" and is_supported:
        raise ValueError("operation_kind='unsupported' requires is_supported=false.")

    if not is_supported and expression:
        raise ValueError("Unsupported result must use an empty expression.")

    if is_supported:
        if not expression:
            raise ValueError("Supported result must include a non-empty expression.")

        unresolved_placeholders = ["<literal>", "<value>", "<fixed_literal>", "<input>"]

        if any(placeholder in expression for placeholder in unresolved_placeholders):
            raise ValueError(
                f"Rulebook expression contains unresolved placeholder: {expression!r}."
            )

        if operation_kind == "fixed_literal" and not expression.startswith("VAL_"):
            raise ValueError(
                "operation_kind='fixed_literal' but expression does not start with "
                f"'VAL_': {expression!r}."
            )

        if operation_kind == "source_field" and expression.startswith("VAL_"):
            raise ValueError(
                "operation_kind='source_field' but expression starts with VAL_. "
                "DTO/source fields must not be literals."
            )

    return {
        "evaluator": evaluator,
        "selected_record_ids": selected_record_ids,
        "operation_kind": operation_kind,
        "is_supported": is_supported,
        "expression": expression,
        "reason": reason.strip(),
        "confidence": confidence_float,
    }


def check_operation_kind_consistency(
    *,
    operation_type: str,
    operation_kind: str,
    expression: str,
    rhs_request: str,
    user_requirement: str,
) -> str:
    combined_text = f"{rhs_request} {user_requirement}"

    has_conditional_signal = text_has_any_signal(combined_text, CONDITIONAL_SIGNALS)
    has_source_field_signal = text_has_any_signal(combined_text, SOURCE_FIELD_SIGNALS)
    has_unit_conversion_signal = text_has_any_signal(
        combined_text, UNIT_CONVERSION_SIGNALS
    )

    if operation_type == "append_attribute_value":
        if operation_kind not in APPEND_VALUE_OPERATION_KINDS:
            return (
                "The planner operation_type is append_attribute_value, so the response "
                "must provide a valid value-side expression for the new sub-key. Return "
                "operation_kind='append_subkey' and expression as RHS value only."
            )
        return ""

    if has_conditional_signal and operation_kind == "fixed_literal":
        return (
            "The request contains conditional language, so operation_kind='fixed_literal' "
            "is incorrect. Reclassify as mapping and build source#condition|result,ELSE|default."
        )

    if has_source_field_signal and operation_kind == "fixed_literal":
        return (
            "The request contains DTO/source-field language, so operation_kind='fixed_literal' "
            "is incorrect. Reclassify as source_field and do not return VAL_<fieldPath>."
        )

    if has_source_field_signal and operation_kind == "unsupported":
        return (
            "The request contains DTO/source-field language and appears to include a valid path. "
            "Do not reject this only because no old evaluator token exists. Plain paths are "
            "fallback source DTO/JsonPath expressions in the merged rulebook."
        )

    if has_source_field_signal and expression.startswith("VAL_"):
        return (
            "The request asks for a DTO/source field, but the expression starts with VAL_. "
            "VAL_ means literal text, not field lookup."
        )

    if has_unit_conversion_signal and operation_kind == "fixed_literal":
        return (
            "The request contains conversion/type-cast language, so fixed_literal is likely incorrect. "
            "Use the exact rulebook conversion prefix or return unsupported."
        )

    return ""
