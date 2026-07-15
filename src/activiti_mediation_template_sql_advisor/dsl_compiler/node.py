from __future__ import annotations

import json
from typing import Any

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    MAX_CLASSIFICATION_RETRIES,
    RULEBOOK_EVALUATOR,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.deterministic import (
    try_compile_deterministically,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.evaluator import (
    evaluate_compiled_expression,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import build_append_fragment
from activiti_mediation_template_sql_advisor.dsl_compiler.rulebook_llm import (
    build_dsl_query,
    call_rulebook_llm,
    check_operation_kind_consistency,
    parse_structured_answer,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def operation_requires_dsl(operation_type: str) -> bool:
    return operation_type in {
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
    }


def dsl_expression_node(state: AdvisorState) -> dict[str, Any]:
    plan = state.get("plan", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    append_key = str(plan.get("append_key", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")
    user_requirement = str(
        state.get("user_requirement", "") or state.get("requirement", "") or ""
    )

    warnings: list[str] = []
    errors: list[str] = []

    if not operation_requires_dsl(operation_type):
        expression_result = {
            "did_compile": False,
            "is_supported": True,
            "selected_evaluator": "",
            "selected_record_id": "",
            "selected_record_ids": [],
            "operation_kind": "",
            "original_operation_kind": "",
            "compiled_rhs": "",
            "append_fragment": "",
            "confidence": 0.0,
            "raw_answer": f"DSL expression not required for operation_type={operation_type}.",
            "structured_answer": {},
            "reason": f"DSL expression not required for operation_type={operation_type}.",
            "warnings": warnings,
            "errors": errors,
        }

        return {"expression": expression_result}

    raw_answer: str | dict[str, Any] = ""
    structured_answer: dict[str, Any] = {}
    last_error = ""
    dsl_query = ""

    deterministic_answer = try_compile_deterministically(state)

    if deterministic_answer is not None:
        raw_answer = deterministic_answer
        structured_answer = parse_structured_answer(deterministic_answer)
        dsl_query = "RULEBOOK_DETERMINISTIC_COMPILER"
    else:
        correction_note = ""

        for attempt in range(MAX_CLASSIFICATION_RETRIES + 1):
            dsl_query = build_dsl_query(state, correction_note=correction_note)

            try:
                raw_answer = call_rulebook_llm(dsl_query)
            except Exception as exc:
                error = f"dsl_expression_node failed while calling rulebook LLM fallback: {exc}"

                expression_result = {
                    "did_compile": False,
                    "is_supported": False,
                    "selected_evaluator": RULEBOOK_EVALUATOR,
                    "selected_record_id": "",
                    "selected_record_ids": [],
                    "operation_kind": "",
                    "original_operation_kind": "",
                    "compiled_rhs": "",
                    "append_fragment": "",
                    "confidence": 0.0,
                    "raw_answer": "",
                    "structured_answer": {},
                    "reason": error,
                    "warnings": warnings,
                    "errors": [error],
                    "dsl_query": dsl_query,
                }

                return {
                    "expression": expression_result,
                    "errors": list(state.get("errors", []) or []) + [error],
                }

            try:
                structured_answer = parse_structured_answer(raw_answer)
            except ValueError as exc:
                last_error = str(exc)
                structured_answer = {}

                if attempt < MAX_CLASSIFICATION_RETRIES:
                    correction_note = (
                        "Your previous response failed validation with this error: "
                        f"{last_error}. Fix this and return a corrected JSON object "
                        "following the schema exactly."
                    )
                    warnings.append(
                        f"Attempt {attempt + 1} failed JSON validation, retrying: {last_error}"
                    )
                    continue

                expression_result = {
                    "did_compile": False,
                    "is_supported": False,
                    "selected_evaluator": RULEBOOK_EVALUATOR,
                    "selected_record_id": "",
                    "selected_record_ids": [],
                    "operation_kind": "",
                    "original_operation_kind": "",
                    "compiled_rhs": "",
                    "append_fragment": "",
                    "confidence": 0.0,
                    "raw_answer": raw_answer,
                    "structured_answer": {},
                    "reason": last_error,
                    "warnings": warnings,
                    "errors": [last_error],
                    "dsl_query": dsl_query,
                }

                return {
                    "expression": expression_result,
                    "errors": list(state.get("errors", []) or []) + [last_error],
                }

            consistency_issue = check_operation_kind_consistency(
                operation_type=operation_type,
                operation_kind=structured_answer["operation_kind"],
                expression=structured_answer["expression"],
                rhs_request=rhs_request,
                user_requirement=user_requirement,
            )

            if not consistency_issue:
                break

            last_error = (
                "Semantic consistency check failed: operation_kind="
                f"{structured_answer['operation_kind']!r} does not match the "
                "rulebook language used in the request."
            )

            if attempt < MAX_CLASSIFICATION_RETRIES:
                correction_note = consistency_issue
                warnings.append(
                    f"Attempt {attempt + 1} returned operation_kind="
                    f"{structured_answer['operation_kind']!r} which conflicts with "
                    "rulebook language; retrying with an explicit correction."
                )
                structured_answer = {}
                continue

            expression_result = {
                "did_compile": False,
                "is_supported": False,
                "selected_evaluator": RULEBOOK_EVALUATOR,
                "selected_record_id": "",
                "selected_record_ids": [],
                "operation_kind": structured_answer.get("operation_kind", ""),
                "original_operation_kind": structured_answer.get("operation_kind", ""),
                "compiled_rhs": "",
                "append_fragment": "",
                "confidence": 0.0,
                "raw_answer": raw_answer,
                "structured_answer": structured_answer,
                "reason": (
                    last_error
                    + " Retries exhausted; refusing to auto-correct. Please review "
                    "the request and/or the rulebook prompt manually."
                ),
                "warnings": warnings,
                "errors": [last_error],
                "dsl_query": dsl_query,
            }

            return {
                "expression": expression_result,
                "errors": list(state.get("errors", []) or []) + [last_error],
            }

    evaluator_raw_answer = ""

    if structured_answer and structured_answer.get("is_supported", False):
        (
            structured_answer,
            evaluator_raw_answer,
            evaluator_warnings,
            evaluator_errors,
        ) = evaluate_compiled_expression(
            state=state,
            structured_answer=structured_answer,
        )

        if evaluator_warnings:
            warnings.extend(evaluator_warnings)

        if evaluator_errors:
            errors.extend(evaluator_errors)

    selected_record_ids = structured_answer["selected_record_ids"]
    selected_record_id = ", ".join(selected_record_ids)

    evaluator = structured_answer["evaluator"]
    operation_kind = structured_answer["operation_kind"]
    effective_operation_kind = operation_kind
    is_supported = structured_answer["is_supported"]
    compiled_rhs = structured_answer["expression"]
    reason = structured_answer["reason"]
    confidence = structured_answer["confidence"]

    append_fragment = ""

    if not is_supported:
        errors.append(reason or "Rulebook compiler marked this RHS as unsupported.")

    if is_supported and operation_type == "append_attribute_value":
        if operation_kind != "append_subkey":
            warnings.append(
                "Normalized structured operation_kind "
                f"from {operation_kind!r} to 'append_subkey' because planner "
                "operation_type is append_attribute_value. The expression was kept "
                "unchanged and used as the value side."
            )
            effective_operation_kind = "append_subkey"

        append_fragment = build_append_fragment(
            append_key=append_key,
            expression=compiled_rhs,
        )

        if not append_fragment:
            errors.append(
                "Could not build append fragment from append key and structured expression."
            )

    if is_supported and operation_type in {"add_attribute", "update_attribute_value"}:
        if operation_kind == "append_subkey":
            errors.append(f"{operation_type} cannot use operation_kind='append_subkey'.")

    did_compile = bool(compiled_rhs) and is_supported and not errors

    expression_result = {
        "did_compile": did_compile,
        "is_supported": is_supported,
        "selected_evaluator": evaluator,
        "selected_record_id": selected_record_id,
        "selected_record_ids": selected_record_ids,
        "operation_kind": effective_operation_kind,
        "original_operation_kind": operation_kind,
        "compiled_rhs": compiled_rhs if did_compile else "",
        "append_fragment": append_fragment if did_compile else "",
        "confidence": confidence if did_compile else 0.0,
        "raw_answer": raw_answer if isinstance(raw_answer, str) else json.dumps(raw_answer, ensure_ascii=False),
        "evaluator_raw_answer": evaluator_raw_answer,
        "was_evaluated": bool(evaluator_raw_answer),
        "structured_answer": structured_answer,
        "reason": reason,
        "warnings": warnings,
        "errors": errors,
        "dsl_query": dsl_query,
    }

    updates: dict[str, Any] = {"expression": expression_result}

    if warnings:
        updates["warnings"] = list(state.get("warnings", []) or []) + warnings

    if errors:
        updates["errors"] = list(state.get("errors", []) or []) + errors

    return updates
