from __future__ import annotations

import pytest

from activiti_mediation_template_sql_advisor.graph.builder import (
    build_advisor_graph,
    get_advisor_graph,
)


@pytest.fixture
def e2e_graph(monkeypatch):
    get_advisor_graph.cache_clear()

    async def fake_oracle_call_tool(tool_name: str, arguments: dict):
        template_id = arguments.get("template_id", "")
        attribute_name = arguments.get("attribute_name", "")
        target_attribute_name = arguments.get("target_attribute_name", "")

        parameter_row = None
        target_parameter_row = None

        if target_attribute_name and target_attribute_name != attribute_name:
            if attribute_name:
                parameter_row = {
                    "PARAM_ID": "1001",
                    "TEMPLATE_ID": template_id,
                    "ATTRIBUTE_NAME": attribute_name,
                    "ATTRIBUTE_VALUE": "ExistingKey=VAL_Existing;",
                }
        elif target_attribute_name and target_attribute_name == attribute_name:
            parameter_row = None
        elif attribute_name:
            parameter_row = {
                "PARAM_ID": "1001",
                "TEMPLATE_ID": template_id,
                "ATTRIBUTE_NAME": attribute_name,
                "ATTRIBUTE_VALUE": "ExistingKey=VAL_Existing;",
            }

        if target_attribute_name and target_attribute_name != attribute_name:
            target_parameter_row = None

        return {
            "template_exists": True,
            "template_row": {"TEMPLATE_ID": template_id},
            "parameter_row": parameter_row,
            "target_parameter_row": target_parameter_row,
            "sample_parameters": [
                {
                    "ATTRIBUTE_NAME": "SampleAttr",
                    "ATTRIBUTE_VALUE": "VAL_Sample;",
                }
            ],
        }

    class FakeManager:
        @classmethod
        async def call_tool(cls, tool_name: str, arguments: dict | None = None):
            return await fake_oracle_call_tool(tool_name, arguments or {})

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.graph.nodes.oracle_inspection.OracleMCPClientManager",
        FakeManager,
    )

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.dsl_compiler.node.evaluate_compiled_expression",
        lambda **kwargs: (
            kwargs["structured_answer"],
            "",
            [],
            [],
        ),
    )

    def fake_request_planner(state):
        requirement = state.get("user_requirement", "")

        if "rename existing attribute poAttributes" in requirement:
            return {
                "plan": {
                    "operation_type": "rename_attribute",
                    "template_phrase": "Prepaid Base Plan ECM request",
                    "external_system": "ECM",
                    "attribute_name": "poAttributes",
                    "new_attribute_name": "poAttributeList",
                    "rhs_request": "",
                }
            }

        if "append Sample to poAttributes" in requirement:
            return {
                "plan": {
                    "operation_type": "append_attribute_value",
                    "template_phrase": "Prepaid Base Plan ECM request",
                    "external_system": "ECM",
                    "attribute_name": "poAttributes",
                    "container_attribute_name": "poAttributes",
                    "append_key": "ccat_sample_value",
                    "rhs_request": "value Sample",
                }
            }

        if "AddToBillFlagCopy" in requirement and "add a new attribute" in requirement.lower():
            return {
                "plan": {
                    "operation_type": "add_attribute",
                    "template_phrase": "Prepaid Base Plan RTF request",
                    "external_system": "RTF",
                    "attribute_name": "AddToBillFlagCopy",
                    "new_attribute_name": "AddToBillFlagCopy",
                    "rhs_request": "If addToBill is false set false, otherwise true.",
                }
            }

        if "change POType" in requirement:
            return {
                "plan": {
                    "operation_type": "update_attribute_value",
                    "template_phrase": "Prepaid STK Notify Store request",
                    "external_system": "",
                    "attribute_name": "POType",
                    "new_attribute_name": "POType",
                    "rhs_request": "Base Plan",
                }
            }

        if "Nonexistent Acme Widget Template 9999" in requirement:
            return {
                "plan": {
                    "operation_type": "add_attribute",
                    "template_phrase": "Nonexistent Acme Widget Template 9999 request",
                    "external_system": "",
                    "attribute_name": "AddToBillFlagCopy",
                    "new_attribute_name": "AddToBillFlagCopy",
                    "rhs_request": "If addToBill is false set false, otherwise true.",
                }
            }

        raise AssertionError(f"Unexpected e2e requirement: {requirement}")

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.graph.builder.request_planner_node",
        fake_request_planner,
    )

    graph = build_advisor_graph()
    yield graph
    get_advisor_graph.cache_clear()


