from __future__ import annotations

import pytest

from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
    load_attribute_value_runtime_spec,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.node import dsl_expression_node


def _base_state(
    requirement: str,
    operation_type: str = "add_attribute",
    *,
    attribute_name: str = "TestAttribute",
    rhs_request: str | None = None,
) -> dict:
    return {
        "user_requirement": requirement,
        "plan": {
            "operation_type": operation_type,
            "attribute_name": attribute_name,
            "new_attribute_name": attribute_name,
            "container_attribute_name": "",
            "append_key": "",
            "rhs_request": rhs_request if rhs_request is not None else requirement,
        },
        "template": {
            "template_id": "MT_TEST_TEMPLATE",
            "external_system": "RTF",
        },
        "oracle": {
            "sample_parameters": [],
            "current_attribute_value": "",
        },
        "warnings": [],
        "errors": [],
    }


@pytest.fixture(autouse=True)
def skip_expression_evaluator_llm(monkeypatch):
    """Unit tests assert deterministic compiler output without a second LLM pass."""

    def _passthrough_evaluator(*, state, structured_answer):
        return structured_answer, "", [], []

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.node.evaluate_compiled_expression",
        _passthrough_evaluator,
    )


def test_load_attribute_value_runtime_spec():
    spec = load_attribute_value_runtime_spec()

    assert isinstance(spec, dict)
    assert "spec_header" in spec
    assert "expression_grammar" in spec


def test_get_rulebook_prompt_summary():
    summary = get_rulebook_prompt_summary()

    assert "ATTRIBUTE_VALUE RUNTIME SPEC SUMMARY" in summary
    assert "VAL_" in summary


def test_dsl_expression_fixed_literal():
    state = _base_state(
        "For prepaid base plan rtf template, add a new attribute gundu with value 123",
        rhs_request="123",
    )

    result = dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "VAL_123"
    assert expression["selected_evaluator"] == "RULEBOOK"
    assert expression["operation_kind"] == "fixed_literal"
    assert expression["dsl_query"] == "RULEBOOK_DETERMINISTIC_COMPILER"
    assert expression["errors"] == []


def test_dsl_expression_mapping():
    state = _base_state(
        "For Prepaid Base Plan RTF request, add a new attribute AddToBillFlagCopy. "
        "If addToBill is false set false, otherwise true.",
        rhs_request="If addToBill is false set false, otherwise true.",
    )

    result = dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "addToBill#false|false,ELSE|true"
    assert expression["selected_evaluator"] == "RULEBOOK"
    assert expression["operation_kind"] == "mapping"
    assert expression["errors"] == []


def test_dsl_expression_unsupported_source_field_without_path():
    state = _base_state(
        "Duration should use dto field",
        operation_type="update_attribute_value",
        attribute_name="Duration",
        rhs_request="",
    )

    result = dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is False
    assert expression["compiled_rhs"] == ""
    assert expression["is_supported"] is False
    assert expression["operation_kind"] == "unsupported"
    assert expression["errors"] == [
        "DTO/source field language was present, but a valid field path could not be identified."
    ]


def test_dsl_expression_append_subkey():
    state = {
        "user_requirement": (
            "For Prepaid Base Plan ECM request, add CustomerType with value "
            "if subscriberType is PREPAID show 1 else 0 inside existing poAttributes."
        ),
        "plan": {
            "operation_type": "append_attribute_value",
            "attribute_name": "poAttributes",
            "new_attribute_name": "",
            "container_attribute_name": "poAttributes",
            "append_key": "CustomerType",
            "rhs_request": "if subscriberType is PREPAID show 1 else 0",
        },
        "template": {
            "template_id": "MT_ECM_PRE_BASEPLAN",
            "external_system": "ECM",
        },
        "oracle": {
            "sample_parameters": [],
            "current_attribute_value": "ExistingKey=VAL_Existing;",
        },
        "warnings": [],
        "errors": [],
    }

    result = dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "subscriberType#PREPAID|1,ELSE|0"
    assert expression["append_fragment"] == "CustomerType=subscriberType#PREPAID|1,ELSE|0;"
    assert expression["operation_kind"] == "append_subkey"
    assert expression["selected_evaluator"] == "RULEBOOK"
    assert expression["errors"] == []
