from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def _format_sql_block(statements: list[str]) -> str:
    """
    Convert a list of SQL/comment strings into one SQL code block.
    """
    if not statements:
        return "No SQL generated."

    return "\n\n".join(statements)


def _format_rag_sources(rag_context: list[dict[str, Any]]) -> str:
    """
    Create a short source summary from retrieved RAG chunks.
    """
    if not rag_context:
        return "No RAG documentation context was retrieved."

    seen: set[str] = set()
    sources: list[str] = []

    for item in rag_context:
        source = str(item.get("source", "Unknown"))
        score = item.get("score")

        key = source

        if key in seen:
            continue

        seen.add(key)

        if score is not None:
            sources.append(f"- {source} — score: {score}")
        else:
            sources.append(f"- {source}")

    return "\n".join(sources)


def _format_current_parameter_preview(state: AdvisorState) -> str:
    """
    Show a small preview of the current Oracle parameter row.
    """
    current_parameter = state.get("current_parameter")

    if not current_parameter:
        return "No current parameter row was found."

    attribute_value = str(current_parameter.get("attribute_value") or "")

    preview = attribute_value[:700]

    if len(attribute_value) > 700:
        preview += "..."

    return "\n".join(
        [
            f"- PARAM_ID: {current_parameter.get('param_id')}",
            f"- TEMPLATE_ID: {current_parameter.get('template_id')}",
            f"- ATTRIBUTE_NAME: {current_parameter.get('attribute_name')}",
            f"- ATTRIBUTE_VALUE preview: {preview}",
        ]
    )


def final_response_node(state: AdvisorState) -> dict[str, Any]:
    """
    LangGraph node: create the final human-readable advisor response.

    Reads:
        user_requirement
        operation_type
        template_id
        attribute_name
        new_attribute_name
        new_attribute_value
        value_to_append
        current_template
        current_parameter
        rag_context
        generated_sql
        rollback_sql
        warnings
        validation_errors

    Writes:
        final_answer
    """
    user_requirement = state.get("user_requirement", "")
    operation_type = state.get("operation_type", "unknown")
    template_id = state.get("template_id", "")
    attribute_name = state.get("attribute_name", "")
    new_attribute_name = state.get("new_attribute_name", "")
    generated_sql = state.get("generated_sql", [])
    rollback_sql = state.get("rollback_sql", [])
    warnings = state.get("warnings", [])
    validation_errors = state.get("validation_errors", [])
    rag_context = state.get("rag_context", [])

    sections: list[str] = []

    sections.append("# Activiti Mediation Template SQL Advisor")

    sections.append(
        "\n".join(
            [
                "## Requirement",
                user_requirement or "No requirement provided.",
            ]
        )
    )

    sections.append(
        "\n".join(
            [
                "## Planner Summary",
                f"- Operation type: `{operation_type}`",
                f"- TEMPLATE_ID: `{template_id}`",
                f"- ATTRIBUTE_NAME: `{attribute_name}`",
                f"- New ATTRIBUTE_NAME: `{new_attribute_name}`"
                if new_attribute_name
                else "- New ATTRIBUTE_NAME: not applicable",
            ]
        )
    )

    sections.append(
        "\n".join(
            [
                "## Expression Compilation",
                f"- Did compile: `{state.get('expression_compilation_did_compile', False)}`",
                f"- Confidence: `{state.get('expression_compilation_confidence', 0.0)}`",
                f"- Reason: {state.get('expression_compilation_reason', '') or 'Not applicable'}",
            ]
        )
    )

    sections.append(
        "\n".join(
            [
                "## Current Oracle Configuration",
                _format_current_parameter_preview(state),
            ]
        )
    )

    sections.append(
        "\n".join(
            [
                "## RAG Documentation Sources",
                _format_rag_sources(rag_context),
            ]
        )
    )

    if validation_errors:
        sections.append(
            "\n".join(
                [
                    "## Validation Errors",
                    "\n".join(f"- {error}" for error in validation_errors),
                ]
            )
        )

        sections.append(
            "SQL was not generated because validation errors were found."
        )

    else:
        sections.append(
            "\n".join(
                [
                    "## Recommended SQL",
                    "```sql",
                    _format_sql_block(generated_sql),
                    "```",
                ]
            )
        )

        sections.append(
            "\n".join(
                [
                    "## Rollback SQL",
                    "```sql",
                    _format_sql_block(rollback_sql),
                    "```",
                ]
            )
        )

    if warnings:
        sections.append(
            "\n".join(
                [
                    "## Warnings",
                    "\n".join(f"- {warning}" for warning in warnings),
                ]
            )
        )

    sections.append(
        "\n".join(
            [
                "## Safety Note",
                (
                    "This assistant only generated advisory SQL. "
                    "Review the pre-checks and SQL manually before running anything in Oracle."
                ),
            ]
        )
    )

    return {
        "final_answer": "\n\n".join(sections)
    }


if __name__ == "__main__":
    test_state: AdvisorState = {
        "user_requirement": (
            "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN"
        ),
        "operation_type": "rename_attribute",
        "template_id": "MT_ECM_PRE_BASEPLAN",
        "attribute_name": "poAttributes",
        "new_attribute_name": "poAttributeList",
        "current_parameter": {
            "param_id": 210354,
            "template_id": "MT_ECM_PRE_BASEPLAN",
            "attribute_name": "poAttributes",
            "attribute_value": "ccat_product_category=VAL_Consumer;ccat_product_group=VAL_M;",
        },
        "rag_context": [
            {
                "source": "Objective.docx",
                "score": 0.56,
            },
            {
                "source": "The Activiti Mediation Expression.docx",
                "score": 0.37,
            },
        ],
        "generated_sql": [
            "-- Pre-check: source attribute should exist",
            "SELECT PARAM_ID, TEMPLATE_ID, ATTRIBUTE_NAME, ATTRIBUTE_VALUE\n"
            "FROM ACT_MEDIATION_PARAMETER\n"
            "WHERE TEMPLATE_ID = 'MT_ECM_PRE_BASEPLAN' "
            "AND ATTRIBUTE_NAME = 'poAttributes';",
            "-- Change: rename ATTRIBUTE_NAME",
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            "SET ATTRIBUTE_NAME = 'poAttributeList'\n"
            "WHERE TEMPLATE_ID = 'MT_ECM_PRE_BASEPLAN' "
            "AND ATTRIBUTE_NAME = 'poAttributes';",
            "COMMIT;",
        ],
        "rollback_sql": [
            "-- Rollback: restore old ATTRIBUTE_NAME",
            "UPDATE ACT_MEDIATION_PARAMETER\n"
            "SET ATTRIBUTE_NAME = 'poAttributes'\n"
            "WHERE TEMPLATE_ID = 'MT_ECM_PRE_BASEPLAN' "
            "AND ATTRIBUTE_NAME = 'poAttributeList';",
            "COMMIT;",
        ],
        "warnings": [
            "Generated SQL is advisory only. Review and run manually in Oracle."
        ],
        "validation_errors": [],
    }

    result = final_response_node(test_state)

    print(result["final_answer"])