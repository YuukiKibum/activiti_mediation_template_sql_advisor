from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import structured
from activiti_mediation_template_sql_advisor.dsl_compiler.rulebook_llm import (
    parse_structured_answer,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.safety import (
    final_expression_safety_issues,
)
from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    load_attribute_value_runtime_spec,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.node import dsl_expression_node

RUNTIME_SPEC_COMPILE_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "eval" / "runtime_spec_compile_cases.jsonl"
)


def load_jsonl_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid runtime spec case JSON at line {line_number}: {exc}"
                ) from exc

    return cases


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower() or "case"


def _iter_prefix_rules() -> list[dict[str, Any]]:
    spec = load_attribute_value_runtime_spec()
    prefix_families = (
        spec.get("expression_grammar", {}).get("prefix_operations_by_family", {}) or {}
    )

    rules: list[dict[str, Any]] = []

    for family_name, family_rules in prefix_families.items():
        for rule in family_rules:
            if not isinstance(rule, dict):
                continue

            token = str(rule.get("token", "") or "")
            example = rule.get("example", {}) or {}
            expression = str(example.get("authored_attribute_value", "") or "")

            if not token or not expression:
                continue

            rules.append(
                {
                    "id": f"prefix_{_slug(token)}",
                    "family": family_name,
                    "token": token,
                    "expression": expression,
                }
            )

    return rules


def _iter_complex_method_rules() -> list[dict[str, Any]]:
    spec = load_attribute_value_runtime_spec()
    methods = (
        spec.get("expression_grammar", {})
        .get("complex_function_calls", {})
        .get("methods", [])
        or []
    )

    rules: list[dict[str, Any]] = []

    for method in methods:
        if not isinstance(method, dict):
            continue

        call_name = str(method.get("call_name", "") or "")
        example = method.get("example", {}) or {}
        expression = str(example.get("authored_attribute_value", "") or "")

        if not call_name or not expression:
            continue

        rules.append(
            {
                "id": f"complex_{_slug(call_name)}",
                "call_name": call_name,
                "expression": expression,
            }
        )

    return rules


def _iter_storage_compile_cases() -> list[dict[str, Any]]:
    spec = load_attribute_value_runtime_spec()
    storage = spec.get("storage_contracts", {}) or {}
    cases: list[dict[str, Any]] = []

    for shape_name, shape_key in (
        ("normal", "normal_attribute_row"),
        ("container", "container_attribute_row"),
    ):
        shape = storage.get(shape_key, {}) or {}

        for index, example in enumerate(shape.get("examples", []) or [], start=1):
            if not isinstance(example, dict):
                continue

            if not example.get("compiled_expression"):
                continue

            cases.append(
                {
                    "id": f"storage_{shape_name}_{index}",
                    "shape": shape_name,
                    "example": example,
                }
            )

    return cases


def _iter_resolution_scenarios() -> list[dict[str, Any]]:
    spec = load_attribute_value_runtime_spec()
    scenarios = (
        spec.get("compiler_examples", {}).get("runtime_resolution_examples", []) or []
    )

    items: list[dict[str, Any]] = []

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue

        scenario_id = scenario.get("id")
        attribute_value = str(scenario.get("attribute_value_string", "") or "")

        if scenario_id is None or not attribute_value:
            continue

        items.append(
            {
                "id": f"resolution_{scenario_id}",
                "scenario": str(scenario.get("scenario", "") or ""),
                "attribute_value_string": attribute_value,
            }
        )

    return items


def _split_composite_expression(attribute_value: str) -> list[str]:
    segments: list[str] = []

    for part in attribute_value.split(";"):
        part = part.strip()
        if not part:
            continue

        if "=" in part:
            _, value = part.split("=", 1)
            segments.append(value.strip())
        else:
            segments.append(part)

    return segments


def infer_operation_kind(expression: str) -> str:
    expr = expression.strip()

    if not expr:
        return "unsupported"

    if expr.startswith("VAL_"):
        return "fixed_literal"

    if expr.startswith("$CONCAT_") or expr.startswith("$MAP_"):
        return "concat"

    if "#" in expr:
        left, right = expr.split("#", 1)
        if "^" not in left and ("|" in right or "ELSE|" in right):
            if not left.startswith("$ANY") and not left.startswith("$ALL"):
                return "mapping"

    if expr.startswith("$") or "$M_" in expr:
        return "unit_conversion_or_cast"

    if "=" in expr:
        return "unsupported"

    return "source_field"


