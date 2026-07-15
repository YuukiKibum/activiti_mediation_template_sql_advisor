from __future__ import annotations

import re

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    SOURCE_FIELD_SIGNALS,
    UNIT_CONVERSION_SIGNALS,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import text_has_any_signal


def final_expression_safety_issues(
    *,
    operation_type: str,
    operation_kind: str,
    expression: str,
    rhs_request: str,
    user_requirement: str,
) -> list[str]:
    """
    Hard Python safety checks.

    These checks protect SQL generation even if the evaluator accepts a bad expression.
    """
    issues: list[str] = []

    combined_text = f"{rhs_request} {user_requirement}"
    expression = expression or ""

    has_source_field_signal = text_has_any_signal(combined_text, SOURCE_FIELD_SIGNALS)
    has_unit_conversion_signal = text_has_any_signal(combined_text, UNIT_CONVERSION_SIGNALS)

    has_boolean_conversion_signal = text_has_any_signal(
        combined_text,
        [
            "boolean",
            "bool",
            "convert it to boolean",
            "convert to boolean",
            "as boolean",
            "to boolean",
        ],
    )

    if re.search(
        r"\b(?:inside|within|under)\s+(?:existing\s+)?[A-Za-z_][A-Za-z0-9_]*",
        expression,
        flags=re.IGNORECASE,
    ):
        issues.append(
            "Compiled expression contains container/location text such as 'inside existing ...'. "
            "That text is request context and must not be stored in ATTRIBUTE_VALUE."
        )

    if operation_type == "append_attribute_value":
        if operation_kind != "append_subkey":
            issues.append("append_attribute_value must use operation_kind='append_subkey' after evaluation.")

        if "=" in expression or expression.endswith(";"):
            issues.append(
                "append_attribute_value expression must be RHS value only. "
                "Do not include append_key= or trailing semicolon."
            )

    if operation_type in {"add_attribute", "update_attribute_value"}:
        if re.fullmatch(r"[^=;]+=[^;]+;?", expression.strip()):
            issues.append(
                "Atomic add/update ATTRIBUTE_VALUE must not be key=value;. "
                "ATTRIBUTE_NAME is already the row key."
            )

    if has_source_field_signal and expression.startswith("VAL_"):
        issues.append(
            "Request asks for DTO/source field, but expression starts with VAL_. "
            "VAL_ means static literal, not source-field lookup."
        )

    if has_boolean_conversion_signal:
        if operation_kind != "unit_conversion_or_cast" or not expression.startswith("$BOOL_"):
            issues.append(
                "Request asks to convert a DTO/source field to BOOLEAN, but expression does not use $BOOL_<sourcePath>."
            )

    if has_unit_conversion_signal and operation_kind == "fixed_literal":
        issues.append(
            "Request contains conversion/type-cast language, but expression is classified as fixed_literal."
        )

    return issues
