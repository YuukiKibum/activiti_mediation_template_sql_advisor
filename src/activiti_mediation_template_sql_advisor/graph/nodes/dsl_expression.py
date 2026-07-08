from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


load_dotenv()

RULEBOOK_EVALUATOR = "RULEBOOK"

ALLOWED_EVALUATORS = {RULEBOOK_EVALUATOR}

ALLOWED_OPERATION_KINDS = {
    "fixed_literal",
    "source_field",
    "mapping",
    "unit_conversion_or_cast",
    "concat",
    "append_subkey",
    "unsupported",
}

# For append_attribute_value, the planner already decided that the database row
# is a composite/container attribute such as poAttributes. The expression should
# be the value side only; Python wraps it as append_key=<expression>;.
APPEND_VALUE_OPERATION_KINDS = {
    "append_subkey",
    "fixed_literal",
    "source_field",
    "mapping",
    "unit_conversion_or_cast",
    "concat",
}

CONDITIONAL_SIGNALS = [
    " if ",
    "if ",
    " else",
    "otherwise",
    " when ",
    "map ",
    "mapping",
    " then ",
]

UNIT_CONVERSION_SIGNALS = [
    "convert",
    "seconds",
    "minutes",
    "hours",
    " to bytes",
    " to kb",
    " to mb",
    " to gb",
    "cast to",
    "as a long",
    "as an integer",
    "as a double",
]

SOURCE_FIELD_SIGNALS = [
    "dto field",
    "dto filed",
    "from dto",
    "from dto field",
    "source field",
    "input field",
    "take from field",
]

LIST_SIGNALS = [
    " as list ",
    " list from ",
    " split by ",
    " separated by comma",
    " comma separated",
]

COMPLEX_METHOD_SIGNALS = [
    "replace spaces with underscores",
    "replace space with underscore",
    "first item",
    "first value",
    "first element",
]

MAX_CLASSIFICATION_RETRIES = 1

# Accept plain source names, dotted source paths, and $. JsonPath-style paths.
FIELD_PATH_PATTERN = r"(?:\$\.)?[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\[[^\]]+\])*"


# -----------------------------------------------------------------------------
# Prompt contract
# -----------------------------------------------------------------------------