EDGE_CASE_SAFETY_CASES: list[dict[str, Any]] = [
    {
        "id": "edge_append_must_be_value_only",
        "operation_type": "append_attribute_value",
        "operation_kind": "append_subkey",
        "expression": "CustomerType=VAL_123;",
        "rhs_request": "value 123 inside existing poAttributes",
        "expect_issue": "append_key=",
    },
    {
        "id": "edge_source_field_must_not_use_val",
        "operation_type": "update_attribute_value",
        "operation_kind": "source_field",
        "expression": "VAL_allowances.sms.freebies",
        "rhs_request": "dto field allowances.sms.freebies",
        "expect_issue": "VAL_",
    },
    {
        "id": "edge_boolean_requires_bool_prefix",
        "operation_type": "update_attribute_value",
        "operation_kind": "source_field",
        "expression": "flags.isActive",
        "rhs_request": "dto field flags.isActive and convert to boolean",
        "expect_issue": "$BOOL_",
    },
    {
        "id": "edge_atomic_row_must_not_be_key_value",
        "operation_type": "add_attribute",
        "operation_kind": "fixed_literal",
        "expression": "gundu=VAL_123;",
        "rhs_request": "value 123",
        "expect_issue": "key=value",
    },
    {
        "id": "edge_location_text_must_not_be_in_expression",
        "operation_type": "append_attribute_value",
        "operation_kind": "append_subkey",
        "expression": "VAL_123 inside existing poAttributes",
        "rhs_request": "value 123 inside existing poAttributes",
        "expect_issue": "inside existing",
    },
]


@pytest.fixture(autouse=True)
def passthrough_expression_evaluator(monkeypatch):
    def _passthrough_evaluator(*, state, structured_answer):
        return structured_answer, "", [], []

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.node.evaluate_compiled_expression",
        _passthrough_evaluator,
    )


def _build_dsl_state(
    *,
    user_requirement: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "user_requirement": user_requirement,
        "plan": plan,
        "template": {
            "template_id": "MT_TEST_TEMPLATE",
            "external_system": "RTF",
        },
        "oracle": {
            "sample_parameters": [],
            "current_attribute_value": "ExistingKey=VAL_Existing;",
        },
        "warnings": [],
        "errors": [],
    }


def _storage_case_to_state(case: dict[str, Any]) -> dict[str, Any]:
    example = case["example"]
    user_intent = str(example.get("user_intent", "") or "")

    if case["shape"] == "container":
        plan = {
            "operation_type": "append_attribute_value",
            "attribute_name": str(example.get("container_attribute_name", "") or ""),
            "new_attribute_name": "",
            "container_attribute_name": str(
                example.get("container_attribute_name", "") or ""
            ),
            "append_key": str(example.get("append_key", "") or ""),
            "rhs_request": user_intent,
        }
    else:
        attribute_name = str(example.get("attribute_name", "") or "")
        plan = {
            "operation_type": "add_attribute",
            "attribute_name": attribute_name,
            "new_attribute_name": attribute_name,
            "container_attribute_name": "",
            "append_key": "",
            "rhs_request": user_intent,
        }

    return _build_dsl_state(user_requirement=user_intent, plan=plan)


@pytest.mark.parametrize("rule", _iter_prefix_rules(), ids=lambda rule: rule["id"])
def test_runtime_spec_prefix_example_is_valid(rule: dict[str, Any]):
    expression = rule["expression"]

    if (
        "=" in expression
        and ";" in expression
        and not expression.startswith("$MAP_")
    ):
        pytest.skip("Composite ATTRIBUTE_VALUE strings are covered by resolution scenarios.")

    operation_kind = infer_operation_kind(expression)

    parsed = parse_structured_answer(
        structured(
            operation_kind=operation_kind,
            expression=expression,
            reason=f"Runtime spec prefix example for {rule['token']}.",
            selected_record_ids=[f"RULEBOOK-{rule['token'].strip('_')}"],
        )
    )

    assert parsed["expression"] == expression
    assert parsed["is_supported"] is True


