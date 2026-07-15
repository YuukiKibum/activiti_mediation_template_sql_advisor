from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    ALLOWED_OPERATION_KINDS,
    MAX_EXPRESSION_EVALUATOR_RETRIES,
    RULEBOOK_EVALUATOR,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.rulebook_llm import (
    check_operation_kind_consistency,
    parse_structured_answer,
    strip_json_fences,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.safety import (
    final_expression_safety_issues,
)
from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState

load_dotenv()


def build_expression_evaluator_query(
    *,
    state: AdvisorState,
    structured_answer: dict[str, Any],
    correction_note: str = "",
) -> str:
    plan = state.get("plan", {}) or {}

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
        runtime_spec_summary = get_rulebook_prompt_summary()
    except Exception as exc:
        runtime_spec_summary = f"ATTRIBUTE_VALUE runtime spec could not be loaded: {exc}"

    candidate = {
        "evaluator": structured_answer.get("evaluator", ""),
        "selected_record_ids": structured_answer.get("selected_record_ids", []),
        "operation_kind": structured_answer.get("operation_kind", ""),
        "is_supported": structured_answer.get("is_supported", False),
        "expression": structured_answer.get("expression", ""),
        "reason": structured_answer.get("reason", ""),
        "confidence": structured_answer.get("confidence", 0.0),
    }

    parts = [
        "You are an ATTRIBUTE_VALUE expression evaluator for an Activiti mediation SQL advisor.",
        "",
        "Your job:",
        "Check whether the candidate compiled expression fully satisfies the user's request.",
        "You may accept it, correct it, or reject it.",
        "",
        "Important:",
        "- Do NOT generate SQL.",
        "- Do NOT use evaluator A/B/C.",
        "- Use only evaluator='RULEBOOK'.",
        "- Return ONLY valid JSON.",
        "",
        "ATTRIBUTE_VALUE runtime spec summary:",
        runtime_spec_summary,
        "",
        "User requirement:",
        user_requirement,
        "",
        "Planner context:",
        json.dumps(
            {
                "operation_type": operation_type,
                "attribute_name": attribute_name,
                "new_attribute_name": new_attribute_name,
                "container_attribute_name": container_attribute_name,
                "append_key": append_key,
                "rhs_request": rhs_request,
            },
            indent=2,
        ),
        "",
        "Candidate compiled expression:",
        json.dumps(candidate, indent=2),
        "",
        "Evaluation rules:",
        "1. If the user asks for a static/literal value, expression should use VAL_<literal>.",
        "2. If the user asks for DTO/source field only, expression should be the plain source path, not VAL_<path>.",
        "3. If the user asks for DTO/source field AND convert to BOOLEAN, expression should be $BOOL_<sourcePath>.",
        "4. If the user asks for DTO/source field AND convert to integer/int, expression should be $INT_<sourcePath>.",
        "5. If the user asks for DTO/source field AND convert to long, expression should be $LONG_<sourcePath>.",
        "6. If the user asks for DTO/source field AND convert to float, expression should be $FLOAT_<sourcePath>.",
        "7. If the user asks for DTO/source field AND convert to double, expression should be $DOU_<sourcePath>.",
        "8. If the user asks for DTO/source field AND convert to decimal/BigDecimal, expression should be $DEC_<sourcePath>.",
        "9. If the user asks to extract number/digits only, expression should use $NUM_<sourcePath>.",
        "10. If the user asks to extract letters/alpha only, expression should use $STR_<sourcePath>.",
        "11. If the request has if/else logic, expression should use source#condition|result,ELSE|default.",
        "12. For append_attribute_value, operation_kind should be append_subkey and expression should be only the RHS value side.",
        "13. For append_attribute_value, do NOT include append_key= in expression.",
        "14. For append_attribute_value, do NOT include trailing semicolon in expression.",
        "15. Do NOT include location/context phrases like 'inside existing poAttributes' inside expression.",
        "16. For add_attribute/update_attribute_value atomic rows, expression must NOT be key=value;.",
        "",
        "Return ONLY this JSON shape:",
        json.dumps(
            {
                "decision": "accept | correct | reject",
                "corrected_operation_kind": "fixed_literal | source_field | mapping | unit_conversion_or_cast | concat | append_subkey | unsupported",
                "corrected_expression": "<final corrected RHS expression, or empty string if reject>",
                "selected_runtime_rules": ["RULEBOOK-..."],
                "reason": "<short reason>",
                "errors": [],
            },
            indent=2,
        ),
    ]

    if correction_note:
        parts.extend(
            [
                "",
                "Previous evaluator attempt failed this validation:",
                correction_note,
                "Fix your JSON decision.",
            ]
        )

    return "\n".join(parts)


def call_expression_evaluator_llm(evaluator_query: str) -> str:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The openai package is required for expression evaluator. Install it with: uv add openai"
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
                    "You are a strict JSON evaluator for "
                    "ACT_MEDIATION_PARAMETER.ATTRIBUTE_VALUE expressions. "
                    "Return JSON only."
                ),
            },
            {"role": "user", "content": evaluator_query},
        ],
    )

    return response.choices[0].message.content or ""


