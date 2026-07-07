from __future__ import annotations

import re
from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.mcp_client.oracle_mcp_client import (
    OracleMCPClient,
)


def _get_any(row: dict[str, Any] | None, *keys: str, default: Any = "") -> Any:
    """
    Read a value from a dict using multiple possible key styles.

    Oracle/MCP responses may return uppercase DB column names like ATTRIBUTE_VALUE,
    or lowercase/pythonic names like attribute_value.
    """
    if not row:
        return default

    for key in keys:
        if key in row and row[key] is not None:
            return row[key]

    lowered = {str(key).lower(): value for key, value in row.items()}

    for key in keys:
        lowered_key = key.lower()

        if lowered_key in lowered and lowered[lowered_key] is not None:
            return lowered[lowered_key]

    return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    if isinstance(value, (int, float)):
        return value != 0

    text = str(value).strip().lower()

    return text in {"true", "yes", "y", "1", "exists", "found"}


def _template_exists_from_response(response: Any) -> bool:
    """
    Support multiple possible MCP shapes.

    Examples:
        {"exists": true}
        {"template_exists": true}
        {"count": 1}
        {"result": {"exists": true}}
    """
    if response is None:
        return False

    if isinstance(response, bool):
        return response

    if not isinstance(response, dict):
        return _as_bool(response)

    if "result" in response and isinstance(response["result"], dict):
        return _template_exists_from_response(response["result"])

    for key in [
        "exists",
        "template_exists",
        "is_exists",
        "found",
        "is_found",
    ]:
        if key in response:
            return _as_bool(response[key])

    for key in ["count", "row_count", "total"]:
        if key in response:
            try:
                return int(response[key]) > 0
            except Exception:
                return False

    # If the server returned a template row itself, treat non-empty dict as found.
    return bool(response)


def _append_key_exists_in_current_value(current_value: str, append_key: str) -> bool:
    """
    Detect whether append_key already exists inside semicolon-separated ATTRIBUTE_VALUE.

    Example:
        current_value = "Color=VAL_Red;CustomerType=VAL_X;"
        append_key = "CustomerType"

    Returns True.
    """
    current_value = current_value or ""
    append_key = (append_key or "").strip()

    if not current_value or not append_key:
        return False

    pattern = rf"(^|;)\s*{re.escape(append_key)}\s*="

    return re.search(pattern, current_value, flags=re.IGNORECASE) is not None


def _target_attribute_name(state: AdvisorState) -> str:
    """
    Attribute row that must already exist for the operation.

    For append:
        existing container ATTRIBUTE_NAME, e.g. poAttributes

    For rename/update/delete:
        existing ATTRIBUTE_NAME

    For add:
        target ATTRIBUTE_NAME, but it must NOT already exist.
        We still return attribute_name here for inspection display.
    """
    plan = state.get("plan", {}) or {}
    operation_type = str(plan.get("operation_type", "") or "")

    if operation_type == "append_attribute_value":
        return str(
            plan.get("container_attribute_name")
            or plan.get("attribute_name")
            or ""
        ).strip()

    if operation_type == "add_attribute":
        return str(
            plan.get("new_attribute_name")
            or plan.get("attribute_name")
            or ""
        ).strip()

    return str(plan.get("attribute_name") or "").strip()


def _target_new_attribute_name(state: AdvisorState) -> str:
    """
    Attribute row that must NOT already exist.

    Used for:
    - rename_attribute: new ATTRIBUTE_NAME
    - add_attribute: new ATTRIBUTE_NAME
    """
    plan = state.get("plan", {}) or {}
    operation_type = str(plan.get("operation_type", "") or "")

    if operation_type == "rename_attribute":
        return str(plan.get("new_attribute_name") or "").strip()

    if operation_type == "add_attribute":
        return str(
            plan.get("new_attribute_name")
            or plan.get("attribute_name")
            or ""
        ).strip()

    return ""


