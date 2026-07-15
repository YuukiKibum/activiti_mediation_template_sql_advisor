from __future__ import annotations

from typing import Any

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    COMPLEX_METHOD_SIGNALS,
    CONDITIONAL_SIGNALS,
    LIST_SIGNALS,
    SOURCE_FIELD_SIGNALS,
    UNIT_CONVERSION_SIGNALS,
)
from activiti_mediation_template_sql_advisor.dsl_compiler.helpers import (
    extract_literal_value,
    extract_mapping,
    extract_source_field,
    structured,
    text_has_any_signal,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def try_compile_deterministically(state: AdvisorState) -> dict[str, Any] | None:
    """
    Compile the common RHS cases without any LLM call.

    This removes the old DSL KB dependency for the demo-critical paths:
    - fixed literals
    - DTO/source fields
    - simple conditional mappings
    - append into composite ATTRIBUTE_VALUE
    - list / replace / first-item complex method examples
    """
    plan = state.get("plan", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")
    user_requirement = str(
        state.get("user_requirement", "") or state.get("requirement", "") or ""
    )

    text = f"{rhs_request}\n{user_requirement}".strip()
    text_lower = f" {text.lower()} "

    has_source_field_signal = text_has_any_signal(text, SOURCE_FIELD_SIGNALS)
    has_conditional_signal = text_has_any_signal(text, CONDITIONAL_SIGNALS)
    has_list_signal = text_has_any_signal(text, LIST_SIGNALS)
    has_complex_signal = text_has_any_signal(text, COMPLEX_METHOD_SIGNALS)

    mapping_parts = extract_mapping(text)
    if mapping_parts:
        source, condition, result, else_value = mapping_parts
        expression = f"{source}#{condition}|{result},ELSE|{else_value}"

        if operation_type == "append_attribute_value":
            return structured(
                operation_kind="append_subkey",
                expression=expression,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-MAPPING"],
                reason="Rulebook deterministic compile: append sub-key value is a conditional mapping.",
                confidence=1.0,
            )

        return structured(
            operation_kind="mapping",
            expression=expression,
            selected_record_ids=["RULEBOOK-MAPPING"],
            reason="Rulebook deterministic compile: conditional request uses source#condition|result,ELSE|default mapping syntax.",
            confidence=1.0,
        )

    if has_conditional_signal:
        return None

    source_field = extract_source_field(text)

    if source_field:
        if "first item" in text_lower or "first value" in text_lower or "first element" in text_lower:
            if "comma" in text_lower or "split" in text_lower or has_list_signal:
                return structured(
                    operation_kind="unit_conversion_or_cast",
                    expression=f"$INDEX('0')$LIST(','){source_field}",
                    selected_record_ids=["RULEBOOK-INDEX", "RULEBOOK-LIST"],
                    reason="Rulebook deterministic compile: split source field by comma and take first item.",
                    confidence=0.95,
                )

        if has_list_signal:
            delimiter = ","
            return structured(
                operation_kind="unit_conversion_or_cast",
                expression=f"$LIST('{delimiter}'){source_field}",
                selected_record_ids=["RULEBOOK-LIST"],
                reason="Rulebook deterministic compile: list conversion using $LIST delimiter method.",
                confidence=0.95,
            )

        if "replace spaces with underscores" in text_lower or "replace space with underscore" in text_lower:
            return structured(
                operation_kind="unit_conversion_or_cast",
                expression=f"$REPLACE(' ','_'){source_field}",
                selected_record_ids=["RULEBOOK-REPLACE"],
                reason="Rulebook deterministic compile: complex $REPLACE method applied to source field.",
                confidence=0.95,
            )

        if operation_type == "append_attribute_value":
            return structured(
                operation_kind="append_subkey",
                expression=source_field,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-SOURCE_FIELD"],
                reason="Rulebook deterministic compile: append sub-key value reads from DTO/source field.",
                confidence=1.0,
            )

        return structured(
            operation_kind="source_field",
            expression=source_field,
            selected_record_ids=["RULEBOOK-SOURCE_FIELD"],
            reason="Rulebook deterministic compile: DTO/source field request uses plain source path, not VAL_ literal.",
            confidence=1.0,
        )

    if has_source_field_signal:
        return structured(
            operation_kind="unsupported",
            expression="",
            selected_record_ids=["RULEBOOK-SOURCE_FIELD-INVALID"],
            is_supported=False,
            reason="DTO/source field language was present, but a valid field path could not be identified.",
            confidence=1.0,
        )

    literal_value = extract_literal_value(text)
    if literal_value:
        expression = f"VAL_{literal_value}"

        if operation_type == "append_attribute_value":
            return structured(
                operation_kind="append_subkey",
                expression=expression,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-VAL_LITERAL"],
                reason="Rulebook deterministic compile: append sub-key value is a fixed literal, so value side uses VAL_.",
                confidence=1.0,
            )

        return structured(
            operation_kind="fixed_literal",
            expression=expression,
            selected_record_ids=["RULEBOOK-VAL_LITERAL"],
            reason="Rulebook deterministic compile: concrete unconditional value uses VAL_ literal syntax.",
            confidence=1.0,
        )

    if has_list_signal or has_complex_signal or text_has_any_signal(text, UNIT_CONVERSION_SIGNALS):
        return None

    return None
