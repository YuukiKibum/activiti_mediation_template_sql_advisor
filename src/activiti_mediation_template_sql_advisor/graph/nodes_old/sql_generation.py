from __future__ import annotations

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def _sql_literal(value: str) -> str:
    """
    Escape a Python string for use inside an Oracle SQL string literal.
    """
    return (value or "").replace("'", "''")


def _to_clob_expression(value: str, chunk_size: int = 3000) -> str:
    """
    Convert text into a safe Oracle CLOB expression.

    Why chunks?
    Oracle string literals can hit length limits. Splitting into TO_CLOB chunks
    is safer for long ATTRIBUTE_VALUE rollback SQL.

    Example:
        TO_CLOB('abc') || TO_CLOB('def')
    """
    value = value or ""

    if value == "":
        return "TO_CLOB('')"

    chunks = [
        value[index : index + chunk_size]
        for index in range(0, len(value), chunk_size)
    ]

    return " || ".join(
        f"TO_CLOB('{_sql_literal(chunk)}')" for chunk in chunks
    )


def _where_clause(
    *,
    template_id: str,
    attribute_name: str,
    param_id: str = "",
) -> str:
    """
    Prefer PARAM_ID when MCP provides it.
    Fall back to TEMPLATE_ID + ATTRIBUTE_NAME.
    """
    safe_template_id = _sql_literal(template_id)
    safe_attribute_name = _sql_literal(attribute_name)
    safe_param_id = _sql_literal(param_id)

    if safe_param_id:
        return f"""PARAM_ID = '{safe_param_id}'
  AND TEMPLATE_ID = '{safe_template_id}'
  AND ATTRIBUTE_NAME = '{safe_attribute_name}'"""

    return f"""TEMPLATE_ID = '{safe_template_id}'
  AND ATTRIBUTE_NAME = '{safe_attribute_name}'"""


def _generate_precheck_sql(
    *,
    template_id: str,
    attribute_name: str,
    param_id: str = "",
) -> str:
    where_clause = _where_clause(
        template_id=template_id,
        attribute_name=attribute_name,
        param_id=param_id,
    )

    return f"""SELECT PARAM_ID, TEMPLATE_ID, ATTRIBUTE_NAME, ATTRIBUTE_VALUE
FROM ACT_MEDIATION_PARAMETER
WHERE {where_clause};"""


def _generate_append_sql(
    *,
    template_id: str,
    attribute_name: str,
    append_fragment: str,
    current_attribute_value: str,
    param_id: str = "",
) -> tuple[str, str]:
    where_clause = _where_clause(
        template_id=template_id,
        attribute_name=attribute_name,
        param_id=param_id,
    )

    safe_append_fragment = _sql_literal(append_fragment)
    rollback_value_expr = _to_clob_expression(current_attribute_value)

    recommended_sql = f"""-- Pre-check: current attribute value
{_generate_precheck_sql(template_id=template_id, attribute_name=attribute_name, param_id=param_id)}

-- Change: append fragment to ATTRIBUTE_VALUE
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = ATTRIBUTE_VALUE || TO_CLOB('{safe_append_fragment}'),
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {where_clause};

COMMIT;"""

    rollback_sql = f"""-- Rollback: restore previous ATTRIBUTE_VALUE captured by MCP
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = {rollback_value_expr},
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR_ROLLBACK',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {where_clause};

COMMIT;"""

    return recommended_sql, rollback_sql


def _generate_update_value_sql(
    *,
    template_id: str,
    attribute_name: str,
    compiled_rhs: str,
    current_attribute_value: str,
    param_id: str = "",
) -> tuple[str, str]:
    where_clause = _where_clause(
        template_id=template_id,
        attribute_name=attribute_name,
        param_id=param_id,
    )

    new_value_expr = _to_clob_expression(compiled_rhs)
    rollback_value_expr = _to_clob_expression(current_attribute_value)

    recommended_sql = f"""-- Pre-check: current attribute value
{_generate_precheck_sql(template_id=template_id, attribute_name=attribute_name, param_id=param_id)}

-- Change: replace ATTRIBUTE_VALUE
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = {new_value_expr},
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {where_clause};

COMMIT;"""

    rollback_sql = f"""-- Rollback: restore previous ATTRIBUTE_VALUE captured by MCP
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_VALUE = {rollback_value_expr},
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR_ROLLBACK',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {where_clause};

COMMIT;"""

    return recommended_sql, rollback_sql


