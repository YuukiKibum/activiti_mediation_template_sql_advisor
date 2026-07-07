from __future__ import annotations

import re
from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _append_warning(updates: dict[str, Any], state: AdvisorState, message: str) -> None:
    warnings = list(state.get("warnings", []) or [])
    warnings.append(message)
    updates["warnings"] = warnings


def _contains_any(text: str, markers: list[str]) -> bool:
    normalized = f" {_normalize_spaces(text).lower()} "
    return any(marker.lower() in normalized for marker in markers)


def _has_conditional_mapping_signal(text: str) -> bool:
    normalized = f" {_normalize_spaces(text).lower()} "

    strong_markers = [
        " if ",
        " when ",
        " otherwise ",
        " else ",
        " default ",
        " means ",
        " mapping ",
        " map ",
        " map to ",
        " maps to ",
    ]

    return any(marker in normalized for marker in strong_markers)


def _derive_value_source_hint(text: str, operation_type: str) -> str:
    """
    Generic source classification.

    This does not compile expression syntax.
    It only classifies where the RHS value comes from.

    Important:
    Transformation must win over plain DTO because:
    "convert DTO field X from seconds to minutes"
    is not a simple DTO path; it needs transformation rules from RAG.
    """
    normalized = f" {_normalize_spaces(text).lower()} "

    explicit_markers = [
        " val_",
        " $",
        "#",
        "|",
    ]

    session_markers = [
        " session ",
        " session variable ",
        " workflow variable ",
        " runtime variable ",
        " context variable ",
        " contextual variable ",
    ]

    transform_markers = [
        " convert ",
        " converted ",
        " converting ",
        " conversion ",
        " format ",
        " parse ",
        " extract ",
        " replace ",
        " split ",
        " list ",
        " index ",
        " calculate ",
        " multiply ",
        " divide ",
        " seconds ",
        " minutes ",
        " hours ",
        " long ",
        " integer ",
        " boolean ",
        " number ",
        " string ",
        " concatenate ",
        " concat ",
        " join ",
        " camel ",
        " any valid ",
        " first valid ",
        " any true ",
        " all true ",
        " bytes ",
        " kb ",
        " by converting ",
        " using conversion ",
    ]

    dto_json_markers = [
        " dto ",
        " dto field ",
        " dto variable ",
        " dto var ",
        " dto varaible ",
        " dto varibale ",
        " json ",
        " json field ",
        " json path ",
        " json variable ",
        " json varaible ",
        " json varibale ",
        " bespoke json ",
        " payload ",
        " payload field ",
        " source field ",
        " source variable ",
        " from field ",
        " from variable ",
        " from dto ",
        " from json ",
        " from payload ",
        " populate from ",
        " take from ",
        " read from ",
        " use field ",
        " value should come from ",
    ]

    static_markers = [
        " static ",
        " fixed ",
        " hardcoded ",
        " literal ",
        " constant ",
        " with value ",
        " value as ",
        " set value as ",
        " set as ",
        " as ",
    ]

    # Priority order:
    # explicit > conditional > session > transformation > DTO/JSON > static > ambiguous
    if _contains_any(normalized, explicit_markers):
        return "explicit_expression"

    if _has_conditional_mapping_signal(normalized):
        return "conditional_mapping"

    if _contains_any(normalized, session_markers):
        return "session_variable"

    if _contains_any(normalized, transform_markers):
        return "typed_or_transformed_value"

    if _contains_any(normalized, dto_json_markers):
        return "dto_json_path"

    if _contains_any(normalized, static_markers):
        return "static_literal"

    if operation_type in {"append_attribute_value", "add_attribute", "update_attribute_value"}:
        return "ambiguous_value_source"

    return "not_applicable"


