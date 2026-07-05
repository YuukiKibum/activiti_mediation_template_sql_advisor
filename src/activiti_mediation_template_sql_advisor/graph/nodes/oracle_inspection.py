import asyncio
from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.mcp_client.oracle_mcp_client import (
    OracleMCPClient,
)


async def oracle_inspection_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: inspect current Oracle configuration through MCP.

    Reads:
        operation_type
        template_id
        attribute_name
        new_attribute_name

    Writes:
        template_exists
        current_template
        current_parameter
        related_parameters
        warnings
        validation_errors

    Important:
        This node does not directly connect to Oracle.
        It uses OracleMCPClient, which talks to the MCP server.
    """
    operation_type = state.get("operation_type", "unknown")
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    new_attribute_name = state.get("new_attribute_name", "").strip()

    warnings = list(state.get("warnings", []))
    validation_errors = list(state.get("validation_errors", []))

    if not template_id:
        validation_errors.append("TEMPLATE_ID is missing.")
        return {
            "template_exists": False,
            "current_template": None,
            "current_parameter": None,
            "related_parameters": [],
            "warnings": warnings,
            "validation_errors": validation_errors,
        }

    async with OracleMCPClient() as client:
        template_exists_result = await client.template_exists(template_id)
        template_exists = bool(template_exists_result.get("exists"))

        current_template = None
        current_parameter = None
        related_parameters: list[dict[str, Any]] = []

        if not template_exists:
            validation_errors.append(
                f"TEMPLATE_ID '{template_id}' does not exist in ACT_MEDIATION_TEMPLATE."
            )

            searched_templates = await client.search_templates(
                keyword=template_id,
                limit=10,
            )

            if searched_templates:
                related_parameters = searched_templates
                warnings.append(
                    "Similar templates were found, but the exact TEMPLATE_ID does not exist."
                )

            return {
                "template_exists": False,
                "current_template": None,
                "current_parameter": None,
                "related_parameters": related_parameters,
                "warnings": warnings,
                "validation_errors": validation_errors,
            }

        current_template = await client.get_template(template_id)

        if attribute_name:
            current_parameter = await client.get_parameter(
                template_id=template_id,
                attribute_name=attribute_name,
            )

        if operation_type in {
            "rename_attribute",
            "append_attribute_value",
            "update_attribute_value",
        }:
            if not attribute_name:
                validation_errors.append(
                    "ATTRIBUTE_NAME is required for this operation."
                )
            elif current_parameter is None:
                validation_errors.append(
                    f"ATTRIBUTE_NAME '{attribute_name}' does not exist for TEMPLATE_ID '{template_id}'."
                )

                related_parameters = await client.list_parameters_for_template(
                    template_id=template_id,
                    limit=50,
                )

                if related_parameters:
                    warnings.append(
                        f"Fetched existing parameters for TEMPLATE_ID '{template_id}' "
                        "to help identify the correct ATTRIBUTE_NAME."
                    )

        if operation_type == "rename_attribute":
            if not new_attribute_name:
                validation_errors.append(
                    "New ATTRIBUTE_NAME is required for rename_attribute operation."
                )
            else:
                existing_target_parameter = await client.get_parameter(
                    template_id=template_id,
                    attribute_name=new_attribute_name,
                )

                if existing_target_parameter is not None:
                    validation_errors.append(
                        f"Cannot rename '{attribute_name}' to '{new_attribute_name}' "
                        f"because '{new_attribute_name}' already exists for TEMPLATE_ID '{template_id}'."
                    )

        if operation_type == "add_attribute":
            if not attribute_name:
                validation_errors.append(
                    "ATTRIBUTE_NAME is required for add_attribute operation."
                )
            else:
                existing_parameter = await client.get_parameter(
                    template_id=template_id,
                    attribute_name=attribute_name,
                )

                if existing_parameter is not None:
                    validation_errors.append(
                        f"Cannot add ATTRIBUTE_NAME '{attribute_name}' because it already exists "
                        f"for TEMPLATE_ID '{template_id}'."
                    )

                    current_parameter = existing_parameter

        return {
            "template_exists": template_exists,
            "current_template": current_template,
            "current_parameter": current_parameter,
            "related_parameters": related_parameters,
            "warnings": warnings,
            "validation_errors": validation_errors,
        }


async def main() -> None:
    """
    Manual test for Oracle inspection node.

    Run with:
        uv run python -m activiti_mediation_template_sql_advisor.graph.nodes.oracle_inspection
    """
    test_state: AdvisorState = {
        "operation_type": "rename_attribute",
        "template_id": "MT_ECM_PRE_BASEPLAN",
        "attribute_name": "poAttributes",
        "new_attribute_name": "poAttributeList",
        "warnings": [],
        "validation_errors": [],
    }

    result = await oracle_inspection_node(test_state)

    print("Template exists:", result["template_exists"])
    print("Current template:", result["current_template"])
    print("Current parameter found:", result["current_parameter"] is not None)
    print("Related parameters:", len(result["related_parameters"]))
    print("Warnings:", result["warnings"])
    print("Validation errors:", result["validation_errors"])

    if result["current_parameter"]:
        print("Current parameter name:", result["current_parameter"]["attribute_name"])
        print(
            "Current value preview:",
            result["current_parameter"]["attribute_value"][:500],
        )


if __name__ == "__main__":
    asyncio.run(main())