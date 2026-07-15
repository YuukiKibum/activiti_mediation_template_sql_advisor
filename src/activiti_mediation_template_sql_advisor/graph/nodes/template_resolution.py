from __future__ import annotations

from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import (
    AdvisorState,
    append_error,
    append_warning,
)
from activiti_mediation_template_sql_advisor.template_registry.resolver import (
    resolve_template_from_plan,
)


def template_resolution_node(state: AdvisorState) -> dict[str, Any]:
    plan = state.get("plan", {}) or {}

    user_requirement = state.get("user_requirement", "")
    template_phrase = str(plan.get("template_phrase", "") or "")
    requested_external_system = str(plan.get("external_system", "") or "")

    try:
        result = resolve_template_from_plan(
            user_requirement=user_requirement,
            template_phrase=template_phrase,
            external_system=requested_external_system,
        )

        graph_result = result.to_graph_dict()

        updates: dict[str, Any] = {
            "template": graph_result,
        }

        if not result.is_resolved:
            updates["warnings"] = append_warning(
                state,
                f"Template resolution failed: {result.reason}",
            )

        return updates

    except Exception as exc:
        error = f"template_resolution_node failed: {exc}"

        return {
            "template": {
                "template_id": "",
                "external_system": requested_external_system,
                "match_type": "error",
                "matched_text": "",
                "score": 0.0,
                "reason": error,
                "is_resolved": False,
            },
            "errors": append_error(state, error),
        }
