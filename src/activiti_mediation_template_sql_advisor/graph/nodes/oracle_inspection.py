from __future__ import annotations

import re
from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState
from activiti_mediation_template_sql_advisor.mcp_client.shared_client import (
    OracleMCPClientManager,
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


def _preview(value: str, max_length: int = 800) -> str:
    value = value or ""

    if len(value) <= max_length:
        return value

    return value[:max_length] + "..."


def _build_sample_parameters(
    rows: list[dict[str, Any]],
    focus_attribute_name: str = "",
    max_samples: int = 12,
) -> list[dict[str, Any]]:
    """
    Build small Oracle examples for DSL pattern matching.

    These are syntax evidence only:
    - VAL_ usage
    - mapping shape
    - $. prefix style
    - composite poAttributes style
    """
    focus = (focus_attribute_name or "").strip().lower()

    normalized_rows: list[dict[str, Any]] = []

    for row in rows or []:
        attribute_name = str(
            _get_any(
                row,
                "ATTRIBUTE_NAME",
                "attribute_name",
                default="",
            )
            or ""
        )

        attribute_value = str(
            _get_any(
                row,
                "ATTRIBUTE_VALUE",
                "attribute_value",
                default="",
            )
            or ""
        )

        if not attribute_name:
            continue

        normalized_rows.append(
            {
                "param_id": str(
                    _get_any(row, "PARAM_ID", "param_id", default="") or ""
                ),
                "attribute_name": attribute_name,
                "attribute_value_preview": _preview(attribute_value),
                "attribute_value_length": len(attribute_value),
                "is_focus_attribute": attribute_name.strip().lower() == focus,
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        value = str(item.get("attribute_value_preview", "") or "")

        has_dsl_signal = any(
            signal in value
            for signal in ["VAL_", "#", "|", "$", ";"]
        )

        return (
            0 if item.get("is_focus_attribute") else 1,
            0 if has_dsl_signal else 1,
        )

    normalized_rows.sort(key=sort_key)

    return normalized_rows[:max_samples]


def _target_attribute_name(state: AdvisorState) -> str:
    """
    Attribute row that must already exist for the operation.

    For append:
        existing container ATTRIBUTE_NAME, e.g. poAttributes

    For rename/update/delete:
        existing ATTRIBUTE_NAME

    For add:
        target ATTRIBUTE_NAME, but it must NOT already exist.
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
    - sample ATTRIBUTE_VALUE rows for DSL syntax pattern matching

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
            "sample_parameters": [],
            "sample_parameter_count": 0,
            "all_parameter_count": 0,
        }

        return {
            "oracle": oracle_result,
            "errors": list(state.get("errors", []) or []) + errors,
        }

    try:
        inspection = await OracleMCPClientManager.call_tool(
            "inspect_template_for_advisor",
            {
                "template_id": template_id,
                "attribute_name": attribute_name,
                "target_attribute_name": target_attribute_name,
                "focus_attribute_name": attribute_name,
                "sample_limit": 20,
            },
        )

        template_exists = _template_exists_from_response(
            inspection.get("template_exists", False)
        )
        template_row = inspection.get("template_row") or None
        parameter_row = inspection.get("parameter_row") or None
        target_parameter_row = inspection.get("target_parameter_row") or None
        all_parameters = inspection.get("sample_parameters") or []

        sample_parameters = _build_sample_parameters(
            rows=all_parameters,
            focus_attribute_name=attribute_name,
        )

        parameter_exists = parameter_row is not None
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

        if not template_exists:
            errors.append(
                f"Template '{template_id}' does not exist in ACT_MEDIATION_TEMPLATE."
            )

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

        if operation_type == "add_attribute":
            if parameter_exists:
                errors.append(
                    f"Cannot add attribute '{attribute_name}' because it already exists "
                    f"for template '{template_id}'."
                )
            else:
                warnings.append(
                    "Add attribute target does not currently exist. "
                    "SQL generation is still blocked until safe PARAM_ID generation is available."
                )

        if operation_type == "rename_attribute":
            if not target_attribute_name:
                errors.append("Rename target new_attribute_name is missing.")

            elif target_parameter_exists:
                errors.append(
                    f"Cannot rename '{attribute_name}' to '{target_attribute_name}' because "
                    f"'{target_attribute_name}' already exists for template '{template_id}'."
                )

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
            "template_exists": template_exists,
            "template_row": template_row or {},
            "parameter_row": parameter_row or {},
            "target_attribute_name": target_attribute_name,
            "target_exists": target_parameter_exists,
            "target_parameter_row": target_parameter_row or {},
            "sample_parameters": sample_parameters,
            "sample_parameter_count": len(sample_parameters),
            "all_parameter_count": int(inspection.get("all_parameter_count", 0)),
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
            "sample_parameters": [],
            "sample_parameter_count": 0,
            "all_parameter_count": 0,
        }

        return {
            "oracle": oracle_result,
            "errors": list(state.get("errors", []) or []) + [error],
        }