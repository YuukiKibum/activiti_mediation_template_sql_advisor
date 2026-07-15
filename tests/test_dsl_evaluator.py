from __future__ import annotations

import pytest

from activiti_mediation_template_sql_advisor.dsl_compiler.evaluator import (
    evaluate_compiled_expression,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.safety import (
    final_expression_safety_issues,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import structured


def _state(
    *,
    operation_type: str = "update_attribute_value",
    rhs_request: str,
    attribute_name: str = "isActiveFlag",
) -> dict:
    return {
        "user_requirement": rhs_request,
        "plan": {
            "operation_type": operation_type,
            "attribute_name": attribute_name,
            "new_attribute_name": attribute_name,
            "container_attribute_name": "",
            "append_key": "",
            "rhs_request": rhs_request,
        },
        "template": {
            "template_id": "MT_TEST_TEMPLATE",
            "external_system": "RTF",
        },
        "oracle": {"sample_parameters": [], "current_attribute_value": ""},
    }


def test_evaluator_correction_path(monkeypatch):
    """Evaluator should upgrade plain source path to $BOOL_ when boolean conversion is requested."""

    candidate = structured(
        operation_kind="source_field",
        expression="flags.isActive",
        reason="Deterministic source field compile.",
    )

    def fake_evaluator_llm(_query: str) -> str:
        return """
        {
          "decision": "correct",
          "corrected_operation_kind": "unit_conversion_or_cast",
          "corrected_expression": "$BOOL_flags.isActive",
          "selected_runtime_rules": ["RULEBOOK-BOOL"],
          "reason": "Boolean conversion requires $BOOL_ prefix.",
          "errors": []
        }
        """

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.evaluator.call_expression_evaluator_llm",
        fake_evaluator_llm,
    )

    state = _state(
        rhs_request="dto field flags.isActive and convert it to boolean",
    )

    evaluated, raw_answer, warnings, errors = evaluate_compiled_expression(
        state=state,
        structured_answer=candidate,
    )

    assert raw_answer
    assert errors == []
    assert evaluated["operation_kind"] == "unit_conversion_or_cast"
    assert evaluated["expression"] == "$BOOL_flags.isActive"
    assert any("corrected" in warning.lower() for warning in warnings)


def test_evaluator_reject_path(monkeypatch):
    candidate = structured(
        operation_kind="fixed_literal",
        expression="VAL_flags.isActive",
        reason="Incorrect literal classification.",
    )

    def fake_evaluator_llm(_query: str) -> str:
        return """
        {
          "decision": "reject",
          "corrected_operation_kind": "unsupported",
          "corrected_expression": "",
          "selected_runtime_rules": ["RULEBOOK-EVALUATOR-REJECT"],
          "reason": "DTO field must not be emitted as VAL_ literal.",
          "errors": ["VAL_ prefix is invalid for source fields"]
        }
        """

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.evaluator.call_expression_evaluator_llm",
        fake_evaluator_llm,
    )

    state = _state(rhs_request="unconditional literal value only")

    evaluated, _, warnings, errors = evaluate_compiled_expression(
        state=state,
        structured_answer=candidate,
    )

    assert evaluated["is_supported"] is False
    assert evaluated["expression"] == ""
    assert evaluated["operation_kind"] == "unsupported"


def test_evaluator_safety_disagreement_after_accept(monkeypatch):
    """Even an accept decision must fail hard safety checks for boolean conversion."""

    candidate = structured(
        operation_kind="source_field",
        expression="flags.isActive",
        reason="Compiler left plain source path.",
    )

    def fake_evaluator_llm(_query: str) -> str:
        return """
        {
          "decision": "accept",
          "corrected_operation_kind": "source_field",
          "corrected_expression": "flags.isActive",
          "selected_runtime_rules": ["RULEBOOK-SOURCE_FIELD"],
          "reason": "Looks fine.",
          "errors": []
        }
        """

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.evaluator.call_expression_evaluator_llm",
        fake_evaluator_llm,
    )

    state = _state(
        rhs_request="dto field flags.isActive and convert it to boolean",
    )

    _, _, warnings, errors = evaluate_compiled_expression(
        state=state,
        structured_answer=candidate,
    )

    assert errors
    assert any("$BOOL_" in issue for issue in errors)
    assert any("attempt" in warning.lower() for warning in warnings)


def test_final_expression_safety_issues_boolean():
    issues = final_expression_safety_issues(
        operation_type="update_attribute_value",
        operation_kind="source_field",
        expression="flags.isActive",
        rhs_request="dto field flags.isActive and convert to boolean",
        user_requirement="",
    )

    assert any("$BOOL_" in issue for issue in issues)
