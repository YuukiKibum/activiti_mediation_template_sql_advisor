from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from activiti_mediation_template_sql_advisor.dsl_rag.answer import answer
from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_rulebook import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "mediation_sql_agent_prompt.md"
)

ALLOWED_EVALUATORS = {"A", "B", "C"}

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
# is a composite/container attribute such as poAttributes. The LLM may still
# describe the value side as fixed_literal/source_field/mapping/etc. That is
# acceptable: Python will wrap the value side as append_key=<expression>;.
APPEND_VALUE_OPERATION_KINDS = {
    "append_subkey",
    "fixed_literal",
    "source_field",
    "mapping",
    "unit_conversion_or_cast",
    "concat",
}

# Keyword signals used ONLY for a post-hoc consistency check against the
# LLM's own operation_kind classification -- never used to construct or
# override an expression directly. If the LLM's classification disagrees
# with these signals, we ask it to reclassify (bounded retry) rather than
# silently trusting or silently overriding.
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

MAX_CLASSIFICATION_RETRIES = 1


def _load_agent_prompt() -> str:
    """
    Load the project SQL-agent prompt supplied by the user.

    This prompt contains project-specific rules:
    - do not guess TEMPLATE_ID
    - use DSL KB
    - inspect Oracle examples
    - preserve composite ATTRIBUTE_VALUE strings
    - do not guess PARAM_ID for inserts
    """
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception:
        return ""


def _select_evaluator_hint(state: AdvisorState) -> str:
    """
    Cheap retrieval hint only.

    Important:
    This is NOT the final evaluator decision.
    The structured JSON response's "evaluator" field is authoritative.

    This hint only narrows DSL KB retrieval before the LLM/RAG call.
    """
    plan = state.get("plan", {}) or {}

    operation_type = str(plan.get("operation_type", "") or "")
    rhs_request = str(plan.get("rhs_request", "") or "").lower()

    if operation_type == "append_attribute_value":
        return "B"

    conditional_or_mapping_signals = [
        "if ",
        " else ",
        "when ",
        "map",
        "mapping",
        "otherwise",
        "convert",
        "from dto",
        "from dto field",
        "dto field",
        "dto filed",
        "source field",
        "input field",
    ]

    if any(signal in rhs_request for signal in conditional_or_mapping_signals):
        return "B"

    if any(symbol in rhs_request for symbol in ["#", "$.", "$eval_", "|"]):
        return "B"

    return "A"


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
            "Match delimiter style, VAL_ usage, mapping shape, and $. prefix style where relevant.",
        ]
    )

    return "\n".join(lines)