def _generate_rename_sql(
    *,
    template_id: str,
    old_attribute_name: str,
    new_attribute_name: str,
    param_id: str = "",
) -> tuple[str, str]:
    where_clause = _where_clause(
        template_id=template_id,
        attribute_name=old_attribute_name,
        param_id=param_id,
    )

    safe_template_id = _sql_literal(template_id)
    safe_old = _sql_literal(old_attribute_name)
    safe_new = _sql_literal(new_attribute_name)
    safe_param_id = _sql_literal(param_id)

    if safe_param_id:
        rollback_where_clause = f"""PARAM_ID = '{safe_param_id}'
  AND TEMPLATE_ID = '{safe_template_id}'
  AND ATTRIBUTE_NAME = '{safe_new}'"""
    else:
        rollback_where_clause = f"""TEMPLATE_ID = '{safe_template_id}'
  AND ATTRIBUTE_NAME = '{safe_new}'"""

    recommended_sql = f"""-- Pre-check: current attribute row
{_generate_precheck_sql(template_id=template_id, attribute_name=old_attribute_name, param_id=param_id)}

-- Change: rename ATTRIBUTE_NAME
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_NAME = '{safe_new}',
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {where_clause};

COMMIT;"""

    rollback_sql = f"""-- Rollback: rename ATTRIBUTE_NAME back
UPDATE ACT_MEDIATION_PARAMETER
SET ATTRIBUTE_NAME = '{safe_old}',
    MODIFIED_USER_ID = 'AI_SQL_ADVISOR_ROLLBACK',
    MODIFIED_DATE = SYSTIMESTAMP
WHERE {rollback_where_clause};

COMMIT;"""

    return recommended_sql, rollback_sql


def sql_generation_node(state: AdvisorState) -> dict:
    plan = state.get("plan", {}) or {}
    template = state.get("template", {}) or {}
    expression = state.get("expression", {}) or {}
    oracle = state.get("oracle", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    template_id = str(template.get("template_id", "") or "")

    param_id = str(oracle.get("param_id", "") or "")
    current_attribute_value = str(oracle.get("current_attribute_value", "") or "")

    warnings: list[str] = []
    errors: list[str] = []

    if not template_id:
        errors.append("SQL generation blocked because template_id is missing.")

    if oracle and not oracle.get("can_generate_sql", False):
        errors.append("SQL generation blocked because oracle.can_generate_sql is false.")

    recommended_sql = ""
    rollback_sql = ""

    try:
        if not errors and operation_type == "append_attribute_value":
            attribute_name = str(
                plan.get("container_attribute_name")
                or plan.get("attribute_name")
                or ""
            )
            append_fragment = str(expression.get("append_fragment", "") or "")

            if not attribute_name:
                errors.append("Append SQL blocked because container attribute name is missing.")

            if not append_fragment:
                errors.append("Append SQL blocked because expression.append_fragment is missing.")

            if not oracle.get("exists", False):
                errors.append("Append SQL blocked because target container attribute does not exist.")

            if oracle.get("duplicate_append_key", False):
                errors.append("Append SQL blocked because append key already exists.")

            if not errors:
                recommended_sql, rollback_sql = _generate_append_sql(
                    template_id=template_id,
                    attribute_name=attribute_name,
                    append_fragment=append_fragment,
                    current_attribute_value=current_attribute_value,
                    param_id=param_id,
                )

        elif not errors and operation_type == "update_attribute_value":
            attribute_name = str(plan.get("attribute_name", "") or "")
            compiled_rhs = str(expression.get("compiled_rhs", "") or "")

            if not attribute_name:
                errors.append("Update SQL blocked because attribute_name is missing.")

            if not compiled_rhs:
                errors.append("Update SQL blocked because expression.compiled_rhs is missing.")

            if not oracle.get("exists", False):
                errors.append("Update SQL blocked because target attribute does not exist.")

            if not errors:
                recommended_sql, rollback_sql = _generate_update_value_sql(
                    template_id=template_id,
                    attribute_name=attribute_name,
                    compiled_rhs=compiled_rhs,
                    current_attribute_value=current_attribute_value,
                    param_id=param_id,
                )

        elif not errors and operation_type == "rename_attribute":
            old_attribute_name = str(plan.get("attribute_name", "") or "")
            new_attribute_name = str(plan.get("new_attribute_name", "") or "")

            if not old_attribute_name:
                errors.append("Rename SQL blocked because old attribute_name is missing.")

            if not new_attribute_name:
                errors.append("Rename SQL blocked because new_attribute_name is missing.")

            if not oracle.get("exists", False):
                errors.append("Rename SQL blocked because old attribute does not exist.")

            if oracle.get("target_exists", False):
                errors.append("Rename SQL blocked because new attribute name already exists.")

            if not errors:
                recommended_sql, rollback_sql = _generate_rename_sql(
                    template_id=template_id,
                    old_attribute_name=old_attribute_name,
                    new_attribute_name=new_attribute_name,
                    param_id=param_id,
                )

        elif not errors and operation_type == "add_attribute":
            errors.append(
                "Add attribute SQL is intentionally blocked until PARAM_ID/order/sequence "
                "rules are defined safely."
            )

        else:
            if not errors:
                errors.append(f"SQL generation does not support operation_type={operation_type} yet.")

    except Exception as exc:
        errors.append(f"sql_generation_node failed: {exc}")

    can_execute = bool(recommended_sql) and not errors

    sql_result = {
        "can_execute": can_execute,
        "recommended_sql": recommended_sql,
        "rollback_sql": rollback_sql,
        "reason": (
            "SQL advisory generated."
            if can_execute
            else "SQL advisory blocked: " + " ".join(errors)
        ),
        "warnings": warnings,
        "errors": errors,
    }

    updates = {
        "sql": sql_result,
    }

    if warnings:
        all_warnings = list(state.get("warnings", []) or [])
        all_warnings.extend(warnings)
        updates["warnings"] = all_warnings

    if errors:
        all_errors = list(state.get("errors", []) or [])
        all_errors.extend(errors)
        updates["errors"] = all_errors

    return updates