from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


AUDIT_USER = "AI_SQL_ADVISOR"


def _sql_string(value: str) -> str:
    """
    Convert a Python string into a safe Oracle SQL string literal.

    Example:
        Bob's plan -> 'Bob''s plan'
    """
    escaped = (value or "").replace("'", "''")
    return f"'{escaped}'"


def _to_clob_expression(value: str, chunk_size: int = 3000) -> str:
    """
    Convert a Python string into an Oracle-safe CLOB expression.

    Why not just use one string literal?
    Oracle SQL string literals have size limits. ATTRIBUTE_VALUE is a CLOB and
    may be long, so we split the value into smaller TO_CLOB('...') chunks.

    Example:
        TO_CLOB('part1') || TO_CLOB('part2')
    """
    value = value or ""

    if value == "":
        return "TO_CLOB('')"

    chunks = [
        value[index : index + chunk_size]
        for index in range(0, len(value), chunk_size)
    ]

    return " || ".join(
        f"TO_CLOB({_sql_string(chunk)})"
        for chunk in chunks
    )


def _where_template_attribute(template_id: str, attribute_name: str) -> str:
    """
    Common WHERE clause for ACT_MEDIATION_PARAMETER by template and attribute.
    """
    return (
        f"TEMPLATE_ID = {_sql_string(template_id)} "
        f"AND ATTRIBUTE_NAME = {_sql_string(attribute_name)}"
    )


def _precheck_sql(template_id: str, attribute_name: str) -> str:
    """
    SQL to verify the current row before running the change.
    """
    return (
        "SELECT PARAM_ID, TEMPLATE_ID, ATTRIBUTE_NAME, ATTRIBUTE_VALUE\n"
        "FROM ACT_MEDIATION_PARAMETER\n"
        f"WHERE {_where_template_attribute(template_id, attribute_name)};"
    )


def _target_name_precheck_sql(template_id: str, new_attribute_name: str) -> str:
    """
    SQL to verify that the rename target does not already exist.
    """
    return (
        "SELECT PARAM_ID, TEMPLATE_ID, ATTRIBUTE_NAME\n"
        "FROM ACT_MEDIATION_PARAMETER\n"
        f"WHERE {_where_template_attribute(template_id, new_attribute_name)};"
    )


def _generate_rename_attribute_sql(state: AdvisorState) -> tuple[list[str], list[str]]:
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    new_attribute_name = state.get("new_attribute_name", "").strip()

    generated_sql = [
        "-- Pre-check: source attribute should exist",
        _precheck_sql(template_id, attribute_name),
        "-- Pre-check: target attribute should not already exist",
        _target_name_precheck_sql(template_id, new_attribute_name),
        "-- Change: rename ATTRIBUTE_NAME",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_NAME = {_sql_string(new_attribute_name)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    rollback_sql = [
        "-- Rollback: restore old ATTRIBUTE_NAME",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_NAME = {_sql_string(attribute_name)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, new_attribute_name)};"
        ),
        "COMMIT;",
    ]

    return generated_sql, rollback_sql