def _structured_output_contract() -> str:
    """
    Prompt contract for the DSL/RAG answer.

    The model must return JSON only.
    Python will parse JSON and will not regex-scrape prose.
    """
    return """
Return ONLY one JSON object.
Do not include markdown fences.
Do not include prose before or after the JSON.

The JSON object must match this exact schema:

{
  "evaluator": "A",
  "selected_record_ids": ["<kb record id>"],
  "operation_kind": "fixed_literal",
  "is_supported": true,
  "expression": "<exact final RHS DSL expression, or empty string if unsupported>",
  "reason": "<short explanation for logs/human display only>",
  "confidence": 1.0
}

Allowed evaluator values:
- "A"
- "B"
- "C"

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
with NO if/else, when/then, map, otherwise, conversion, or concat language
anywhere in the request. If the request contains ANY conditional language
(if / else / when / then / otherwise / map), you MUST NOT use fixed_literal,
even if the underlying values look simple (e.g. "false" or "true") --
use "mapping" instead.
Expression must be exactly:
VAL_<literal>
Preserve the literal exactly as given, including case and spaces.

Example:
add attribute gundu with value 123
=> operation_kind: fixed_literal
=> expression: VAL_123

2. source_field

Use this when the request says:
- DTO field
- DTO filed
- from DTO
- from DTO field
- source field
- input field
- take from field

A source_field means the ATTRIBUTE_VALUE should read from an input/source path.
It is NOT a literal.

Expression must be the field/path expression supported by the rulebook and KB.
Usually this is the plain path, for example:
allowances.sms.freebies

If the KB/evaluator examples require a leading $. for this template/evaluator, this is also acceptable:
$.allowances.sms.freebies

Never return VAL_<fieldPath> for DTO/source-field requests.
VAL_ means literal text, not field lookup.

Important source_field evaluator rule:
A plain DTO/source path does NOT require a special evaluator token.
The ATTRIBUTE_VALUE rulebook says that if no known prefix matches, the value is
treated as a direct JsonPath/source DTO expression.

Therefore, for a request like:
"add attribute gundu with dto field allowances.sms.freebies"

Correct:
operation_kind: source_field
expression: allowances.sms.freebies

Wrong:
operation_kind: unsupported
reason: "No evaluator A token exists for DTO field"

Why wrong:
Plain source paths are fallback ATTRIBUTE_VALUE expressions. They are not B/C-only
tokens. Only return unsupported if the source field name itself is invalid or
ambiguous, or the user asks for a transformation whose DSL syntax is not
confirmed.

Example:
For prepaid base plan rtf template, add a new attribute gundu with dto field allowances.sms.freebies
=> operation_kind: source_field
=> expression: allowances.sms.freebies

Wrong:
=> operation_kind: fixed_literal
=> expression: VAL_allowances.sms.freebies

If the text after DTO field is not a valid field-like name, for example just "123", return:
operation_kind: unsupported
is_supported: false
expression: ""

3. mapping

Use this whenever the request contains conditional language such as:

if X show Y else Z
if X set Y otherwise Z
map A to B
when X then Y otherwise Z

This applies EVEN IF the two branch results are simple literals like true/false or 1/0. The presence of a condition makes it a mapping, not a fixed_literal.

Build the expression using the KB-supported mapping shape:

<path>#<key1>|<result1>,ELSE|<resultElse>

The presence or absence of leading $. must follow the selected evaluator rule from the KB records. Include the KB record IDs that justify this in selected_record_ids.

Important mapping source-path rule:

For mapping expressions, the text before # must be the source/input field from the condition clause.

The source path must come from:

* the field after "if"
* the field after "when"
* the field being mapped

Never use these as the source path before #:

* target ATTRIBUTE_NAME
* new_attribute_name
* append_key
* output attribute name

Example:

User request:

"For Prepaid Base Plan RTF request, add a new attribute AddToBillFlagCopy. If addToBill is false set false, otherwise true."

Correct:

addToBill#false|false,ELSE|true

Wrong:

AddToBillFlagCopy#false|false,ELSE|true

Why wrong:

AddToBillFlagCopy is the target/new ATTRIBUTE_NAME. It is not the source field being evaluated.

Mapping expression slot rule:

For condition text like:

If <sourceField> is <conditionValue> set/show/send <resultValue>, otherwise <elseValue>

The expression MUST be:

<sourceField>#<conditionValue>|<resultValue>,ELSE|<elseValue>

Do not omit the conditionValue.

Do not write:

<sourceField>#<resultValue>,ELSE|<elseValue>

Example:

If yuuki is false set maakhidi, otherwise gungudu.

Correct:

yuuki#false|maakhidi,ELSE|gungudu

Wrong:

yuuki#maakhidi,ELSE|gungudu

Why wrong:

false is the conditionValue. maakhidi is the resultValue. Both are required in the mapping expression.

When building a mapping, identify four separate parts:

1. sourceField: the field after "if" or "when"
2. conditionValue: the value after "is", "equals", or "="
3. resultValue: the value after "set", "show", "send", "return", or "then"
4. elseValue: the value after "else" or "otherwise"

Then assemble:

sourceField#conditionValue|resultValue,ELSE|elseValue

More examples:

If addToBill is false set false, otherwise true.

Correct:

addToBill#false|false,ELSE|true

Wrong:

VAL_false
VAL_true
AddToBillFlagCopy#false|false,ELSE|true
addToBill#false,ELSE|true

If subscriberType is PREPAID show 1 else 0.

Correct:

subscriberType#PREPAID|1,ELSE|0

Wrong:

subscriberType#1,ELSE|0
CustomerType#PREPAID|1,ELSE|0

For append_subkey requests, the expression is still only the RHS value.

Example:

User request:

"For Prepaid Base Plan ECM request, add CustomerType with value if subscriberType is PREPAID show 1 else 0 inside existing poAttributes."

Correct expression:

subscriberType#PREPAID|1,ELSE|0

Wrong expression:

CustomerType#PREPAID|1,ELSE|0

Why wrong:

CustomerType is the append key/output sub-key. subscriberType is the source/input field from the condition.

The Python caller will later wrap the append result as:

CustomerType=subscriberType#PREPAID|1,ELSE|0;

Therefore, for append_subkey, do not include append_key= and do not include a trailing semicolon in the JSON expression field.

4. unit_conversion_or_cast
Use this when the request asks for a data-size conversion, time-unit conversion,
or type cast.

Use only exact tokens confirmed in the KB.
If the exact conversion direction is not supported, return:
operation_kind: "unsupported"
is_supported: false
expression: ""
and include the relevant unsupported KB record ID if available.

5. concat
Use this when the request asks to combine multiple fields or literals.
Use the KB-supported CONCAT syntax only.

6. append_subkey
Use this when the request adds or changes one key inside an existing composite
attribute such as poAttributes.

Use operation_kind="append_subkey" whenever the planner operation_type is
append_attribute_value, or whenever the user says things like:
- inside existing poAttributes
- inside poAttributes
- within existing poAttributes
- add <key> inside existing <container attribute>

This is true even when the sub-key value itself is a fixed literal.

Example:
For Prepaid Base Plan ECM request, add CustomerType with value 123 inside existing poAttributes.
=> operation_kind: append_subkey
=> expression: VAL_123

Wrong:
=> operation_kind: fixed_literal
=> expression: VAL_123

Why wrong:
The value 123 is a fixed literal, but the overall RHS task is append_subkey
because it is being added inside an existing composite/container attribute.

For append_subkey requests, the expression is still only the RHS value. 
If the user says:
"add CustomerType with value if subscriberType is PREPAID show 1 else 0 inside existing poAttributes"

Correct expression:
subscriberType#PREPAID|1,ELSE|0

Wrong expression:
CustomerType#PREPAID|1,ELSE|0

Why:
CustomerType is the append key/output sub-key. subscriberType is the source/input field from the condition.

The expression field must contain ONLY the value side for that sub-key.
Do not include:
- append_key=
- trailing semicolon

The Python caller will wrap it as:
append_key=<expression>;

7. DTO field/source-field rule:

If the request says "DTO field", "DTO filed", "from DTO", "from DTO field",
"source field", "input field", or "take from DTO", do NOT classify it as
fixed_literal.

A DTO field means the RHS should reference an input/source field using the
rulebook/KB-supported syntax. Use operation_kind="source_field" for simple
direct source-field reads.

Only use fixed_literal when the user gives a concrete unconditional value like:
"value 123"
"value false"
"value Base Plan"

If the text after "DTO field" is not a valid field-like name, for example "123",
return operation_kind="unsupported", is_supported=false, expression="", and explain:
"DTO field name appears invalid or ambiguous."

Do not treat numbers after "DTO field" as fixed literals.
"with DTO field 123" is ambiguous/invalid, not VAL_123.

8. unsupported
Use this for anything with no matching KB token.
Return:
operation_kind: "unsupported"
is_supported: false
expression: ""
reason: explain what is missing
"""


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

    project_prompt = _load_agent_prompt()
    oracle_samples_text = _format_oracle_samples_for_dsl(state)

    try:
        rulebook_summary = get_rulebook_prompt_summary()
    except Exception as exc:
        rulebook_summary = f"ATTRIBUTE_VALUE rulebook could not be loaded: {exc}"

    parts = [
        "You are compiling ONLY the RHS ATTRIBUTE_VALUE expression for ACT_MEDIATION_PARAMETER.",
        "",
        _structured_output_contract(),
        "",
        "ATTRIBUTE_VALUE rulebook summary:",
        rulebook_summary,
        "",
    ]

    if project_prompt:
        parts.extend(
            [
                "Project SQL-agent prompt/rules:",
                project_prompt,
                "",
            ]
        )

    parts.extend(
        [
            "Current request context:",
            f"Full user requirement: {user_requirement}",
            f"Planner operation_type: {operation_type}",
            f"Template ID: {template.get('template_id', '')}",
            f"Template external system: {template.get('external_system', '')}",
            f"Attribute name: {attribute_name}",
            f"New attribute name: {new_attribute_name}",
            f"RHS request from planner: {rhs_request}",
        ]
    )

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
        parts.extend(
            [
                "",
                oracle_samples_text,
            ]
        )

    if correction_note:
        parts.extend(
            [
                "",
                "CORRECTION FROM A PREVIOUS ATTEMPT (read carefully, your prior answer was wrong):",
                correction_note,
            ]
        )

    return "\n".join(parts)