def _structured_output_contract() -> str:
    """
    Prompt contract for the rulebook-only DSL answer.

    Important: this node no longer uses the old dsl_rag KB/retriever/evaluator
    A/B/C files. The only authority for ATTRIBUTE_VALUE syntax is the merged
    attribute_value_rulebook.json plus current Oracle examples.
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


# -----------------------------------------------------------------------------
# Formatting / extraction helpers
# -----------------------------------------------------------------------------


def _format_oracle_samples_for_dsl(state: AdvisorState) -> str:
    """
    Format Oracle MCP examples for DSL compilation.

    These examples are syntax-pattern evidence only.
    They must not be copied as business values.
    """
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


def _clean_token(value: str) -> str:
    value = (value or "").strip()
    value = value.strip(" \t\r\n.,;:")
    value = value.strip("'\"")
    return value.strip()


def _clean_literal(value: str) -> str:
    value = _clean_token(value)
    # Remove common trailing explanatory phrases that appear in full requirements.
    value = re.split(r"\s+(?:inside|within|under)\s+existing\s+", value, flags=re.IGNORECASE)[0]
    value = re.split(r"\s+(?:inside|within|under)\s+", value, flags=re.IGNORECASE)[0]
    return _clean_token(value)


def _text_has_any_signal(text: str, signals: list[str]) -> bool:
    lowered = f" {text.lower()} "
    return any(signal in lowered for signal in signals)


def _is_valid_field_path(value: str) -> bool:
    value = _clean_token(value)
    return bool(re.fullmatch(FIELD_PATH_PATTERN, value))


def _extract_source_field(text: str) -> str:
    patterns = [
        rf"(?:dto\s+field|dto\s+filed|from\s+dto\s+field|from\s+dto|source\s+field|input\s+field|take\s+from\s+field)\s+(?P<path>{FIELD_PATH_PATTERN})",
        rf"(?:json\s+path|json\s+field|payload\s+field)\s+(?P<path>{FIELD_PATH_PATTERN})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            return _clean_token(match.group("path"))

    return ""


def _extract_literal_value(text: str) -> str:
    patterns = [
        r"(?:with\s+)?value\s+(?P<value>.+?)(?:\s+(?:inside|within|under)\b|[.]?$)",
        r"(?:set\s+to|as)\s+(?P<value>.+?)(?:\s+(?:inside|within|under)\b|[.]?$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if match:
            value = _clean_literal(match.group("value"))
            if value:
                return value

    return ""


def _extract_mapping(text: str) -> tuple[str, str, str, str] | None:
    """
    Extract simple if/when mapping patterns such as:
    if subscriberType is PREPAID show 1 else 0
    if addToBill is false set false otherwise true
    """
    patterns = [
        rf"(?:if|when)\s+(?P<source>{FIELD_PATH_PATTERN})\s+(?:is|equals|=)\s+(?P<condition>.+?)\s+(?:set|show|send|return|then)\s+(?P<result>.+?)\s+(?:else|otherwise)\s+(?P<else_value>.+?)(?:[.]|$)",
        rf"(?:if|when)\s+(?P<source>{FIELD_PATH_PATTERN})\s+(?P<condition>[^\s]+)\s+(?:set|show|send|return|then)\s+(?P<result>.+?)\s+(?:else|otherwise)\s+(?P<else_value>.+?)(?:[.]|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        if not match:
            continue

        source = _clean_token(match.group("source"))
        condition = _clean_literal(match.group("condition"))
        result = _clean_literal(match.group("result"))
        else_value = _clean_literal(match.group("else_value"))

        if source and condition and result and else_value:
            return source, condition, result, else_value

    return None


def _build_append_fragment(append_key: str, expression: str) -> str:
    append_key = (append_key or "").strip()
    expression = (expression or "").strip()

    if not append_key or not expression:
        return ""

    return f"{append_key}={expression};"


def _structured(
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


# -----------------------------------------------------------------------------
# Deterministic rulebook compiler
# -----------------------------------------------------------------------------


def _try_compile_deterministically(state: AdvisorState) -> dict[str, Any] | None:
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

    has_source_field_signal = _text_has_any_signal(text, SOURCE_FIELD_SIGNALS)
    has_conditional_signal = _text_has_any_signal(text, CONDITIONAL_SIGNALS)
    has_list_signal = _text_has_any_signal(text, LIST_SIGNALS)
    has_complex_signal = _text_has_any_signal(text, COMPLEX_METHOD_SIGNALS)

    # 1. Conditional mapping always wins before literal/source-field handling.
    mapping_parts = _extract_mapping(text)
    if mapping_parts:
        source, condition, result, else_value = mapping_parts
        expression = f"{source}#{condition}|{result},ELSE|{else_value}"

        if operation_type == "append_attribute_value":
            return _structured(
                operation_kind="append_subkey",
                expression=expression,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-MAPPING"],
                reason="Rulebook deterministic compile: append sub-key value is a conditional mapping.",
                confidence=1.0,
            )

        return _structured(
            operation_kind="mapping",
            expression=expression,
            selected_record_ids=["RULEBOOK-MAPPING"],
            reason="Rulebook deterministic compile: conditional request uses source#condition|result,ELSE|default mapping syntax.",
            confidence=1.0,
        )

    # If conditional language exists but we cannot parse it reliably, let the LLM
    # try using the rulebook-only prompt rather than guessing.
    if has_conditional_signal:
        return None

    source_field = _extract_source_field(text)

    # 2. Complex/list methods with source path.
    if source_field:
        if "first item" in text_lower or "first value" in text_lower or "first element" in text_lower:
            if "comma" in text_lower or "split" in text_lower or has_list_signal:
                return _structured(
                    operation_kind="unit_conversion_or_cast",
                    expression=f"$INDEX('0')$LIST(','){source_field}",
                    selected_record_ids=["RULEBOOK-INDEX", "RULEBOOK-LIST"],
                    reason="Rulebook deterministic compile: split source field by comma and take first item.",
                    confidence=0.95,
                )

        if has_list_signal:
            delimiter = ","
            return _structured(
                operation_kind="unit_conversion_or_cast",
                expression=f"$LIST('{delimiter}'){source_field}",
                selected_record_ids=["RULEBOOK-LIST"],
                reason="Rulebook deterministic compile: list conversion using $LIST delimiter method.",
                confidence=0.95,
            )

        if "replace spaces with underscores" in text_lower or "replace space with underscore" in text_lower:
            return _structured(
                operation_kind="unit_conversion_or_cast",
                expression=f"$REPLACE(' ','_'){source_field}",
                selected_record_ids=["RULEBOOK-REPLACE"],
                reason="Rulebook deterministic compile: complex $REPLACE method applied to source field.",
                confidence=0.95,
            )

        if operation_type == "append_attribute_value":
            return _structured(
                operation_kind="append_subkey",
                expression=source_field,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-SOURCE_FIELD"],
                reason="Rulebook deterministic compile: append sub-key value reads from DTO/source field.",
                confidence=1.0,
            )

        return _structured(
            operation_kind="source_field",
            expression=source_field,
            selected_record_ids=["RULEBOOK-SOURCE_FIELD"],
            reason="Rulebook deterministic compile: DTO/source field request uses plain source path, not VAL_ literal.",
            confidence=1.0,
        )

    if has_source_field_signal:
        return _structured(
            operation_kind="unsupported",
            expression="",
            selected_record_ids=["RULEBOOK-SOURCE_FIELD-INVALID"],
            is_supported=False,
            reason="DTO/source field language was present, but a valid field path could not be identified.",
            confidence=1.0,
        )

    # 3. Concrete literal.
    literal_value = _extract_literal_value(text)
    if literal_value:
        expression = f"VAL_{literal_value}"

        if operation_type == "append_attribute_value":
            return _structured(
                operation_kind="append_subkey",
                expression=expression,
                selected_record_ids=["RULEBOOK-APPEND_SUBKEY", "RULEBOOK-VAL_LITERAL"],
                reason="Rulebook deterministic compile: append sub-key value is a fixed literal, so value side uses VAL_.",
                confidence=1.0,
            )

        return _structured(
            operation_kind="fixed_literal",
            expression=expression,
            selected_record_ids=["RULEBOOK-VAL_LITERAL"],
            reason="Rulebook deterministic compile: concrete unconditional value uses VAL_ literal syntax.",
            confidence=1.0,
        )

    # 4. Complex request but no source path found: let LLM try rulebook-only.
    if has_list_signal or has_complex_signal or _text_has_any_signal(text, UNIT_CONVERSION_SIGNALS):
        return None

    return None


# -----------------------------------------------------------------------------
# Rulebook-only LLM fallback
# -----------------------------------------------------------------------------


def _build_dsl_query(
    state: AdvisorState,
    *,
    correction_note: str = "",
) -> str:
    plan = state.get("plan", {}) or {}
    template = state.get("template", {}) or {}
    oracle = state.get("oracle", {}) or {}

    user_requirement = str(
        state.get("user_requirement", "")
        or state.get("requirement", "")
        or ""
    )

    operation_type = str(plan.get("operation_type", "") or "")
    attribute_name = str(plan.get("attribute_name", "") or "")
    new_attribute_name = str(plan.get("new_attribute_name", "") or "")
    container_attribute_name = str(plan.get("container_attribute_name", "") or "")
    append_key = str(plan.get("append_key", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")

    try:
        rulebook_summary = get_rulebook_prompt_summary()
    except Exception as exc:
        rulebook_summary = f"ATTRIBUTE_VALUE rulebook could not be loaded: {exc}"

    oracle_samples_text = _format_oracle_samples_for_dsl(state)

    parts = [
        "You are compiling ONLY the RHS ATTRIBUTE_VALUE expression for ACT_MEDIATION_PARAMETER.",
        "Use the merged ATTRIBUTE_VALUE rulebook as the source of truth.",
        "Do not use evaluator A/B/C. Do not mention old DSL KB records.",
        "Return evaluator='RULEBOOK'.",
        "",
        _structured_output_contract(),
        "",
        "ATTRIBUTE_VALUE rulebook summary:",
        rulebook_summary,
        "",
        "Current request context:",
        f"Full user requirement: {user_requirement}",
        f"Planner operation_type: {operation_type}",
        f"Template ID: {template.get('template_id', '')}",
        f"Template external system: {template.get('external_system', '')}",
        f"Attribute name: {attribute_name}",
        f"New attribute name: {new_attribute_name}",
        f"RHS request from planner: {rhs_request}",
    ]

    if operation_type == "append_attribute_value":
        current_attribute_value = str(
            oracle.get("current_attribute_value", "") or ""
        )

        parts.extend(
            [
                "",
                "Append/composite attribute context:",
                "The SQL row is the existing container attribute.",
                "Return operation_kind='append_subkey'.",
                "Return expression as ONLY the value side for the new sub-key.",
                "Do not include append_key= in expression.",
                "Do not include trailing semicolon in expression.",
                f"Existing container attribute: {container_attribute_name}",
                f"Append key: {append_key}",
                f"Current full ATTRIBUTE_VALUE preview: {current_attribute_value[:1500]}",
            ]
        )

    elif operation_type in {"add_attribute", "update_attribute_value"}:
        parts.extend(
            [
                "",
                "Add/update ATTRIBUTE_VALUE context:",
                "Return the final concrete RHS expression.",
                "Do not return placeholders such as VAL_<literal>.",
                "Do not return SQL.",
            ]
        )

    else:
        parts.extend(
            [
                "",
                "This operation does not require DSL RHS compilation.",
            ]
        )

    if oracle_samples_text:
        parts.extend(["", oracle_samples_text])

    if correction_note:
        parts.extend(
            [
                "",
                "CORRECTION FROM A PREVIOUS ATTEMPT:",
                correction_note,
            ]
        )

    return "\n".join(parts)


def _call_rulebook_llm(dsl_query: str) -> str:
    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The openai package is required for rulebook fallback generation. Install it with: uv add openai"
        ) from exc

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict rulebook-only compiler for "
                    "ACT_MEDIATION_PARAMETER.ATTRIBUTE_VALUE. Return JSON only."
                ),
            },
            {"role": "user", "content": dsl_query},
        ],
    )

    return response.choices[0].message.content or ""


# -----------------------------------------------------------------------------
# JSON parsing / validation
# -----------------------------------------------------------------------------


def _strip_json_fences(raw_answer: str) -> str:
    text = (raw_answer or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


def _parse_structured_answer(raw_answer: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_answer, dict):
        data = raw_answer
    else:
        text = _strip_json_fences(raw_answer)

        if not text:
            raise ValueError("Rulebook compiler returned an empty response; expected JSON object.")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Rulebook compiler did not return valid JSON: {exc.msg}. Raw answer: {raw_answer}"
            ) from exc

    if not isinstance(data, dict):
        raise ValueError("Rulebook compiler JSON must be an object.")

    required_keys = {
        "evaluator",
        "selected_record_ids",
        "operation_kind",
        "is_supported",
        "expression",
        "reason",
        "confidence",
    }

    missing_keys = sorted(required_keys - set(data.keys()))

    if missing_keys:
        raise ValueError(
            "Rulebook compiler JSON is missing required keys: " + ", ".join(missing_keys)
        )

    evaluator = data["evaluator"]

    if not isinstance(evaluator, str) or evaluator not in ALLOWED_EVALUATORS:
        raise ValueError(
            f"Rulebook compiler JSON has invalid evaluator={evaluator!r}; expected 'RULEBOOK'."
        )

    selected_record_ids = data["selected_record_ids"]

    if not isinstance(selected_record_ids, list) or not all(
        isinstance(item, str) for item in selected_record_ids
    ):
        raise ValueError("Rulebook compiler JSON selected_record_ids must be a list of strings.")

    operation_kind = data["operation_kind"]

    if not isinstance(operation_kind, str) or operation_kind not in ALLOWED_OPERATION_KINDS:
        raise ValueError(
            f"Rulebook compiler JSON has invalid operation_kind={operation_kind!r}; "
            f"expected one of {sorted(ALLOWED_OPERATION_KINDS)}."
        )

    is_supported = data["is_supported"]

    if not isinstance(is_supported, bool):
        raise ValueError("Rulebook compiler JSON is_supported must be a boolean.")

    expression = data["expression"]

    if not isinstance(expression, str):
        raise ValueError("Rulebook compiler JSON expression must be a string.")

    reason = data["reason"]

    if not isinstance(reason, str):
        raise ValueError("Rulebook compiler JSON reason must be a string.")

    confidence = data["confidence"]

    if not isinstance(confidence, (int, float)):
        raise ValueError("Rulebook compiler JSON confidence must be a number.")

    confidence_float = float(confidence)

    if confidence_float < 0.0 or confidence_float > 1.0:
        raise ValueError("Rulebook compiler JSON confidence must be between 0.0 and 1.0.")

    expression = expression.strip()

    if operation_kind == "unsupported" and is_supported:
        raise ValueError("operation_kind='unsupported' requires is_supported=false.")

    if not is_supported and expression:
        raise ValueError("Unsupported result must use an empty expression.")

    if is_supported:
        if not expression:
            raise ValueError("Supported result must include a non-empty expression.")

        unresolved_placeholders = ["<literal>", "<value>", "<fixed_literal>", "<input>"]

        if any(placeholder in expression for placeholder in unresolved_placeholders):
            raise ValueError(
                f"Rulebook expression contains unresolved placeholder: {expression!r}."
            )

        if operation_kind == "fixed_literal" and not expression.startswith("VAL_"):
            raise ValueError(
                "operation_kind='fixed_literal' but expression does not start with "
                f"'VAL_': {expression!r}."
            )

        if operation_kind == "source_field" and expression.startswith("VAL_"):
            raise ValueError(
                "operation_kind='source_field' but expression starts with VAL_. "
                "DTO/source fields must not be literals."
            )

    return {
        "evaluator": evaluator,
        "selected_record_ids": selected_record_ids,
        "operation_kind": operation_kind,
        "is_supported": is_supported,
        "expression": expression,
        "reason": reason.strip(),
        "confidence": confidence_float,
    }


# -----------------------------------------------------------------------------
# Semantic consistency validation
# -----------------------------------------------------------------------------


def _check_operation_kind_consistency(
    *,
    operation_type: str,
    operation_kind: str,
    expression: str,
    rhs_request: str,
    user_requirement: str,
) -> str:
    combined_text = f"{rhs_request} {user_requirement}"

    has_conditional_signal = _text_has_any_signal(combined_text, CONDITIONAL_SIGNALS)
    has_source_field_signal = _text_has_any_signal(combined_text, SOURCE_FIELD_SIGNALS)
    has_unit_conversion_signal = _text_has_any_signal(
        combined_text, UNIT_CONVERSION_SIGNALS
    )

    if operation_type == "append_attribute_value":
        if operation_kind not in APPEND_VALUE_OPERATION_KINDS:
            return (
                "The planner operation_type is append_attribute_value, so the response "
                "must provide a valid value-side expression for the new sub-key. Return "
                "operation_kind='append_subkey' and expression as RHS value only."
            )
        return ""

    if has_conditional_signal and operation_kind == "fixed_literal":
        return (
            "The request contains conditional language, so operation_kind='fixed_literal' "
            "is incorrect. Reclassify as mapping and build source#condition|result,ELSE|default."
        )

    if has_source_field_signal and operation_kind == "fixed_literal":
        return (
            "The request contains DTO/source-field language, so operation_kind='fixed_literal' "
            "is incorrect. Reclassify as source_field and do not return VAL_<fieldPath>."
        )

    if has_source_field_signal and operation_kind == "unsupported":
        return (
            "The request contains DTO/source-field language and appears to include a valid path. "
            "Do not reject this only because no old evaluator token exists. Plain paths are "
            "fallback source DTO/JsonPath expressions in the merged rulebook."
        )

    if has_source_field_signal and expression.startswith("VAL_"):
        return (
            "The request asks for a DTO/source field, but the expression starts with VAL_. "
            "VAL_ means literal text, not field lookup."
        )

    if has_unit_conversion_signal and operation_kind == "fixed_literal":
        return (
            "The request contains conversion/type-cast language, so fixed_literal is likely incorrect. "
            "Use the exact rulebook conversion prefix or return unsupported."
        )

    return ""


def _operation_requires_dsl(operation_type: str) -> bool:
    return operation_type in {
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
    }


# -----------------------------------------------------------------------------
# Node entry point
# -----------------------------------------------------------------------------


def dsl_expression_node(state: AdvisorState) -> dict[str, Any]:
    plan = state.get("plan", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    append_key = str(plan.get("append_key", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "")
    user_requirement = str(
        state.get("user_requirement", "") or state.get("requirement", "") or ""
    )

    warnings: list[str] = []
    errors: list[str] = []

    if not _operation_requires_dsl(operation_type):
        expression_result = {
            "did_compile": False,
            "is_supported": True,
            "selected_evaluator": "",
            "selected_record_id": "",
            "selected_record_ids": [],
            "operation_kind": "",
            "original_operation_kind": "",
            "compiled_rhs": "",
            "append_fragment": "",
            "confidence": 0.0,
            "raw_answer": f"DSL expression not required for operation_type={operation_type}.",
            "structured_answer": {},
            "reason": f"DSL expression not required for operation_type={operation_type}.",
            "warnings": warnings,
            "errors": errors,
        }

        return {"expression": expression_result}

    raw_answer: str | dict[str, Any] = ""
    structured_answer: dict[str, Any] = {}
    last_error = ""
    dsl_query = ""

    deterministic_answer = _try_compile_deterministically(state)

    if deterministic_answer is not None:
        raw_answer = deterministic_answer
        structured_answer = _parse_structured_answer(deterministic_answer)
        dsl_query = "RULEBOOK_DETERMINISTIC_COMPILER"
    else:
        correction_note = ""

        for attempt in range(MAX_CLASSIFICATION_RETRIES + 1):
            dsl_query = _build_dsl_query(state, correction_note=correction_note)

            try:
                raw_answer = _call_rulebook_llm(dsl_query)
            except Exception as exc:
                error = f"dsl_expression_node failed while calling rulebook LLM fallback: {exc}"

                expression_result = {
                    "did_compile": False,
                    "is_supported": False,
                    "selected_evaluator": RULEBOOK_EVALUATOR,
                    "selected_record_id": "",
                    "selected_record_ids": [],
                    "operation_kind": "",
                    "original_operation_kind": "",
                    "compiled_rhs": "",
                    "append_fragment": "",
                    "confidence": 0.0,
                    "raw_answer": "",
                    "structured_answer": {},
                    "reason": error,
                    "warnings": warnings,
                    "errors": [error],
                    "dsl_query": dsl_query,
                }

                return {
                    "expression": expression_result,
                    "errors": list(state.get("errors", []) or []) + [error],
                }

            try:
                structured_answer = _parse_structured_answer(raw_answer)
            except ValueError as exc:
                last_error = str(exc)
                structured_answer = {}

                if attempt < MAX_CLASSIFICATION_RETRIES:
                    correction_note = (
                        "Your previous response failed validation with this error: "
                        f"{last_error}. Fix this and return a corrected JSON object "
                        "following the schema exactly."
                    )
                    warnings.append(
                        f"Attempt {attempt + 1} failed JSON validation, retrying: {last_error}"
                    )
                    continue

                expression_result = {
                    "did_compile": False,
                    "is_supported": False,
                    "selected_evaluator": RULEBOOK_EVALUATOR,
                    "selected_record_id": "",
                    "selected_record_ids": [],
                    "operation_kind": "",
                    "original_operation_kind": "",
                    "compiled_rhs": "",
                    "append_fragment": "",
                    "confidence": 0.0,
                    "raw_answer": raw_answer,
                    "structured_answer": {},
                    "reason": last_error,
                    "warnings": warnings,
                    "errors": [last_error],
                    "dsl_query": dsl_query,
                }

                return {
                    "expression": expression_result,
                    "errors": list(state.get("errors", []) or []) + [last_error],
                }

            consistency_issue = _check_operation_kind_consistency(
                operation_type=operation_type,
                operation_kind=structured_answer["operation_kind"],
                expression=structured_answer["expression"],
                rhs_request=rhs_request,
                user_requirement=user_requirement,
            )

            if not consistency_issue:
                break

            last_error = (
                "Semantic consistency check failed: operation_kind="
                f"{structured_answer['operation_kind']!r} does not match the "
                "rulebook language used in the request."
            )

            if attempt < MAX_CLASSIFICATION_RETRIES:
                correction_note = consistency_issue
                warnings.append(
                    f"Attempt {attempt + 1} returned operation_kind="
                    f"{structured_answer['operation_kind']!r} which conflicts with "
                    "rulebook language; retrying with an explicit correction."
                )
                structured_answer = {}
                continue

            expression_result = {
                "did_compile": False,
                "is_supported": False,
                "selected_evaluator": RULEBOOK_EVALUATOR,
                "selected_record_id": "",
                "selected_record_ids": [],
                "operation_kind": structured_answer.get("operation_kind", ""),
                "original_operation_kind": structured_answer.get("operation_kind", ""),
                "compiled_rhs": "",
                "append_fragment": "",
                "confidence": 0.0,
                "raw_answer": raw_answer,
                "structured_answer": structured_answer,
                "reason": (
                    last_error
                    + " Retries exhausted; refusing to auto-correct. Please review "
                    "the request and/or the rulebook prompt manually."
                ),
                "warnings": warnings,
                "errors": [last_error],
                "dsl_query": dsl_query,
            }

            return {
                "expression": expression_result,
                "errors": list(state.get("errors", []) or []) + [last_error],
            }

    # Success path.
    selected_record_ids = structured_answer["selected_record_ids"]
    selected_record_id = ", ".join(selected_record_ids)

    evaluator = structured_answer["evaluator"]
    operation_kind = structured_answer["operation_kind"]
    effective_operation_kind = operation_kind
    is_supported = structured_answer["is_supported"]
    compiled_rhs = structured_answer["expression"]
    reason = structured_answer["reason"]
    confidence = structured_answer["confidence"]

    append_fragment = ""

    if not is_supported:
        errors.append(reason or "Rulebook compiler marked this RHS as unsupported.")

    if is_supported and operation_type == "append_attribute_value":
        if operation_kind != "append_subkey":
            warnings.append(
                "Normalized structured operation_kind "
                f"from {operation_kind!r} to 'append_subkey' because planner "
                "operation_type is append_attribute_value. The expression was kept "
                "unchanged and used as the value side."
            )
            effective_operation_kind = "append_subkey"

        append_fragment = _build_append_fragment(
            append_key=append_key,
            expression=compiled_rhs,
        )

        if not append_fragment:
            errors.append(
                "Could not build append fragment from append key and structured expression."
            )

    if is_supported and operation_type in {"add_attribute", "update_attribute_value"}:
        if operation_kind == "append_subkey":
            errors.append(f"{operation_type} cannot use operation_kind='append_subkey'.")

    did_compile = bool(compiled_rhs) and is_supported and not errors

    expression_result = {
        "did_compile": did_compile,
        "is_supported": is_supported,
        "selected_evaluator": evaluator,
        "selected_record_id": selected_record_id,
        "selected_record_ids": selected_record_ids,
        "operation_kind": effective_operation_kind,
        "original_operation_kind": operation_kind,
        "compiled_rhs": compiled_rhs if did_compile else "",
        "append_fragment": append_fragment if did_compile else "",
        "confidence": confidence if did_compile else 0.0,
        "raw_answer": raw_answer if isinstance(raw_answer, str) else json.dumps(raw_answer, ensure_ascii=False),
        "structured_answer": structured_answer,
        "reason": reason,
        "warnings": warnings,
        "errors": errors,
        "dsl_query": dsl_query,
    }

    updates: dict[str, Any] = {"expression": expression_result}

    if warnings:
        updates["warnings"] = list(state.get("warnings", []) or []) + warnings

    if errors:
        updates["errors"] = list(state.get("errors", []) or []) + errors

    return updates