async def oracle_inspection_node(state: AdvisorState) -> dict[str, Any]:
    """
    Real Oracle inspection through MCP.

    This node is read-only.

    It checks:
    - whether TEMPLATE_ID exists in ACT_MEDIATION_TEMPLATE
    - whether ATTRIBUTE_NAME exists in ACT_MEDIATION_PARAMETER
    - current ATTRIBUTE_VALUE for rollback/safety
    - duplicate append key inside current ATTRIBUTE_VALUE for append operations
    - duplicate target ATTRIBUTE_NAME for rename/add operations

    It does NOT generate SQL.
    It does NOT execute DML.
    """
    template = state.get("template", {}) or {}
    plan = state.get("plan", {}) or {}

    template_id = str(template.get("template_id", "") or "").strip()
    operation_type = str(plan.get("operation_type", "") or "").strip()

    attribute_name = _target_attribute_name(state)
    target_attribute_name = _target_new_attribute_name(state)
    append_key = str(plan.get("append_key", "") or "").strip()

    warnings: list[str] = []
    errors: list[str] = []

    if not template_id:
        errors.append("Oracle inspection cannot run because template_id is missing.")

    if not operation_type or operation_type == "unknown":
        errors.append("Oracle inspection cannot run because operation_type is missing or unknown.")

    if not attribute_name and operation_type in {
        "append_attribute_value",
        "update_attribute_value",
        "rename_attribute",
        "delete_attribute",
        "add_attribute",
    }:
        errors.append("Oracle inspection cannot run because attribute_name is missing.")

    if operation_type == "rename_attribute" and not target_attribute_name:
        errors.append("Oracle inspection cannot run because new_attribute_name is missing.")

    if errors:
        oracle_result = {
            "can_generate_sql": False,
            "param_id": "",
            "template_id": template_id,
            "attribute_name": attribute_name,
            "current_attribute_value": "",
            "exists": False,
            "duplicate_append_key": False,
            "warnings": warnings,
            "errors": errors,
            "template_exists": False,
            "target_attribute_name": target_attribute_name,
            "target_exists": False,
            "target_parameter_row": {},
            "template_row": {},
            "parameter_row": {},
        }

        return {
            "oracle": oracle_result,
            "errors": list(state.get("errors", []) or []) + errors,
        }

    try:
        async with OracleMCPClient() as client:
            template_exists_response = await client.template_exists(template_id)
            template_exists = _template_exists_from_response(template_exists_response)

            template_row: dict[str, Any] | None = None

            if template_exists:
                template_row = await client.get_template(template_id)

            parameter_row: dict[str, Any] | None = None

            if attribute_name:
                parameter_row = await client.get_parameter(
                    template_id=template_id,
                    attribute_name=attribute_name,
                )

            parameter_exists = parameter_row is not None

            target_parameter_row: dict[str, Any] | None = None

            if target_attribute_name:
                target_parameter_row = await client.get_parameter(
                    template_id=template_id,
                    attribute_name=target_attribute_name,
                )

            target_parameter_exists = target_parameter_row is not None

            param_id = str(
                _get_any(
                    parameter_row,
                    "PARAM_ID",
                    "param_id",
                    "ID",
                    "id",
                    default="",
                )
                or ""
            )

            current_attribute_value = str(
                _get_any(
                    parameter_row,
                    "ATTRIBUTE_VALUE",
                    "attribute_value",
                    "VALUE",
                    "value",
                    default="",
                )
                or ""
            )

            duplicate_append_key = False

            if operation_type == "append_attribute_value":
                duplicate_append_key = _append_key_exists_in_current_value(
                    current_value=current_attribute_value,
                    append_key=append_key,
                )

            # Template must exist for every operation.
            if not template_exists:
                errors.append(
                    f"Template '{template_id}' does not exist in ACT_MEDIATION_TEMPLATE."
                )

            # Existing attribute must exist for these operations.
            if operation_type in {
                "append_attribute_value",
                "update_attribute_value",
                "rename_attribute",
                "delete_attribute",
            } and not parameter_exists:
                errors.append(
                    f"Attribute '{attribute_name}' does not exist for template '{template_id}' "
                    "in ACT_MEDIATION_PARAMETER."
                )

            # Add operation target must NOT already exist.
            if operation_type == "add_attribute":
                if parameter_exists:
                    errors.append(
                        f"Cannot add attribute '{attribute_name}' because it already exists "
                        f"for template '{template_id}'."
                    )
                else:
                    warnings.append(
                        "Add attribute target does not currently exist. "
                        "SQL generation may still require PARAM_ID/order rules before insert can be safe."
                    )

            # Rename operation target must NOT already exist.
            if operation_type == "rename_attribute":
                if not target_attribute_name:
                    errors.append("Rename target new_attribute_name is missing.")

                elif target_parameter_exists:
                    errors.append(
                        f"Cannot rename '{attribute_name}' to '{target_attribute_name}' because "
                        f"'{target_attribute_name}' already exists for template '{template_id}'."
                    )

            # Append operation key must NOT already exist inside current ATTRIBUTE_VALUE.
            if operation_type == "append_attribute_value":
                if not append_key:
                    errors.append("Append key is missing.")

                elif duplicate_append_key:
                    errors.append(
                        f"Append key '{append_key}' already exists inside ATTRIBUTE_VALUE "
                        f"for attribute '{attribute_name}'."
                    )

            can_generate_sql = not errors

            oracle_result = {
                "can_generate_sql": can_generate_sql,
                "param_id": param_id,
                "template_id": template_id,
                "attribute_name": attribute_name,
                "current_attribute_value": current_attribute_value,
                "exists": parameter_exists,
                "duplicate_append_key": duplicate_append_key,
                "warnings": warnings,
                "errors": errors,
                # Extra debug-safe fields.
                "template_exists": template_exists,
                "template_row": template_row or {},
                "parameter_row": parameter_row or {},
                "target_attribute_name": target_attribute_name,
                "target_exists": target_parameter_exists,
                "target_parameter_row": target_parameter_row or {},
            }

            updates: dict[str, Any] = {
                "oracle": oracle_result,
            }

            if warnings:
                updates["warnings"] = list(state.get("warnings", []) or []) + warnings

            if errors:
                updates["errors"] = list(state.get("errors", []) or []) + errors

            return updates

    except Exception as exc:
        error = f"oracle_inspection_node failed while calling MCP: {exc}"

        oracle_result = {
            "can_generate_sql": False,
            "param_id": "",
            "template_id": template_id,
            "attribute_name": attribute_name,
            "current_attribute_value": "",
            "exists": False,
            "duplicate_append_key": False,
            "warnings": warnings,
            "errors": [error],
            "template_exists": False,
            "target_attribute_name": target_attribute_name,
            "target_exists": False,
            "target_parameter_row": {},
            "template_row": {},
            "parameter_row": {},
        }

        return {
            "oracle": oracle_result,
            "errors": list(state.get("errors", []) or []) + [error],
        }