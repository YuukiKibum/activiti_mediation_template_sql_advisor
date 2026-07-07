from __future__ import annotations

import json

import pytest

from activiti_mediation_template_sql_advisor.graph.nodes import dsl_expression


def _base_state(requirement: str, operation_type: str = "add_attribute") -> dict:
    return {
        "user_requirement": requirement,
        "plan": {
            "operation_type": operation_type,
            "attribute_name": "TestAttribute",
            "new_attribute_name": "TestAttribute",
            "container_attribute_name": "",
            "append_key": "",
            "rhs_request": requirement,
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


def test_dsl_expression_fixed_literal(monkeypatch):
    def fake_answer(query: str, evaluator: str = "") -> str:
        return json.dumps(
            {
                "evaluator": "A",
                "selected_record_ids": ["A-VAL_"],
                "operation_kind": "fixed_literal",
                "is_supported": True,
                "expression": "VAL_123",
                "reason": "Fixed literal value.",
                "confidence": 1.0,
            }
        )

    monkeypatch.setattr(dsl_expression, "answer", fake_answer)

    state = _base_state(
        "For prepaid base plan rtf template, add a new attribute gundu with value 123"
    )

    result = dsl_expression.dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "VAL_123"
    assert expression["selected_evaluator"] == "A"
    assert expression["selected_record_id"] == "A-VAL_"
    assert expression["errors"] == []


def test_dsl_expression_mapping(monkeypatch):
    def fake_answer(query: str, evaluator: str = "") -> str:
        return json.dumps(
            {
                "evaluator": "B",
                "selected_record_ids": ["MAP-general", "NUANCE-dollar-dot-prefix"],
                "operation_kind": "mapping",
                "is_supported": True,
                "expression": "addToBill#false|false,ELSE|true",
                "reason": "Conditional mapping.",
                "confidence": 0.95,
            }
        )

    monkeypatch.setattr(dsl_expression, "answer", fake_answer)

    state = _base_state(
        "For Prepaid Base Plan RTF request, add a new attribute AddToBillFlagCopy. "
        "If addToBill is false set false, otherwise true."
    )

    result = dsl_expression.dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "addToBill#false|false,ELSE|true"
    assert expression["selected_evaluator"] == "B"
    assert expression["operation_kind"] == "mapping"
    assert expression["errors"] == []


def test_dsl_expression_unsupported(monkeypatch):
    def fake_answer(query: str, evaluator: str = "") -> str:
        return json.dumps(
            {
                "evaluator": "B",
                "selected_record_ids": ["UNSUPPORTED-time-conversion"],
                "operation_kind": "unsupported",
                "is_supported": False,
                "expression": "",
                "reason": "Seconds to minutes conversion is not supported by the KB.",
                "confidence": 1.0,
            }
        )

    monkeypatch.setattr(dsl_expression, "answer", fake_answer)

    state = _base_state(
        "For Prepaid Base Plan RTF request, update Duration by converting seconds to minutes.",
        operation_type="update_attribute_value",
    )

    result = dsl_expression.dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is False
    assert expression["compiled_rhs"] == ""
    assert expression["is_supported"] is False
    assert expression["errors"] == [
        "Seconds to minutes conversion is not supported by the KB."
    ]


def test_dsl_expression_append_subkey(monkeypatch):
    def fake_answer(query: str, evaluator: str = "") -> str:
        return json.dumps(
            {
                "evaluator": "B",
                "selected_record_ids": ["MAP-general"],
                "operation_kind": "append_subkey",
                "is_supported": True,
                "expression": "subscriberType#PREPAID|1,ELSE|0",
                "reason": "Append sub-key value mapping.",
                "confidence": 0.9,
            }
        )

    monkeypatch.setattr(dsl_expression, "answer", fake_answer)

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

    result = dsl_expression.dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == "subscriberType#PREPAID|1,ELSE|0"
    assert expression["append_fragment"] == "CustomerType=subscriberType#PREPAID|1,ELSE|0;"
    assert expression["operation_kind"] == "append_subkey"
    assert expression["errors"] == []