from __future__ import annotations

from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def _add_validation_error(
    updates: dict[str, Any],
    state: AdvisorState,
    message: str,
) -> None:
    validation_errors = list(state.get("validation_errors", []) or [])
    validation_errors.append(message)
    updates["validation_errors"] = validation_errors


def _append_warning(
    updates: dict[str, Any],
    state: AdvisorState,
    message: str,
) -> None:
    warnings = list(state.get("warnings", []) or [])
    warnings.append(message)
    updates["warnings"] = warnings


def _looks_like_key_value_fragment(value: str) -> bool:
    clean_value = (value or "").strip()
    return clean_value.endswith(";") and "=" in clean_value


def _starts_with_attribute_wrapper(value: str, attribute_name: str) -> bool:
    clean_value = (value or "").strip()
    clean_attribute = (attribute_name or "").strip()

    if not clean_value or not clean_attribute:
        return False

    without_semicolon = clean_value[:-1].strip() if clean_value.endswith(";") else clean_value

    return without_semicolon.lower().startswith(f"{clean_attribute.lower()}=")


def expression_assembler_node(state: AdvisorState) -> dict[str, Any]:
    """
    Deterministically assemble final expression shape.

    This node does not know expression syntax.
    It does not know VAL_, $LIST, $ALLTRUE_, $MAP_, etc.

    It only knows database operation shape:
    - append_attribute_value -> append_key=compiled_rhs;
    - add_attribute/update_attribute_value -> compiled_rhs
    """
    operation_type = state.get("operation_type", "unknown")
    compiled_rhs = str(state.get("compiled_rhs", "") or "").strip()

    updates: dict[str, Any] = {
        "expression_is_valid": False,
    }

    if operation_type not in {
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
    }:
        updates["expression_is_valid"] = True
        updates["assembled_expression"] = ""
        return updates

    if not state.get("rhs_compilation_did_compile"):
        message = "Expression assembly skipped because RHS compilation did not succeed."
        _append_warning(updates, state, message)
        updates["assembled_expression"] = ""
        return updates

    if not compiled_rhs:
        message = "Expression assembly failed because compiled_rhs is empty."
        _add_validation_error(updates, state, message)
        _append_warning(updates, state, message)
        updates["assembled_expression"] = ""
        return updates

    if operation_type == "append_attribute_value":
        append_key = str(state.get("append_key", "") or "").strip()
        target_attribute_name = str(
            state.get("target_attribute_name", "") or state.get("attribute_name", "") or ""
        ).strip()

        if not append_key:
            message = "Expression assembly failed because append_key is missing."
            _add_validation_error(updates, state, message)
            _append_warning(updates, state, message)
            updates["assembled_expression"] = ""
            updates["value_to_append"] = ""
            return updates

        if target_attribute_name and append_key.lower() == target_attribute_name.lower():
            message = (
                "Expression assembly failed because append_key is the same as the existing "
                "container ATTRIBUTE_NAME. The container belongs in SQL WHERE clause only."
            )
            _add_validation_error(updates, state, message)
            _append_warning(updates, state, message)
            updates["assembled_expression"] = ""
            updates["value_to_append"] = ""
            return updates

        if _starts_with_attribute_wrapper(compiled_rhs, append_key):
            message = (
                "Expression assembly failed because compiled_rhs is already wrapped as "
                "append_key=value. RHS compiler must return RHS only."
            )
            _add_validation_error(updates, state, message)
            _append_warning(updates, state, message)
            updates["assembled_expression"] = ""
            updates["value_to_append"] = ""
            return updates

        assembled = f"{append_key}={compiled_rhs};"

        updates["value_to_append"] = assembled
        updates["new_attribute_value"] = ""
        updates["assembled_expression"] = assembled
        updates["expression_is_valid"] = True

        return updates

    if operation_type in {"add_attribute", "update_attribute_value"}:
        attribute_name = str(
            state.get("new_attribute_name", "")
            or state.get("target_attribute_name", "")
            or state.get("attribute_name", "")
            or ""
        ).strip()

        if operation_type == "add_attribute" and _starts_with_attribute_wrapper(
            compiled_rhs,
            attribute_name,
        ):
            message = (
                "Expression assembly failed because add_attribute compiled_rhs looks like "
                "'ATTRIBUTE_NAME=value;'. For add_attribute, ATTRIBUTE_NAME is stored in "
                "the database column and ATTRIBUTE_VALUE must contain RHS only."
            )
            _add_validation_error(updates, state, message)
            _append_warning(updates, state, message)
            updates["assembled_expression"] = ""
            updates["new_attribute_value"] = ""
            return updates

        if operation_type == "add_attribute" and _looks_like_key_value_fragment(compiled_rhs):
            message = (
                "Expression assembly failed because add_attribute compiled_rhs looks like "
                "an append fragment. Add attribute requires RHS only."
            )
            _add_validation_error(updates, state, message)
            _append_warning(updates, state, message)
            updates["assembled_expression"] = ""
            updates["new_attribute_value"] = ""
            return updates

        updates["new_attribute_value"] = compiled_rhs
        updates["value_to_append"] = ""
        updates["assembled_expression"] = compiled_rhs
        updates["expression_is_valid"] = True

        return updates

    return updates