@pytest.mark.parametrize(
    ("requirement", "expect"),
    [
        (
            "For Prepaid Base Plan ECM request, rename existing attribute poAttributes to poAttributeList.",
            {
                "operation_type": "rename_attribute",
                "template_id": "MT_ECM_PRE_BASEPLAN",
                "can_execute": True,
                "sql_contains": "SET ATTRIBUTE_NAME = 'poAttributeList'",
            },
        ),
        (
            "For Prepaid Base Plan ECM request, append Sample to poAttributes key ccat_sample_value.",
            {
                "operation_type": "append_attribute_value",
                "template_id": "MT_ECM_PRE_BASEPLAN",
                "compiled_rhs": "VAL_Sample",
                "append_fragment": "ccat_sample_value=VAL_Sample;",
                "can_execute": True,
            },
        ),
        (
            "For Prepaid Base Plan RTF request, add a new attribute AddToBillFlagCopy. If addToBill is false set false, otherwise true.",
            {
                "operation_type": "add_attribute",
                "template_id": "MT_RTF_PREPAID_PLAN",
                "compiled_rhs": "addToBill#false|false,ELSE|true",
                "can_execute": False,
                "sql_contains": "DRAFT ONLY",
            },
        ),
        (
            "For Prepaid STK Notify Store request, change POType from Add-on to Base Plan.",
            {
                "operation_type": "update_attribute_value",
                "template_id": "MT_PREPAID_STK_NOTIFY_STORE",
                "compiled_rhs": "VAL_Base Plan",
                "can_execute": True,
            },
        ),
        (
            "For Nonexistent Acme Widget Template 9999 request, add AddToBillFlagCopy with addToBill false as false and true as true.",
            {
                "operation_type": "add_attribute",
                "template_resolved": False,
                "can_execute": False,
            },
        ),
    ],
    ids=[
        "rename_attribute",
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
        "unresolved_template",
    ],
)
def test_advisor_e2e_operation_types(e2e_graph, requirement, expect):
    import anyio

    async def run_graph():
        return await e2e_graph.ainvoke(
            {
                "user_requirement": requirement,
                "warnings": [],
                "errors": [],
                "debug": {},
            }
        )

    final_state = anyio.run(run_graph)

    plan = final_state.get("plan", {})
    template = final_state.get("template", {})
    sql = final_state.get("sql", {})
    expression = final_state.get("expression", {})
    debug = final_state.get("debug", {})

    assert plan.get("operation_type") == expect["operation_type"]

    if expect.get("template_resolved") is False:
        assert template.get("is_resolved") is False
        assert final_state.get("oracle", {}) == {}
        assert not final_state.get("expression")
    else:
        assert template.get("is_resolved") is True
        assert template.get("template_id") == expect["template_id"]
        if expect["operation_type"] == "add_attribute":
            assert final_state.get("oracle", {}).get("exists") is False
        else:
            assert final_state.get("oracle", {}).get("exists") is True

    if expect.get("compiled_rhs"):
        assert expression.get("compiled_rhs") == expect["compiled_rhs"]

    if expect.get("append_fragment"):
        assert expression.get("append_fragment") == expect["append_fragment"]

    assert sql.get("can_execute") is expect["can_execute"]

    if expect.get("sql_contains"):
        assert expect["sql_contains"] in (sql.get("recommended_sql") or "")

    timings = debug.get("timings") or []
    if expect.get("template_resolved") is False:
        expected_nodes = {
            "request_planner",
            "template_resolution",
            "sql_generation",
            "final_response",
        }
    else:
        expected_nodes = {
            "request_planner",
            "template_resolution",
            "oracle_inspection",
            "dsl_expression",
            "sql_generation",
            "final_response",
        }

    assert {entry["node"] for entry in timings} >= expected_nodes
