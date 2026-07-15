from __future__ import annotations

import re
from typing import Any

from activiti_mediation_template_sql_advisor.dsl_compiler.constants import (
    FIELD_PATH_PATTERN,
    RULEBOOK_EVALUATOR,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def structured_output_contract() -> str:
    """
    Prompt contract for the rulebook-only DSL answer.

    Important: this node no longer uses the old dsl_rag KB/retriever/evaluator
    A/B/C files. The only authority for ATTRIBUTE_VALUE syntax is the merged
    attribute_value_runtime_spec.json plus current Oracle examples.
    """
    return """
Return ONLY one JSON object.
Do not include markdown fences.
Do not include prose before or after the JSON.

The JSON object must match this exact schema:

{
  "evaluator": "RULEBOOK",
  "selected_record_ids": ["<rulebook rule id>"],
  "operation_kind": "fixed_literal",
  "is_supported": true,
  "expression": "<exact final RHS DSL expression, or empty string if unsupported>",
  "reason": "<short explanation for logs/human display only>",
  "confidence": 1.0
}

Allowed evaluator value:
- "RULEBOOK"

Allowed operation_kind values:
- "fixed_literal"
- "source_field"
- "mapping"
- "unit_conversion_or_cast"
- "concat"
- "append_subkey"
- "unsupported"

Routing and expression rules:

1. fixed_literal
Use this ONLY when the human request supplies one concrete, unconditional value
with NO if/else, when/then, map, otherwise, DTO/source field, conversion, or
concat language anywhere in the request.
Expression must be exactly:
VAL_<literal>

Example:
add attribute gundu with value 123
=> operation_kind: fixed_literal
=> expression: VAL_123

2. source_field
Use this when the request says DTO field, DTO filed, from DTO, from DTO field,
source field, input field, or take from field.
A source_field means the ATTRIBUTE_VALUE reads from an input/source path.
It is NOT a literal.

Correct:
with dto field allowances.sms.freebies
=> operation_kind: source_field
=> expression: allowances.sms.freebies

Wrong:
=> operation_kind: fixed_literal
=> expression: VAL_allowances.sms.freebies

A plain DTO/source path does NOT require an evaluator A/B/C token. The merged
ATTRIBUTE_VALUE rulebook says that if no known prefix matches, the value falls
back to direct JsonPath/source DTO resolution.

3. mapping
Use this whenever the request contains conditional language such as:
if X show Y else Z
if X set Y otherwise Z
map A to B
when X then Y otherwise Z

Build the expression using this mapping shape:
<sourcePath>#<conditionValue>|<resultValue>,ELSE|<elseValue>

The text before # must be the source/input field from the condition clause.
Never use the target ATTRIBUTE_NAME, new_attribute_name, append_key, or output
attribute name before #.

Example:
If addToBill is false set false, otherwise true.
=> addToBill#false|false,ELSE|true

Example:
If yuuki is false set maakhidi, otherwise gungudu.
=> yuuki#false|maakhidi,ELSE|gungudu

Example:
If subscriberType is PREPAID show 1 else 0.
=> subscriberType#PREPAID|1,ELSE|0

4. append_subkey
Use operation_kind="append_subkey" whenever planner operation_type is
append_attribute_value, or whenever the user says inside existing poAttributes,
inside poAttributes, within poAttributes, or similar.

For append_subkey, expression must contain ONLY the value side.
Do not include append_key=.
Do not include trailing semicolon.
Python will wrap it as append_key=<expression>;.

Example:
add CustomerType with value 123 inside existing poAttributes
=> operation_kind: append_subkey
=> expression: VAL_123

Example:
add CustomerType with value if subscriberType is PREPAID show 1 else 0 inside existing poAttributes
=> operation_kind: append_subkey
=> expression: subscriberType#PREPAID|1,ELSE|0

5. concat / list / complex methods
Use rulebook prefixes only when directly requested.
Examples:
- list from dto field services separated by comma => $LIST(',')services
- first item from dto field services split by comma => $INDEX('0')$LIST(',')services
- dto field customerName and replace spaces with underscores => $REPLACE(' ','_')customerName

6. unsupported
Use this only when the RHS cannot be represented by the merged rulebook, or when
the user gives an invalid source field such as "DTO field 123".
Return is_supported=false and expression="".
""".strip()


def format_oracle_samples_for_dsl(state: AdvisorState) -> str:
    """Format Oracle MCP examples for DSL compilation."""
    oracle = state.get("oracle", {}) or {}
    sample_parameters = oracle.get("sample_parameters", []) or []

    if not sample_parameters:
        return ""

    lines = [
        "Existing working ATTRIBUTE_VALUE examples from the same TEMPLATE_ID:",
    ]

    for index, item in enumerate(sample_parameters[:8], start=1):
        attribute_name = str(item.get("attribute_name", "") or "")
        attribute_value_preview = str(item.get("attribute_value_preview", "") or "")

        if not attribute_name:
            continue

        lines.append(f"{index}. {attribute_name} = {attribute_value_preview}")

    lines.extend(
        [
            "",
            "Use these examples only as syntax-pattern evidence.",
            "Do not copy unrelated attribute values.",
            "Match delimiter style, VAL_ usage, mapping shape, and source path style where relevant.",
        ]
    )

    return "\n".join(lines)


def clean_token(value: str) -> str:
    value = (value or "").strip()
    value = value.strip(" \t\r\n.,;:")
    value = value.strip("'\"")
    return value.strip()


def clean_literal(value: str) -> str:
    value = clean_token(value)
    value = re.split(r"\s+(?:inside|within|under)\s+existing\s+", value, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+(?:inside|within|under)\s+", value, flags=re.IGNORECASE)[0]
    return clean_token(value)


def text_has_any_signal(text: str, signals: list[str]) -> bool:
    lowered = f" {text.lower()} "
    return any(signal in lowered for signal in signals)


def is_valid_field_path(value: str) -> bool:
    value = clean_token(value)
    return bool(re.fullmatch(FIELD_PATH_PATTERN, value))


def extract_source_field(text: str) -> str:
    patterns = [
        rf"(?:dto\s+field|dto\s+filed|from\s+dto\s+field|from\s+dto|source\s+field|input\s+field|take\s+from\s+field)\s+(?P<path>{FIELD_PATH_PATTERN})",
        rf"(?:json\s+path|json\s+field|payload\s+field)\s+(?P<path>{FIELD_PATH_PATTERN})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            return clean_token(match.group("path"))

    return ""


def extract_literal_value(text: str) -> str:
    patterns = [
        r"(?:with\s+)?value\s+(?P<value>.+?)(?:\s+(?:inside|within|under)\b|[.]?$)",
        r"(?:set\s+to|as)\s+(?P<value>.+?)(?:\s+(?:inside|within|under)\b|[.]?$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = clean_literal(match.group("value"))
            if value:
                return value

    return ""


def extract_mapping(text: str) -> tuple[str, str, str, str] | None:
    patterns = [
        rf"(?:if|when)\s+(?P<source>{FIELD_PATH_PATTERN})\s+(?:is|equals|=)\s+(?P<condition>.+?)\s+(?:set|show|send|return|then)\s+(?P<result>.+?)\s+(?:else|otherwise)\s+(?P<else_value>.+?)(?:[.]|$)",
        rf"(?:if|when)\s+(?P<source>{FIELD_PATH_PATTERN})\s+(?P<condition>[^\s]+)\s+(?:set|show|send|return|then)\s+(?P<result>.+?)\s+(?:else|otherwise)\s+(?P<else_value>.+?)(?:[.]|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if not match:
            continue

        source = clean_token(match.group("source"))
        condition = clean_literal(match.group("condition"))
        result = clean_literal(match.group("result"))
        else_value = clean_literal(match.group("else_value"))

        if source and condition and result and else_value:
            return source, condition, result, else_value

    return None


def build_append_fragment(append_key: str, expression: str) -> str:
    append_key = (append_key or "").strip()
    expression = (expression or "").strip()

    if not append_key or not expression:
        return ""

    return f"{append_key}={expression};"


def structured(
    *,
    operation_kind: str,
    expression: str,
    reason: str,
    confidence: float = 1.0,
    selected_record_ids: list[str] | None = None,
    is_supported: bool = True,
) -> dict[str, Any]:
    return {
        "evaluator": RULEBOOK_EVALUATOR,
        "selected_record_ids": selected_record_ids or ["RULEBOOK"],
        "operation_kind": operation_kind,
        "is_supported": is_supported,
        "expression": expression,
        "reason": reason,
        "confidence": confidence,
    }
