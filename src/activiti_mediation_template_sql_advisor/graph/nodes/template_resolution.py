from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.template_registry.resolver import (
    resolve_template,
)


def template_resolution_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: resolve business/user language into an exact TEMPLATE_ID.

    Reads:
        user_requirement
        template_id

    Writes:
        template_id
        template_external_system
        template_resolution_matched_text
        template_resolution_match_type
        template_resolution_score
        template_resolution_reason
        warnings
        validation_errors

    Why this node exists:
        The planner may extract a TEMPLATE_ID when the user gives one directly.

        But users may also say:
            "Prepaid Base Plan ECM request"

        This node maps that business phrase to:
            MT_ECM_PRE_BASEPLAN

        using data/template_registry/template_registry.yaml.
    """
    user_requirement = state.get("user_requirement", "").strip()
    planner_template_id = state.get("template_id", "").strip()

    warnings = list(state.get("warnings", []))
    validation_errors = list(state.get("validation_errors", []))

    resolution = resolve_template(user_requirement)

    updates: dict[str, Any] = {
        "template_external_system": resolution.external_system,
        "template_resolution_matched_text": resolution.matched_text,
        "template_resolution_match_type": resolution.match_type,
        "template_resolution_score": resolution.score,
        "template_resolution_reason": resolution.reason,
        "warnings": warnings,
        "validation_errors": validation_errors,
    }

    if resolution.match_type != "not_found":
        if planner_template_id and planner_template_id != resolution.template_id:
            warnings.append(
                "Planner TEMPLATE_ID differed from template registry resolution. "
                f"Planner gave '{planner_template_id}', registry resolved "
                f"'{resolution.template_id}'. Using registry result."
            )

        updates["template_id"] = resolution.template_id

        return updates

    if planner_template_id:
        warnings.append(
            "Template registry did not resolve the requirement, but planner extracted "
            f"TEMPLATE_ID '{planner_template_id}'. Oracle inspection will verify it."
        )

        updates["template_id"] = planner_template_id

        return updates

    validation_errors.append(
        "Could not resolve TEMPLATE_ID from the template registry. "
        "Add the correct TEMPLATE_ID or alias to data/template_registry/template_registry.yaml."
    )

    return updates


if __name__ == "__main__":
    examples = [
        {
            "user_requirement": (
                "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"
            ),
            "template_id": "MT_ECM_PRE_BASEPLAN",
            "warnings": [],
            "validation_errors": [],
        },
        {
            "user_requirement": (
                "For Prepaid Base Plan ECM request, rename existing attribute "
                "poAttributes to poAttributeList."
            ),
            "template_id": "",
            "warnings": [],
            "validation_errors": [],
        },
        {
            "user_requirement": (
                "For Prepaid Base Plan XYZ request, add AddToBillFlagCopy."
            ),
            "template_id": "",
            "warnings": [],
            "validation_errors": [],
        },
    ]

    for example in examples:
        result = template_resolution_node(example)

        print("=" * 100)
        print("Input:", example["user_requirement"])
        print("Result:", result)