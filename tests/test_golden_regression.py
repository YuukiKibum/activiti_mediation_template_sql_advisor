from __future__ import annotations

import json
from pathlib import Path

import pytest

from activiti_mediation_template_sql_advisor.dsl_compiler.node import dsl_expression_node
from activiti_mediation_template_sql_advisor.template_registry.loader import (
    get_template_registry,
)

GOLDEN_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "eval" / "golden_cases.jsonl"
)


def load_golden_cases(path: Path = GOLDEN_CASES_PATH) -> list[dict]:
    cases: list[dict] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid golden case JSON at line {line_number}: {exc}"
                ) from exc

    return cases


@pytest.fixture(autouse=True)
def reset_template_registry_cache():
    get_template_registry.cache_clear()
    yield
    get_template_registry.cache_clear()


@pytest.fixture(autouse=True)
def skip_expression_evaluator_llm(monkeypatch):
    def _passthrough_evaluator(*, state, structured_answer):
        return structured_answer, "", [], []

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.node.evaluate_compiled_expression",
        _passthrough_evaluator,
    )


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda case: case["id"])
def test_golden_template_resolution(case: dict):
    from activiti_mediation_template_sql_advisor.graph.nodes.template_resolution import (
        template_resolution_node,
    )

    state = {
        "user_requirement": case["user_requirement"],
        "plan": case["plan"],
        "warnings": [],
        "errors": [],
    }

    result = template_resolution_node(state)
    template = result["template"]
    expected = case["expect"]

    assert template.get("is_resolved") is expected["template_resolved"]
    assert template.get("template_id", "") == expected.get("template_id", "")


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda case: case["id"])
def test_golden_dsl_compilation(case: dict):
    expected = case["expect"]

    if expected.get("requires_dsl") is False:
        pytest.skip("DSL compilation not required for this golden case.")

    if not expected.get("compiled_rhs") and not expected.get("append_fragment"):
        pytest.skip("No DSL expectation defined for this golden case.")

    state = {
        "user_requirement": case["user_requirement"],
        "plan": case["plan"],
        "template": {
            "template_id": expected.get("template_id", ""),
            "external_system": case["plan"].get("external_system", ""),
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

    if expected.get("compiled_rhs"):
        assert expression["compiled_rhs"] == expected["compiled_rhs"]

    if expected.get("append_fragment"):
        assert expression["append_fragment"] == expected["append_fragment"]
