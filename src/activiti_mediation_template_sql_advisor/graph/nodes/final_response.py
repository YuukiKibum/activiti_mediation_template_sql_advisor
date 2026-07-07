from __future__ import annotations

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def _section(title: str, body: str) -> str:
    body = body.strip()

    if not body:
        return ""

    return f"## {title}\n\n{body}"


def final_response_node(state: AdvisorState) -> dict:
    plan = state.get("plan", {}) or {}
    template = state.get("template", {}) or {}
    expression = state.get("expression", {}) or {}
    oracle = state.get("oracle", {}) or {}
    sql = state.get("sql", {}) or {}

    warnings = state.get("warnings", []) or []
    errors = state.get("errors", []) or []

    summary_lines = [
        f"Operation: {plan.get('operation_type', 'unknown')}",
        f"Template ID: {template.get('template_id', 'Not resolved') or 'Not resolved'}",
        f"External system: {template.get('external_system', '') or 'Not available'}",
        f"Template match: {template.get('match_type', '') or 'Not available'}",
        f"Attribute: {plan.get('attribute_name', '') or 'Not applicable'}",
    ]

    if plan.get("operation_type") == "append_attribute_value":
        summary_lines.extend(
            [
                f"Container attribute: {plan.get('container_attribute_name', '')}",
                f"Append key: {plan.get('append_key', '')}",
            ]
        )

    if plan.get("operation_type") == "rename_attribute":
        summary_lines.append(f"New attribute name: {plan.get('new_attribute_name', '')}")

    expression_lines = [
        f"Compiled: {expression.get('did_compile', False)}",
        f"Supported: {expression.get('is_supported', False)}",
        f"Evaluator: {expression.get('selected_evaluator', '') or 'Not available'}",
        f"Selected KB record: {expression.get('selected_record_id', '') or 'Not available'}",
        f"Compiled RHS: {expression.get('compiled_rhs', '') or 'Not available'}",
    ]

    if expression.get("append_fragment"):
        expression_lines.append(f"Append fragment: {expression.get('append_fragment')}")

    if expression.get("reason"):
        expression_lines.append("")
        expression_lines.append("DSL answer:")
        expression_lines.append(str(expression.get("reason", "")))

    oracle_lines = [
        f"Can generate SQL: {oracle.get('can_generate_sql', False)}",
        f"Template ID: {oracle.get('template_id', '') or 'Not available'}",
        f"Attribute name: {oracle.get('attribute_name', '') or 'Not available'}",
    ]

    if oracle.get("warnings"):
        oracle_lines.append("")
        oracle_lines.append("Oracle warnings:")
        oracle_lines.extend(f"- {warning}" for warning in oracle.get("warnings", []))

    sql_lines = [
        f"Can execute: {sql.get('can_execute', False)}",
        f"Reason: {sql.get('reason', '')}",
    ]

    if sql.get("recommended_sql"):
        sql_lines.append("")
        sql_lines.append("Recommended SQL:")
        sql_lines.append("```sql")
        sql_lines.append(str(sql.get("recommended_sql", "")))
        sql_lines.append("```")

    if sql.get("rollback_sql"):
        sql_lines.append("")
        sql_lines.append("Rollback SQL:")
        sql_lines.append("```sql")
        sql_lines.append(str(sql.get("rollback_sql", "")))
        sql_lines.append("```")

    warning_error_lines: list[str] = []

    if warnings:
        warning_error_lines.append("Warnings:")
        warning_error_lines.extend(f"- {warning}" for warning in warnings)

    if errors:
        if warning_error_lines:
            warning_error_lines.append("")

        warning_error_lines.append("Errors:")
        warning_error_lines.extend(f"- {error}" for error in errors)

    final_answer = "\n\n".join(
        section
        for section in [
            _section("Advisor Summary", "\n".join(summary_lines)),
            _section("Expression Compilation", "\n".join(expression_lines)),
            _section("Oracle Inspection", "\n".join(oracle_lines)),
            _section("SQL Advisory", "\n".join(sql_lines)),
            _section("Warnings / Errors", "\n".join(warning_error_lines)),
        ]
        if section
    )

    return {
        "final_answer": final_answer,
    }