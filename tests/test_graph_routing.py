from __future__ import annotations

from activiti_mediation_template_sql_advisor.graph.builder import (
    route_after_template_resolution,
)
from activiti_mediation_template_sql_advisor.graph.nodes.final_response import (
    final_response_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.sql_generation import (
    sql_generation_node,
)
from activiti_mediation_template_sql_advisor.graph.nodes.template_resolution import (
    template_resolution_node,
)


def test_route_after_template_resolution_when_resolved():
    state = {
        "template": {
            "template_id": "MT_ECM_PRE_BASEPLAN",
            "is_resolved": True,
        }
    }

    assert route_after_template_resolution(state) == "oracle_inspection"


def test_route_after_template_resolution_when_unresolved():
    state = {
        "template": {
            "template_id": "",
            "is_resolved": False,
        }
    }

    assert route_after_template_resolution(state) == "sql_generation"


def test_unresolved_template_short_circuit_produces_blocked_response():
    requirement = (
        "For Nonexistent Acme Widget Template 9999 request, "
        "add AddToBillFlagCopy with addToBill false as false and true as true."
    )

    state = {
        "user_requirement": requirement,
        "plan": {
            "operation_type": "add_attribute",
            "template_phrase": "Nonexistent Acme Widget Template 9999 request",
            "external_system": "",
            "attribute_name": "AddToBillFlagCopy",
            "new_attribute_name": "AddToBillFlagCopy",
            "rhs_request": "If addToBill is false set false, otherwise true.",
        },
        "warnings": [],
        "errors": [],
    }

    state.update(template_resolution_node(state))
    assert route_after_template_resolution(state) == "sql_generation"

    state.update(sql_generation_node(state))
    state.update(final_response_node(state))

    assert state["template"]["is_resolved"] is False
    assert state.get("oracle", {}) == {}
    assert state.get("expression", {}) == {}
    assert state["sql"]["can_execute"] is False
    assert "template_id is missing" in state["sql"]["reason"]
    assert "Not resolved" in state["final_answer"]
    assert state["errors"]