def _generate_append_attribute_value_sql(
    state: AdvisorState,
) -> tuple[list[str], list[str]]:
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    value_to_append = state.get("value_to_append", "")
    current_parameter = state.get("current_parameter") or {}
    current_value = str(current_parameter.get("attribute_value") or "")

    generated_sql = [
        "-- Pre-check: current attribute value",
        _precheck_sql(template_id, attribute_name),
        "-- Change: append fragment to ATTRIBUTE_VALUE",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_VALUE = ATTRIBUTE_VALUE || {_to_clob_expression(value_to_append)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    rollback_sql = [
        "-- Rollback: restore original ATTRIBUTE_VALUE",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_VALUE = {_to_clob_expression(current_value)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    return generated_sql, rollback_sql


def _generate_update_attribute_value_sql(
    state: AdvisorState,
) -> tuple[list[str], list[str]]:
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    new_attribute_value = state.get("new_attribute_value", "")
    current_parameter = state.get("current_parameter") or {}
    current_value = str(current_parameter.get("attribute_value") or "")

    generated_sql = [
        "-- Pre-check: current attribute value",
        _precheck_sql(template_id, attribute_name),
        "-- Change: replace ATTRIBUTE_VALUE",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_VALUE = {_to_clob_expression(new_attribute_value)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    rollback_sql = [
        "-- Rollback: restore original ATTRIBUTE_VALUE",
        (
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            f"SET ATTRIBUTE_VALUE = {_to_clob_expression(current_value)},\n"
            f"    MODIFIED_USER_ID = {_sql_string(AUDIT_USER)},\n"
            "    MODIFIED_DATE = SYSTIMESTAMP\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    return generated_sql, rollback_sql


def _generate_add_attribute_sql(state: AdvisorState) -> tuple[list[str], list[str]]:
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    new_attribute_value = state.get("new_attribute_value", "")

    generated_sql = [
        "-- Pre-check: attribute should not already exist",
        _precheck_sql(template_id, attribute_name),
        "-- Change: insert new ACT_MEDIATION_PARAMETER row",
        (
            "INSERT INTO ACT_MEDIATION_PARAMETER (\n"
            "    PARAM_ID,\n"
            "    TEMPLATE_ID,\n"
            "    ATTRIBUTE_NAME,\n"
            "    CREATED_USER_ID,\n"
            "    MODIFIED_USER_ID,\n"
            "    CREATED_DATE,\n"
            "    MODIFIED_DATE,\n"
            "    ATTRIBUTE_VALUE\n"
            ")\n"
            "VALUES (\n"
            "    (SELECT NVL(MAX(PARAM_ID), 0) + 1 FROM ACT_MEDIATION_PARAMETER),\n"
            f"    {_sql_string(template_id)},\n"
            f"    {_sql_string(attribute_name)},\n"
            f"    {_sql_string(AUDIT_USER)},\n"
            f"    {_sql_string(AUDIT_USER)},\n"
            "    SYSTIMESTAMP,\n"
            "    SYSTIMESTAMP,\n"
            f"    {_to_clob_expression(new_attribute_value)}\n"
            ");"
        ),
        "COMMIT;",
    ]

    rollback_sql = [
        "-- Rollback: delete newly inserted attribute",
        (
            "DELETE FROM ACT_MEDIATION_PARAMETER\n"
            f"WHERE {_where_template_attribute(template_id, attribute_name)};"
        ),
        "COMMIT;",
    ]

    return generated_sql, rollback_sql


def _validate_required_fields(state: AdvisorState) -> list[str]:
    """
    Validate that the planner and oracle inspection produced enough information
    for SQL generation.
    """
    operation_type = state.get("operation_type", "unknown")
    template_id = state.get("template_id", "").strip()
    attribute_name = state.get("attribute_name", "").strip()
    new_attribute_name = state.get("new_attribute_name", "").strip()
    new_attribute_value = state.get("new_attribute_value", "")
    value_to_append = state.get("value_to_append", "")

    errors: list[str] = []

    if operation_type == "unknown":
        errors.append("Cannot generate SQL because operation_type is unknown.")

    if not template_id:
        errors.append("Cannot generate SQL because TEMPLATE_ID is missing.")

    if operation_type in {
        "rename_attribute",
        "append_attribute_value",
        "update_attribute_value",
        "add_attribute",
    } and not attribute_name:
        errors.append("Cannot generate SQL because ATTRIBUTE_NAME is missing.")

    if operation_type == "rename_attribute" and not new_attribute_name:
        errors.append(
            "Cannot generate SQL because new ATTRIBUTE_NAME is missing."
        )

    if operation_type == "append_attribute_value" and not value_to_append:
        errors.append(
            "Cannot generate SQL because value_to_append is missing."
        )

    if operation_type in {"update_attribute_value", "add_attribute"} and not new_attribute_value:
        errors.append(
            "Cannot generate SQL because new ATTRIBUTE_VALUE is missing."
        )

    return errors


def sql_generation_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: generate SQL recommendation and rollback SQL.

    Reads:
        operation_type
        template_id
        attribute_name
        new_attribute_name
        new_attribute_value
        value_to_append
        current_parameter
        validation_errors

    Writes:
        generated_sql
        rollback_sql
        warnings
        validation_errors

    Important:
        This node only generates SQL text.
        It does not execute SQL.
    """
    validation_errors = list(state.get("validation_errors", []))
    warnings = list(state.get("warnings", []))

    if validation_errors:
        return {
            "generated_sql": [],
            "rollback_sql": [],
            "warnings": warnings,
            "validation_errors": validation_errors,
        }

    validation_errors.extend(_validate_required_fields(state))

    if validation_errors:
        return {
            "generated_sql": [],
            "rollback_sql": [],
            "warnings": warnings,
            "validation_errors": validation_errors,
        }

    operation_type = state.get("operation_type", "unknown")

    if operation_type == "rename_attribute":
        generated_sql, rollback_sql = _generate_rename_attribute_sql(state)

    elif operation_type == "append_attribute_value":
        generated_sql, rollback_sql = _generate_append_attribute_value_sql(state)

    elif operation_type == "update_attribute_value":
        generated_sql, rollback_sql = _generate_update_attribute_value_sql(state)

    elif operation_type == "add_attribute":
        generated_sql, rollback_sql = _generate_add_attribute_sql(state)

    else:
        validation_errors.append(
            f"Unsupported operation_type for SQL generation: {operation_type}"
        )
        generated_sql = []
        rollback_sql = []

    warnings.append(
        "Generated SQL is advisory only. Review and run manually in Oracle."
    )

    if operation_type == "add_attribute":
        warnings.append(
            "PARAM_ID is generated using MAX(PARAM_ID) + 1 because no sequence "
            "is currently configured in the project metadata. Replace with the "
            "correct Oracle sequence if one exists in the real environment."
        )

    return {
        "generated_sql": generated_sql,
        "rollback_sql": rollback_sql,
        "warnings": warnings,
        "validation_errors": validation_errors,
    }


if __name__ == "__main__":
    test_state: AdvisorState = {
        "operation_type": "rename_attribute",
        "template_id": "MT_ECM_PRE_BASEPLAN",
        "attribute_name": "poAttributes",
        "new_attribute_name": "poAttributeList",
        "current_parameter": {
            "attribute_value": "sample=current;value=old;"
        },
        "warnings": [],
        "validation_errors": [],
    }

    result = sql_generation_node(test_state)

    print("Generated SQL:")
    for statement in result["generated_sql"]:
        print(statement)
        print()

    print("=" * 80)

    print("Rollback SQL:")
    for statement in result["rollback_sql"]:
        print(statement)
        print()

    print("Warnings:", result["warnings"])
    print("Validation errors:", result["validation_errors"])