from __future__ import annotations

import pytest

from activiti_mediation_template_sql_advisor.graph.telemetry import timed_node


def test_timed_node_records_success_timing():
    def sample_impl(state):
        return {"value": 1}

    sample_node = timed_node("sample_node", sample_impl)

    result = sample_node(
        {"debug": {"timings": [{"node": "prior", "elapsed_ms": 1.0, "status": "ok"}]}}
    )

    timings = result["debug"]["timings"]
    assert timings[0]["node"] == "prior"
    assert timings[-1]["node"] == "sample_node"
    assert timings[-1]["status"] == "ok"
    assert timings[-1]["elapsed_ms"] >= 0


def test_timed_node_records_failure_telemetry():
    def failing_impl(state):
        raise ValueError("boom")

    failing_node = timed_node("failing_node", failing_impl)

    with pytest.raises(ValueError, match="boom"):
        failing_node({"debug": {}})


@pytest.fixture
def graph_with_fake_planner(monkeypatch):
    from activiti_mediation_template_sql_advisor.graph.builder import (
        build_advisor_graph,
        get_advisor_graph,
    )

    get_advisor_graph.cache_clear()

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.graph.builder.request_planner_node",
        lambda state: {
            "plan": {
                "operation_type": "unknown",
                "template_phrase": "Prepaid Base Plan ECM request",
                "external_system": "ECM",
                "attribute_name": "",
                "new_attribute_name": "",
                "rhs_request": "",
            }
        },
    )

    async def fake_oracle_inspection(state):
        return {"oracle": {"exists": False}}

    monkeypatch.setattr(
        "activiti_mediation_template_sql_advisor.graph.nodes.oracle_inspection.oracle_inspection_node",
        fake_oracle_inspection,
    )

    graph = build_advisor_graph()
    yield graph
    get_advisor_graph.cache_clear()


def test_graph_records_per_node_timings(graph_with_fake_planner):
    import anyio

    async def run_graph():
        return await graph_with_fake_planner.ainvoke(
            {
                "user_requirement": "For Prepaid Base Plan ECM request, noop.",
                "warnings": [],
                "errors": [],
                "debug": {},
            }
        )

    final_state = anyio.run(run_graph)

    timings = final_state.get("debug", {}).get("timings") or []
    node_names = [entry["node"] for entry in timings]

    assert node_names == [
        "request_planner",
        "template_resolution",
        "oracle_inspection",
        "dsl_expression",
        "sql_generation",
        "final_response",
    ]

    assert all(entry["status"] == "ok" for entry in timings)
    assert all(entry["elapsed_ms"] >= 0 for entry in timings)