def _clean_rhs_words(value: str) -> str:
    """
    Converts user-friendly RHS phrases into the raw RHS candidate.

    This is not expression compilation.
    Example:
    - "dto variable sample" -> "sample"
    - "sample dto variable" -> "sample"
    - "json path $.product.name" -> "$.product.name"
    - "static value Sample" -> "Sample"
    - "by converting DTO field x from seconds to minutes" -> "converting DTO field x from seconds to minutes"
    """
    cleaned = _normalize_spaces(value)

    cleanup_patterns = [
        r"\bwith\s+attribute\s+value\s+as\b",
        r"\battribute\s+value\s+as\b",
        r"\bwith\s+value\s+as\b",
        r"\bvalue\s+as\b",
        r"\bwith\s+value\b",
        r"\bby\s+using\b",
        r"\bby\b",
        r"\busing\b",
        r"\bfrom\s+dto\s+field\b",
        r"\bfrom\s+dto\s+variable\b",
        r"\bfrom\s+dto\s+var\b",
        r"\bfrom\s+json\s+path\b",
        r"\bfrom\s+json\s+field\b",
        r"\bfrom\s+payload\s+field\b",
        r"\bdto\s+field\b",
        r"\bdto\s+variable\b",
        r"\bdto\s+var\b",
        r"\bdto\s+varaible\b",
        r"\bdto\s+varibale\b",
        r"\bjson\s+path\b",
        r"\bjson\s+field\b",
        r"\bjson\s+variable\b",
        r"\bjson\s+varaible\b",
        r"\bjson\s+varibale\b",
        r"\bpayload\s+field\b",
        r"\bsource\s+field\b",
        r"\bstatic\s+value\b",
        r"\bfixed\s+value\b",
        r"\bhardcoded\s+value\b",
        r"\bliteral\s+value\b",
    ]

    for pattern in cleanup_patterns:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(
        r"\b(dto|json|payload|source)\s+(field|variable|var|varaible|varibale|path)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\b(field|variable|var|varaible|varibale)\b$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )

    return _normalize_spaces(cleaned)


def _extract_append_key_rhs_from_value_to_append(value_to_append: str) -> tuple[str, str]:
    """
    Extract append_key and raw_rhs_value from planner value_to_append.

    This is generic intent normalization, not expression syntax compilation.
    """
    text = _normalize_spaces(value_to_append)

    if not text:
        return "", ""

    direct_match = re.match(
        r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<rhs>.+?);?$",
        text,
    )
    if direct_match:
        return (
            direct_match.group("key").strip(),
            _clean_rhs_words(direct_match.group("rhs")),
        )

    phrase_match = re.match(
        r"""
        ^(?P<key>[A-Za-z_][A-Za-z0-9_]*)
        (?:\s+attribute)?
        \s+
        (?P<rhs_phrase>.+)
        $
        """,
        text,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    if phrase_match:
        key = phrase_match.group("key").strip()
        rhs_phrase = phrase_match.group("rhs_phrase").strip()
        return key, _clean_rhs_words(rhs_phrase)

    return "", ""


def _extract_append_from_user_requirement(user_requirement: str) -> tuple[str, str, str]:
    """
    Detect append requests like:

    add ccat_sample_value attribute with value as sample dto variable inside existing poAttributes
    add PreferredNumberFreebieMinutes by converting DTO field x from seconds to minutes inside existing poAttributes

    Returns:
    target_attribute_name, append_key, raw_rhs_value
    """
    text = _normalize_spaces(user_requirement)

    pattern = re.compile(
        r"""
        add\s+
        (?P<append_key>[A-Za-z_][A-Za-z0-9_]*)
        (?:\s+attribute)?
        (?:
            \s+
            (?P<rhs_phrase>
                (?:
                    with\s+attribute\s+value\s+as
                    |attribute\s+value\s+as
                    |with\s+value\s+as
                    |with\s+value
                    |value\s+as
                    |as
                    |from
                    |by
                    |using
                    |converted
                    |converting
                )
                \s+
                .*?
            )
        )?
        \s+
        inside
        \s+
        (?:existing\s+)?
        (?P<target_attribute>[A-Za-z_][A-Za-z0-9_]*)
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)

    if not match:
        return "", "", ""

    target_attribute_name = match.group("target_attribute").strip()
    append_key = match.group("append_key").strip()
    rhs_phrase = (match.group("rhs_phrase") or "").strip()
    raw_rhs_value = _clean_rhs_words(rhs_phrase)

    return target_attribute_name, append_key, raw_rhs_value


def _extract_add_attribute_from_user_requirement(user_requirement: str) -> tuple[str, str]:
    """
    Detect:
    add a new attribute ccat_sample_value with attribute value as dto variable sample
    add a new attribute PreferredNumberFreebieMinutes by converting DTO field x from seconds to minutes

    Returns:
    new_attribute_name, raw_rhs_value
    """
    text = _normalize_spaces(user_requirement)

    pattern = re.compile(
        r"""
        add
        \s+
        (?:a\s+)?
        new
        \s+
        attribute
        \s+
        (?P<attribute_name>[A-Za-z_][A-Za-z0-9_]*)
        (?:
            \s+
            (?P<rhs_phrase>
                (?:
                    with\s+attribute\s+value\s+as
                    |attribute\s+value\s+as
                    |with\s+value\s+as
                    |with\s+value
                    |value\s+as
                    |as
                    |from
                    |by
                    |using
                    |converted
                    |converting
                )
                \s+
                .*
            )
        )?
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)

    if not match:
        return "", ""

    attribute_name = match.group("attribute_name").strip()
    rhs_phrase = (match.group("rhs_phrase") or "").strip()
    raw_rhs_value = _clean_rhs_words(rhs_phrase)

    return attribute_name, raw_rhs_value


def _build_rhs_rag_query(
    state: AdvisorState,
    operation_type: str,
    value_source_hint: str,
    raw_rhs_value: str,
    append_key: str,
    target_attribute_name: str,
) -> str:
    """
    Build a RAG query focused on RHS expression rules, not final SQL shape.

    This intentionally avoids hardcoding advanced syntax.
    It asks retrieval for the relevant guide section.
    """
    base_parts = [
        state.get("user_requirement", ""),
        state.get("rag_query", ""),
        operation_type,
        value_source_hint,
        raw_rhs_value,
        append_key,
        target_attribute_name,
    ]

    rhs_focus = """
RHS expression compilation rules only.
Do not retrieve only final SQL examples.
Retrieve exact Activiti expression syntax rules for:
static literal
DTO JSON path
session variable
explicit expression
conditional mapping
typed transformation
list handling
index handling
any valid
any true
all true
map object
date format
replace
concat
math
boolean conversion
number extraction
string extraction
time unit conversion
seconds conversion
minutes conversion
long conversion

For append operation, retrieve rule for RHS and append fragment shape separately:
RHS value becomes compiled_rhs.
Append assembler later creates append_key=compiled_rhs;

Do not use generic SQL function syntax unless that exact syntax is in the guide.
Use only exact tokens or method directives from retrieved Master RAG Guide context.
"""

    return _normalize_spaces(
        " ".join(str(part) for part in base_parts if part) + " " + rhs_focus
    )


def intent_normalization_node(state: AdvisorState) -> dict[str, Any]:
    operation_type = state.get("operation_type", "unknown")
    user_requirement = state.get("user_requirement", "")

    updates: dict[str, Any] = {}

    target_attribute_name = str(
        state.get("target_attribute_name", "") or state.get("attribute_name", "") or ""
    ).strip()

    append_key = str(state.get("append_key", "") or "").strip()
    raw_rhs_value = str(state.get("raw_rhs_value", "") or "").strip()

    if operation_type == "append_attribute_value":
        extracted_target, extracted_key, extracted_rhs = _extract_append_from_user_requirement(
            user_requirement
        )

        if extracted_target:
            target_attribute_name = extracted_target

        if extracted_key:
            append_key = extracted_key

        if extracted_rhs:
            raw_rhs_value = extracted_rhs

        if not append_key or not raw_rhs_value:
            value_to_append = str(state.get("value_to_append", "") or "").strip()
            extracted_key, extracted_rhs = _extract_append_key_rhs_from_value_to_append(
                value_to_append
            )

            if extracted_key and not append_key:
                append_key = extracted_key

            if extracted_rhs and not raw_rhs_value:
                raw_rhs_value = extracted_rhs

        updates["target_attribute_name"] = target_attribute_name
        updates["attribute_name"] = target_attribute_name
        updates["append_key"] = append_key
        updates["raw_rhs_value"] = raw_rhs_value

    elif operation_type == "add_attribute":
        new_attribute_name = str(
            state.get("new_attribute_name", "") or state.get("attribute_name", "") or ""
        ).strip()

        extracted_attribute, extracted_rhs = _extract_add_attribute_from_user_requirement(
            user_requirement
        )

        if extracted_attribute:
            new_attribute_name = extracted_attribute

        if extracted_rhs:
            raw_rhs_value = extracted_rhs
        elif not raw_rhs_value:
            raw_rhs_value = _clean_rhs_words(str(state.get("new_attribute_value", "") or ""))

        updates["new_attribute_name"] = new_attribute_name
        updates["attribute_name"] = new_attribute_name
        updates["raw_rhs_value"] = raw_rhs_value
        updates["target_attribute_name"] = new_attribute_name

    elif operation_type == "update_attribute_value":
        target_attribute_name = str(
            state.get("target_attribute_name", "") or state.get("attribute_name", "") or ""
        ).strip()

        if not raw_rhs_value:
            raw_rhs_value = _clean_rhs_words(str(state.get("new_attribute_value", "") or ""))

        updates["target_attribute_name"] = target_attribute_name
        updates["attribute_name"] = target_attribute_name
        updates["raw_rhs_value"] = raw_rhs_value

    else:
        updates["target_attribute_name"] = target_attribute_name
        updates["raw_rhs_value"] = raw_rhs_value

    classification_text = " ".join(
        str(part)
        for part in [
            user_requirement,
            state.get("value_to_append", ""),
            state.get("new_attribute_value", ""),
            updates.get("raw_rhs_value", ""),
        ]
        if part
    )

    value_source_hint = _derive_value_source_hint(
        text=classification_text,
        operation_type=operation_type,
    )

    updates["value_source_hint"] = value_source_hint

    updates["rag_query"] = _build_rhs_rag_query(
        state={**state, **updates},
        operation_type=operation_type,
        value_source_hint=value_source_hint,
        raw_rhs_value=updates.get("raw_rhs_value", ""),
        append_key=updates.get("append_key", ""),
        target_attribute_name=updates.get("target_attribute_name", ""),
    )

    if operation_type == "append_attribute_value" and not updates.get("append_key"):
        _append_warning(
            updates,
            state,
            "Intent normalization could not determine append_key for append operation.",
        )

    if operation_type in {"append_attribute_value", "add_attribute", "update_attribute_value"}:
        if not updates.get("raw_rhs_value"):
            _append_warning(
                updates,
                state,
                "Intent normalization could not determine raw_rhs_value.",
            )

    return updates