def _strip_json_fences(raw_answer: str) -> str:
    """
    Strip accidental markdown fences.

    This is not expression scraping.
    It only unwraps a full JSON object if the model accidentally puts it in
    ```json fences.
    """
    text = (raw_answer or "").strip()

    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    return text


def _parse_structured_answer(raw_answer: str) -> dict[str, Any]:
    """
    Parse the structured JSON object returned by answer().

    Raises:
        ValueError with a clear message if parsing or validation fails.

    Important:
    This intentionally does NOT fall back to regex extraction.
    A malformed structured answer should be loud and visible.
    """
    text = _strip_json_fences(raw_answer)

    if not text:
        raise ValueError("DSL RAG returned an empty response; expected JSON object.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"DSL RAG did not return valid JSON: {exc.msg}. Raw answer: {raw_answer}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("DSL RAG JSON must be an object.")

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
            "DSL RAG JSON is missing required keys: " + ", ".join(missing_keys)
        )

    evaluator = data["evaluator"]

    if not isinstance(evaluator, str) or evaluator not in ALLOWED_EVALUATORS:
        raise ValueError(
            f"DSL RAG JSON has invalid evaluator={evaluator!r}; expected one of {sorted(ALLOWED_EVALUATORS)}."
        )

    selected_record_ids = data["selected_record_ids"]

    if not isinstance(selected_record_ids, list) or not all(
        isinstance(item, str) for item in selected_record_ids
    ):
        raise ValueError("DSL RAG JSON selected_record_ids must be a list of strings.")

    operation_kind = data["operation_kind"]

    if not isinstance(operation_kind, str) or operation_kind not in ALLOWED_OPERATION_KINDS:
        raise ValueError(
            f"DSL RAG JSON has invalid operation_kind={operation_kind!r}; "
            f"expected one of {sorted(ALLOWED_OPERATION_KINDS)}."
        )

    is_supported = data["is_supported"]

    if not isinstance(is_supported, bool):
        raise ValueError("DSL RAG JSON is_supported must be a boolean.")

    expression = data["expression"]

    if not isinstance(expression, str):
        raise ValueError("DSL RAG JSON expression must be a string.")

    reason = data["reason"]

    if not isinstance(reason, str):
        raise ValueError("DSL RAG JSON reason must be a string.")

    confidence = data["confidence"]

    if not isinstance(confidence, (int, float)):
        raise ValueError("DSL RAG JSON confidence must be a number.")

    confidence_float = float(confidence)

    if confidence_float < 0.0 or confidence_float > 1.0:
        raise ValueError("DSL RAG JSON confidence must be between 0.0 and 1.0.")

    expression = expression.strip()

    if operation_kind == "unsupported" and is_supported:
        raise ValueError(
            "DSL RAG JSON operation_kind='unsupported' requires is_supported=false."
        )

    if not is_supported and expression:
        raise ValueError("DSL RAG JSON unsupported result must use an empty expression.")

    if is_supported:
        if not expression:
            raise ValueError("DSL RAG JSON supported result must include a non-empty expression.")

        unresolved_placeholders = ["<literal>", "<value>", "<fixed_literal>", "<input>"]

        if any(placeholder in expression for placeholder in unresolved_placeholders):
            raise ValueError(
                f"DSL RAG JSON expression contains unresolved placeholder: {expression!r}."
            )

        # A fixed_literal expression must actually look like VAL_<something>.
        # This catches the model picking "fixed_literal" but returning
        # mapping-shaped syntax (or vice versa is caught by the consistency
        # check below, not here).
        if operation_kind == "fixed_literal" and not expression.startswith("VAL_"):
            raise ValueError(
                "DSL RAG JSON operation_kind='fixed_literal' but expression does not "
                f"start with 'VAL_': {expression!r}."
            )

        if operation_kind == "source_field" and expression.startswith("VAL_"):
            raise ValueError(
                "DSL RAG JSON operation_kind='source_field' but expression starts "
                f"with 'VAL_': {expression!r}. DTO/source fields must not be literals."
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


def _text_has_any_signal(text: str, signals: list[str]) -> bool:
    lowered = f" {text.lower()} "
    return any(signal in lowered for signal in signals)


def _check_operation_kind_consistency(
    *,
    operation_type: str,
    operation_kind: str,
    expression: str,
    rhs_request: str,
    user_requirement: str,
) -> str:
    """
    Best-effort SEMANTIC sanity check on top of the already-valid JSON.

    This does NOT construct or override any expression. It only decides
    whether the LLM's own classification should be trusted, or whether we
    should ask it to reclassify. Returns an empty string if consistent, or a
    human-readable correction instruction to feed back into a retry prompt.

    Important append rule:
    For append_attribute_value, the planner already knows the target is a
    composite/container attribute. Therefore a value-side kind such as mapping
    or fixed_literal is acceptable as long as the expression itself is a valid
    RHS value. Python will normalize the final operation_kind to append_subkey
    and wrap it as append_key=<expression>; later.
    """
    combined_text = f"{rhs_request} {user_requirement}"

    has_conditional_signal = _text_has_any_signal(combined_text, CONDITIONAL_SIGNALS)
    has_source_field_signal = _text_has_any_signal(combined_text, SOURCE_FIELD_SIGNALS)
    has_unit_conversion_signal = _text_has_any_signal(
        combined_text, UNIT_CONVERSION_SIGNALS
    )

    if has_conditional_signal and operation_kind == "fixed_literal":
        if operation_type == "append_attribute_value":
            return (
                "The request contains conditional language and is an append operation. "
                "Return operation_kind='append_subkey' and put only the conditional "
                "mapping expression in expression, for example "
                "subscriberType#PREPAID|1,ELSE|0. Do not return VAL_<literal>."
            )

        return (
            "The request contains conditional language (if/else/when/then/otherwise/map), "
            "so operation_kind='fixed_literal' is incorrect. Reclassify this as "
            "operation_kind='mapping' and build a <path>#<key>|<result>,ELSE|<default> "
            "style expression instead of a VAL_<literal> expression. Do not use "
            "fixed_literal just because the branch results themselves are simple "
            "values like true/false or 1/0 -- the presence of a condition is what "
            "matters, not the simplicity of the outcomes."
        )

    if has_source_field_signal and operation_kind == "fixed_literal":
        return (
            "The request contains DTO/source-field language such as 'DTO field', "
            "'from DTO', or 'source field', so operation_kind='fixed_literal' is "
            "incorrect. Reclassify this as operation_kind='source_field'. The "
            "ATTRIBUTE_VALUE rulebook supports direct source-field syntax through "
            "fallback JsonPath/source DTO resolution. Do not return VAL_<fieldPath> "
            "for DTO/source fields."
        )

    if has_source_field_signal and operation_kind == "unsupported":
        return (
            "The request contains DTO/source-field language and the supplied field path "
            "looks like a valid source path. Do not reject this only because there is no "
            "special evaluator token. The ATTRIBUTE_VALUE rulebook says plain paths are "
            "fallback source DTO/JsonPath expressions when no prefix matches. Reclassify "
            "this as operation_kind='source_field' and return the plain path expression, "
            "for example allowances.sms.freebies or $.allowances.sms.freebies."
        )

    if has_source_field_signal and expression.startswith("VAL_"):
        return (
            "The request asks for a DTO/source field, but the expression starts with VAL_. "
            "VAL_ means literal text, not field lookup. Return the source path according "
            "to the rulebook, such as allowances.sms.freebies or $.allowances.sms.freebies."
        )

    if has_unit_conversion_signal and operation_kind == "fixed_literal":
        return (
            "The request contains unit-conversion or type-cast language (convert, "
            "seconds/minutes/hours, cast to, as a long/integer/double, or a "
            "byte/KB/MB/GB size unit), so operation_kind='fixed_literal' is likely "
            "incorrect. Reclassify this as operation_kind='unit_conversion_or_cast' "
            "(or operation_kind='unsupported' if no KB token performs the exact "
            "requested conversion) instead of returning a VAL_<literal> expression."
        )

    if operation_type == "append_attribute_value":
        if operation_kind not in APPEND_VALUE_OPERATION_KINDS:
            return (
                "The planner operation_type is append_attribute_value, so the response "
                "must provide a valid value-side expression for the new sub-key. Return "
                "operation_kind='append_subkey' if possible. A value-side kind such as "
                "mapping, source_field, fixed_literal, unit_conversion_or_cast, or concat "
                "is also acceptable only if expression contains the RHS value. Do not "
                "return unsupported unless the RHS syntax truly cannot be represented."
            )

        # Accept mapping/fixed_literal/source_field/etc. for append operations.
        # The final success path will normalize the operation_kind to append_subkey
        # because the planner already decided this is an append into a composite row.
        return ""

    return ""


def _build_append_fragment(append_key: str, expression: str) -> str:
    """
    Build key=value; for composite ATTRIBUTE_VALUE updates.

    The structured LLM response must provide expression as value-only.
    This function adds the append key wrapper.
    """
    append_key = (append_key or "").strip()
    expression = (expression or "").strip()

    if not append_key or not expression:
        return ""

    return f"{append_key}={expression};"


def _operation_requires_dsl(operation_type: str) -> bool:
    return operation_type in {
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
    }


def _call_answer(dsl_query: str, evaluator_hint: str) -> str:
    try:
        raw_answer = answer(dsl_query, evaluator=evaluator_hint)
    except TypeError:
        raw_answer = answer(dsl_query)

    return str(raw_answer or "")


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

    evaluator_hint = _select_evaluator_hint(state)

    correction_note = ""
    raw_answer = ""
    structured_answer: dict[str, Any] = {}
    last_error = ""
    dsl_query = ""

    for attempt in range(MAX_CLASSIFICATION_RETRIES + 1):
        dsl_query = _build_dsl_query(state, correction_note=correction_note)

        try:
            raw_answer = _call_answer(dsl_query, evaluator_hint)
        except Exception as exc:
            error = f"dsl_expression_node failed while calling DSL RAG: {exc}"

            expression_result = {
                "did_compile": False,
                "is_supported": False,
                "selected_evaluator": evaluator_hint,
                "selected_record_id": "",
                "selected_record_ids": [],
                "operation_kind": "",
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
                "selected_evaluator": evaluator_hint,
                "selected_record_id": "",
                "selected_record_ids": [],
                "operation_kind": "",
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

        # JSON parsed and passed schema validation. Now run the semantic
        # consistency check -- this is the piece that catches "if X else Y"
        # being misclassified as fixed_literal/VAL_.
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
            "language used in the request."
        )

        if attempt < MAX_CLASSIFICATION_RETRIES:
            correction_note = consistency_issue
            warnings.append(
                f"Attempt {attempt + 1} returned operation_kind="
                f"{structured_answer['operation_kind']!r} which conflicts with "
                "request/rulebook language; retrying with an explicit correction."
            )
            structured_answer = {}
            continue

        # Retries exhausted and the model still disagrees with the
        # deterministic signal. Do NOT silently accept the mismatched
        # classification, and do NOT silently override it ourselves --
        # surface this as a compile failure for human review instead.
        expression_result = {
            "did_compile": False,
            "is_supported": False,
            "selected_evaluator": evaluator_hint,
            "selected_record_id": "",
            "selected_record_ids": [],
            "operation_kind": structured_answer.get("operation_kind", ""),
            "compiled_rhs": "",
            "append_fragment": "",
            "confidence": 0.0,
            "raw_answer": raw_answer,
            "structured_answer": structured_answer,
            "reason": (
                last_error
                + " Retries exhausted; refusing to auto-correct. Please review "
                "the request and/or the DSL RAG prompt manually."
            ),
            "warnings": warnings,
            "errors": [last_error],
            "dsl_query": dsl_query,
        }

        return {
            "expression": expression_result,
            "errors": list(state.get("errors", []) or []) + [last_error],
        }

    # Success path: structured_answer is valid AND passed the consistency check.
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
        errors.append(reason or "DSL RAG marked this RHS as unsupported.")

    if is_supported and operation_type == "append_attribute_value":
        if operation_kind != "append_subkey":
            # This is a safe normalization, not an expression rewrite. The planner
            # already decided this is an append into a composite ATTRIBUTE_VALUE;
            # the LLM often describes the value side as mapping/fixed_literal/etc.
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
        "raw_answer": raw_answer,
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