@pytest.mark.parametrize(
    "rule",
    _iter_complex_method_rules(),
    ids=lambda rule: rule["id"],
)
def test_runtime_spec_complex_method_example_is_valid(rule: dict[str, Any]):
    expression = rule["expression"]

    parsed = parse_structured_answer(
        structured(
            operation_kind="unit_conversion_or_cast",
            expression=expression,
            reason=f"Runtime spec complex method example for {rule['call_name']}.",
            selected_record_ids=[f"RULEBOOK-{rule['call_name'].lstrip('$')}"],
        )
    )

    assert parsed["expression"] == expression
    assert parsed["is_supported"] is True


@pytest.mark.parametrize(
    "case",
    _iter_storage_compile_cases(),
    ids=lambda case: case["id"],
)
def test_runtime_spec_storage_shape_compiles(case: dict[str, Any]):
    example = case["example"]
    state = _storage_case_to_state(case)

    result = dsl_expression_node(state)
    expression = result["expression"]

    assert expression["did_compile"] is True
    assert expression["compiled_rhs"] == example["compiled_expression"]

    if case["shape"] == "container":
        append_key = str(example.get("append_key", "") or "")
        expected_fragment = example.get("append_fragment")
        if expected_fragment:
            assert expression["append_fragment"] == expected_fragment
        else:
            assert expression["append_fragment"] == f"{append_key}={example['compiled_expression']};"
        assert expression["operation_kind"] == "append_subkey"
    else:
        assert expression["operation_kind"] in {
            "fixed_literal",
            "source_field",
            "mapping",
        }


@pytest.mark.parametrize(
    "scenario",
    _iter_resolution_scenarios(),
    ids=lambda scenario: scenario["id"],
)
def test_runtime_spec_resolution_scenario_expressions_are_valid(scenario: dict[str, Any]):
    for segment_expression in _split_composite_expression(
        scenario["attribute_value_string"]
    ):
        operation_kind = infer_operation_kind(segment_expression)

        if operation_kind == "unsupported":
            continue

        parsed = parse_structured_answer(
            structured(
                operation_kind=operation_kind,
                expression=segment_expression,
                reason=f"Runtime spec resolution scenario: {scenario['scenario']}.",
                selected_record_ids=[scenario["id"]],
            )
        )

        assert parsed["expression"] == segment_expression
        assert parsed["is_supported"] is True


@pytest.mark.parametrize(
    "case",
    EDGE_CASE_SAFETY_CASES,
    ids=lambda case: case["id"],
)
def test_runtime_spec_edge_case_safety(case: dict[str, Any]):
    issues = final_expression_safety_issues(
        operation_type=case["operation_type"],
        operation_kind=case["operation_kind"],
        expression=case["expression"],
        rhs_request=case["rhs_request"],
        user_requirement=case["rhs_request"],
    )

    assert issues
    assert any(case["expect_issue"] in issue for issue in issues)


@pytest.mark.parametrize(
    "case",
    load_jsonl_cases(RUNTIME_SPEC_COMPILE_CASES_PATH),
    ids=lambda case: case["id"],
)
def test_runtime_spec_compile_case(case: dict[str, Any], monkeypatch):
    compile_mode = case.get("compile_mode", "deterministic")

    if compile_mode == "mock_rulebook":
        mock_answer = case["mock_structured_answer"]

        def fake_rulebook_llm(_query: str) -> str:
            return json.dumps(mock_answer)

        monkeypatch.setattr(
            "activiti_mediation_template_sql_advisor.dsl_compiler.node.try_compile_deterministically",
            lambda _state: None,
        )
        monkeypatch.setattr(
            "activiti_mediation_template_sql_advisor.dsl_compiler.node.call_rulebook_llm",
            fake_rulebook_llm,
        )

    state = _build_dsl_state(
        user_requirement=case["user_requirement"],
        plan=case["plan"],
    )

    result = dsl_expression_node(state)
    expression = result["expression"]
    expect = case["expect"]

    assert expression["did_compile"] is expect["did_compile"]
    assert expression["compiled_rhs"] == expect["compiled_rhs"]
    assert expression["operation_kind"] == expect["operation_kind"]