def parse_expression_evaluator_answer(raw_answer: str) -> dict[str, Any]:
    text = strip_json_fences(raw_answer)

    if not text:
        raise ValueError("Expression evaluator returned an empty response; expected JSON object.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Expression evaluator did not return valid JSON: {exc.msg}. Raw answer: {raw_answer}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Expression evaluator JSON must be an object.")

    required_keys = {
        "decision",
        "corrected_operation_kind",
        "corrected_expression",
        "selected_runtime_rules",
        "reason",
        "errors",
    }

    missing_keys = sorted(required_keys - set(data.keys()))

    if missing_keys:
        raise ValueError(
            "Expression evaluator JSON is missing required keys: " + ", ".join(missing_keys)
        )

    decision = data["decision"]

    if decision not in {"accept", "correct", "reject"}:
        raise ValueError(
            f"Expression evaluator decision must be accept/correct/reject, got {decision!r}."
        )

    operation_kind = data["corrected_operation_kind"]

    if operation_kind not in ALLOWED_OPERATION_KINDS:
        raise ValueError(
            f"Expression evaluator returned invalid corrected_operation_kind={operation_kind!r}."
        )

    expression = data["corrected_expression"]

    if not isinstance(expression, str):
        raise ValueError("Expression evaluator corrected_expression must be a string.")

    selected_runtime_rules = data["selected_runtime_rules"]

    if not isinstance(selected_runtime_rules, list) or not all(
        isinstance(item, str) for item in selected_runtime_rules
    ):
        raise ValueError("Expression evaluator selected_runtime_rules must be a list of strings.")

    reason = data["reason"]

    if not isinstance(reason, str):
        raise ValueError("Expression evaluator reason must be a string.")

    errors = data["errors"]

    if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
        raise ValueError("Expression evaluator errors must be a list of strings.")

    return {
        "decision": decision,
        "corrected_operation_kind": operation_kind,
        "corrected_expression": expression.strip(),
        "selected_runtime_rules": selected_runtime_rules,
        "reason": reason.strip(),
        "errors": errors,
    }


def evaluator_decision_to_structured_answer(
    *,
    original_structured_answer: dict[str, Any],
    evaluator_decision: dict[str, Any],
) -> dict[str, Any]:
    decision = evaluator_decision["decision"]

    if decision == "accept":
        return original_structured_answer

    if decision == "reject":
        return parse_structured_answer(
            {
                "evaluator": RULEBOOK_EVALUATOR,
                "selected_record_ids": evaluator_decision.get("selected_runtime_rules")
                or ["RULEBOOK-EVALUATOR-REJECT"],
                "operation_kind": "unsupported",
                "is_supported": False,
                "expression": "",
                "reason": evaluator_decision.get("reason")
                or "Expression evaluator rejected the candidate expression.",
                "confidence": 0.0,
            }
        )

    return parse_structured_answer(
        {
            "evaluator": RULEBOOK_EVALUATOR,
            "selected_record_ids": evaluator_decision.get("selected_runtime_rules")
            or original_structured_answer.get("selected_record_ids", [])
            or ["RULEBOOK-EVALUATOR-CORRECTED"],
            "operation_kind": evaluator_decision["corrected_operation_kind"],
            "is_supported": True,
            "expression": evaluator_decision["corrected_expression"],
            "reason": evaluator_decision.get("reason")
            or "Expression evaluator corrected the candidate expression.",
            "confidence": min(float(original_structured_answer.get("confidence", 1.0)), 0.95),
        }
    )


def evaluate_compiled_expression(
    *,
    state: AdvisorState,
    structured_answer: dict[str, Any],
) -> tuple[dict[str, Any], str, list[str], list[str]]:
    plan = state.get("plan", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")
    user_requirement = str(
        state.get("user_requirement", "")
        or state.get("requirement", "")
        or ""
    )

    evaluator_warnings: list[str] = []
    evaluator_errors: list[str] = []
    raw_evaluator_answer = ""
    correction_note = ""

    current_answer = structured_answer

    for attempt in range(MAX_EXPRESSION_EVALUATOR_RETRIES + 1):
        evaluator_query = build_expression_evaluator_query(
            state=state,
            structured_answer=current_answer,
            correction_note=correction_note,
        )

        try:
            raw_evaluator_answer = call_expression_evaluator_llm(evaluator_query)
            evaluator_decision = parse_expression_evaluator_answer(raw_evaluator_answer)
            evaluated_answer = evaluator_decision_to_structured_answer(
                original_structured_answer=current_answer,
                evaluator_decision=evaluator_decision,
            )
        except Exception as exc:
            evaluator_warnings.append(f"Expression evaluator failed; using compiler output: {exc}")
            evaluated_answer = current_answer

        consistency_issue = check_operation_kind_consistency(
            operation_type=operation_type,
            operation_kind=evaluated_answer["operation_kind"],
            expression=evaluated_answer["expression"],
            rhs_request=rhs_request,
            user_requirement=user_requirement,
        )

        safety_issues = final_expression_safety_issues(
            operation_type=operation_type,
            operation_kind=evaluated_answer["operation_kind"],
            expression=evaluated_answer["expression"],
            rhs_request=rhs_request,
            user_requirement=user_requirement,
        )

        all_issues: list[str] = []
        if consistency_issue:
            all_issues.append(consistency_issue)
        all_issues.extend(safety_issues)

        if not all_issues:
            if evaluated_answer != structured_answer:
                evaluator_warnings.append(
                    "Expression evaluator corrected the compiled expression before SQL generation."
                )

            return evaluated_answer, raw_evaluator_answer, evaluator_warnings, evaluator_errors

        if attempt < MAX_EXPRESSION_EVALUATOR_RETRIES:
            correction_note = " ".join(all_issues)
            current_answer = evaluated_answer
            evaluator_warnings.append(
                f"Expression evaluator attempt {attempt + 1} still had issues; retrying."
            )
            continue

        evaluator_errors.extend(all_issues)

        return evaluated_answer, raw_evaluator_answer, evaluator_warnings, evaluator_errors

    return current_answer, raw_evaluator_answer, evaluator_warnings, evaluator_errors
