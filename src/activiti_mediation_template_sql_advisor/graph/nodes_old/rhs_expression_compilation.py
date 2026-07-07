from __future__ import annotations

import os
from dotenv import load_dotenv, load_ipython_extension
import re
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState

load_dotenv()

RHS_EXPRESSION_COMPILER_SYSTEM_PROMPT = """
You are the RHS Expression Compiler for the Activiti Mediation Template SQL Advisor.

Your job is to compile ONLY the right-hand-side ATTRIBUTE_VALUE expression.

You must not assemble final database operation shape.

Critical rule:
Return only compiled_rhs.

Do not return:
- key=value;
- attribute_name=value;
- append_key=value;
- SQL
- TO_CLOB(...)
- UPDATE statements
- INSERT statements

The operation shape is handled later by deterministic Python code.

Source-of-truth rule:
Use only the retrieved Master RAG Guide context.
Do not rely on general memory.
Do not invent unsupported Activiti expression tokens.
Do not invent SQL, Java, JavaScript, Python, or pseudo-code functions.

For append_attribute_value:
append_key: ccat_sample_value
raw_rhs_value: sample
value_source_hint: dto_json_path

Your output:
compiled_rhs = sample

Later Python will assemble:
ccat_sample_value=sample;

For add_attribute:
attribute_name: ccat_sample_value
raw_rhs_value: sample
value_source_hint: dto_json_path

Your output:
compiled_rhs = sample

Later Python will store:
ATTRIBUTE_NAME = ccat_sample_value
ATTRIBUTE_VALUE = sample

For static_literal:
Use static literal syntax only if retrieved context supports it.

For dto_json_path:
Use direct DTO/JSON field/path syntax only if retrieved context supports it.
Do not use VAL_.

For session_variable:
Use session syntax only if retrieved context supports it.
Do not use VAL_.

For explicit_expression:
Preserve the expression only if retrieved context supports the pattern.

For conditional_mapping:
Apply only the mapping grammar found in retrieved context.
Retrieved examples are grammar examples only.
Do not copy variable names, field names, condition values, or output values from a retrieved
example unless those exact values appear in the user request or normalized intent.
Do not return a comma-separated list of extracted terms.
If the retrieved context does not clearly support the required mapping grammar,
return did_compile=false.

For typed_or_transformed_value:
Use only exact syntax found in retrieved Master RAG Guide context.
Do not invent generic function-call syntax.
Do not invent arithmetic syntax.
Do not invent method chaining.
Do not convert the request into SQL-style, Java-style, JavaScript-style, Python-style,
or pseudo-code transformations.
If the guide supports a token or method directive, use that exact guide syntax.
If the retrieved context does not clearly support the requested transformation syntax,
return did_compile=false.

Value source priority:
1. explicit_expression
2. conditional_mapping
3. session_variable
4. typed_or_transformed_value
5. dto_json_path
6. static_literal
7. ambiguous_value_source

Output contract:
- compiled_rhs must be only the RHS expression.
- compiled_rhs must not contain the append key followed by equals.
- compiled_rhs must not include the target ATTRIBUTE_NAME as a wrapper.
- compiled_rhs must be exactly the expression that belongs in ATTRIBUTE_VALUE for add/update,
  or exactly the RHS part that will be wrapped for append.
- compiled_rhs may contain expression-specific separators only if the retrieved guide supports them.
- compiled_rhs must not be a copied example with unrelated field names or unrelated values.
- compiled_rhs must not be a plain comma-separated extraction of user terms.
- compiled_rhs must not contain unsupported function-call syntax.

Return only the structured output.
"""


class RhsExpressionDecision(BaseModel):
    did_compile: bool = Field(
        description="Whether RHS expression compilation succeeded using retrieved context."
    )

    value_source_category: str = Field(
        default="",
        description=(
            "The final source category used: static_literal, dto_json_path, session_variable, "
            "explicit_expression, conditional_mapping, typed_or_transformed_value, or "
            "ambiguous_value_source."
        ),
    )

    raw_rhs_value: str = Field(
        default="",
        description="The raw RHS value interpreted from the user request.",
    )

    compiled_rhs: str = Field(
        default="",
        description=(
            "The compiled RHS expression only. Must not include append_key=, "
            "attribute_name=, SQL, or TO_CLOB."
        ),
    )

    rule_source: str = Field(
        default="",
        description="The retrieved Master RAG Guide section/rule used.",
    )

    rule_evidence: str = Field(
        default="",
        description="Brief evidence from retrieved context. Do not invent.",
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence that compiled_rhs follows retrieved context.",
    )

    reasoning: str = Field(
        default="",
        description="Short reasoning explaining the RHS compilation decision.",
    )

    warnings: list[str] = Field(default_factory=list)


def _get_rhs_compiler_llm():
    llm = init_chat_model(
        os.getenv("OPENAI_MODEL", "gpt-4.1-nano"),
        model_provider="openai",
        temperature=0,
    )
    return llm.with_structured_output(RhsExpressionDecision)


def _extract_context_text(item: Any) -> str:
    if item is None:
        return ""

    if isinstance(item, str):
        return item

    if isinstance(item, dict):
        for key in ("page_content", "content", "text", "document", "chunk"):
            value = item.get(key)
            if value:
                return str(value)

        doc = item.get("doc") or item.get("document")
        if doc is not None:
            return str(getattr(doc, "page_content", doc))

    return str(getattr(item, "page_content", item))


def _extract_context_source(item: Any) -> str:
    if item is None:
        return "unknown"

    if isinstance(item, dict):
        metadata = item.get("metadata") or {}
        source_file = (
            item.get("source_file")
            or item.get("source")
            or metadata.get("source_file")
            or metadata.get("source")
        )
        if source_file:
            return str(source_file)

    metadata = getattr(item, "metadata", None) or {}
    return str(metadata.get("source_file") or metadata.get("source") or "unknown")


def _extract_context_score(item: Any) -> str:
    if isinstance(item, dict):
        score = item.get("score")
        if score is not None:
            return str(score)

    return ""


def _format_rag_context(rag_context: Any) -> str:
    if not rag_context:
        return ""

    if not isinstance(rag_context, list):
        rag_context = [rag_context]

    chunks: list[str] = []

    for index, item in enumerate(rag_context, start=1):
        text = _extract_context_text(item).strip()

        if not text:
            continue

        source = _extract_context_source(item)
        score = _extract_context_score(item)

        chunks.append(
            "\n".join(
                [
                    f"--- Retrieved Context Chunk {index} ---",
                    f"Source: {source}",
                    f"Score: {score or 'not provided'}",
                    text,
                ]
            )
        )

    return "\n\n".join(chunks)


def _operation_needs_rhs_compilation(operation_type: str) -> bool:
    return operation_type in {
        "append_attribute_value",
        "add_attribute",
        "update_attribute_value",
    }


def _looks_wrapped_as_key_value(compiled_rhs: str, possible_keys: list[str]) -> bool:
    value = (compiled_rhs or "").strip()

    if not value:
        return False

    normalized = value[:-1].strip() if value.endswith(";") else value

    for key in possible_keys:
        clean_key = (key or "").strip()
        if clean_key and normalized.lower().startswith(f"{clean_key.lower()}="):
            return True

    return False


def _contains_sql_or_clob(compiled_rhs: str) -> bool:
    value = (compiled_rhs or "").lower()

    blocked_fragments = [
        "to_clob(",
        "update ",
        "insert ",
        "delete ",
        "merge ",
        "select ",
        "commit",
        "rollback",
        "act_mediation_parameter",
        "act_mediation_template",
    ]

    return any(fragment in value for fragment in blocked_fragments)


def _unsupported_function_calls_from_context(
    compiled_rhs: str,
    rag_context: Any,
) -> list[str]:
    """
    Reject invented function-call syntax like TO_LONG(...) or TO_NUMBER(...)
    unless those exact function names appear in the retrieved context.

    This is generic validation.
    It does not generate or hardcode Activiti expression syntax.
    """
    rhs = compiled_rhs or ""
    context_text = _format_rag_context(rag_context).lower()

    function_names = re.findall(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        rhs,
    )

    unsupported: list[str] = []

    for function_name in function_names:
        if function_name.lower() not in context_text:
            unsupported.append(function_name)

    return sorted(set(unsupported))


def _extract_simple_conditional_mapping_terms(raw_rhs_value: str) -> dict[str, str]:
    text = (raw_rhs_value or "").strip()

    if not text:
        return {}

    pattern = re.compile(
        r"""
        if\s+
        (?P<source_field>[A-Za-z_][A-Za-z0-9_.]*)
        \s+
        (?:is|equals|=|==)
        \s+
        (?P<match_value>[A-Za-z0-9_.\-$]+)
        \s+
        (?:set|return|use|map\s+to)
        \s+
        (?P<output_value>[A-Za-z0-9_.\-$]+)
        \s+
        (?:otherwise|else|default)
        \s+
        (?P<otherwise_value>[A-Za-z0-9_.\-$]+)
        """,
        flags=re.IGNORECASE | re.VERBOSE,
    )

    match = pattern.search(text)

    if not match:
        return {}

    return {
        "source_field": match.group("source_field").strip(),
        "match_value": match.group("match_value").strip(),
        "output_value": match.group("output_value").strip(),
        "otherwise_value": match.group("otherwise_value").strip(),
    }


def _missing_conditional_user_terms(
    raw_rhs_value: str,
    compiled_rhs: str,
) -> list[str]:
    terms = _extract_simple_conditional_mapping_terms(raw_rhs_value)

    if not terms:
        return []

    compiled = (compiled_rhs or "").lower()
    missing_terms: list[str] = []

    for label, value in terms.items():
        if value and value.lower() not in compiled:
            missing_terms.append(f"{label}='{value}'")

    return missing_terms


def _is_plain_comma_separated_terms(raw_rhs_value: str, compiled_rhs: str) -> bool:
    terms = _extract_simple_conditional_mapping_terms(raw_rhs_value)

    if not terms:
        return False

    rhs = (compiled_rhs or "").strip()

    if not rhs:
        return False

    if "#" in rhs or "|" in rhs or "$" in rhs:
        return False

    parts = [part.strip().lower() for part in rhs.split(",") if part.strip()]

    if len(parts) < 2:
        return False

    user_values = {value.lower() for value in terms.values() if value}

    return set(parts).issubset(user_values)


def _rag_context_supports_hash_pipe_mapping(rag_context: Any) -> bool:
    context_text = _format_rag_context(rag_context).lower()

    if not context_text:
        return False

    has_mapping_words = any(
        word in context_text
        for word in [
            "mapping",
            "map",
            "conditional",
            "otherwise",
            "else",
            "default",
        ]
    )

    has_hash_pipe_symbols = "#" in context_text and "|" in context_text

    return has_mapping_words and has_hash_pipe_symbols


def _conditional_mapping_shape_errors(
    state: AdvisorState,
    compiled_rhs: str,
) -> list[str]:
    raw_rhs_value = str(state.get("raw_rhs_value", "") or "").strip()
    terms = _extract_simple_conditional_mapping_terms(raw_rhs_value)

    if not terms:
        return []

    rhs = (compiled_rhs or "").strip()

    if not rhs:
        return []

    errors: list[str] = []

    if _is_plain_comma_separated_terms(raw_rhs_value=raw_rhs_value, compiled_rhs=rhs):
        errors.append(
            "conditional_mapping compiled_rhs is only a comma-separated list of extracted "
            "terms. It must be a valid expression using the mapping grammar retrieved "
            "from the Master RAG Guide."
        )

    supports_hash_pipe_mapping = _rag_context_supports_hash_pipe_mapping(
        state.get("rag_context")
    )

    if supports_hash_pipe_mapping:
        if "#" not in rhs or "|" not in rhs:
            errors.append(
                "Retrieved context appears to support hash/pipe conditional mapping grammar, "
                "but compiled_rhs does not use mapping separators. It should apply the "
                "retrieved mapping grammar to the user's actual field and values."
            )
    else:
        errors.append(
            "Could not verify conditional mapping grammar from retrieved context. "
            "RHS compiler should return did_compile=false instead of guessing."
        )

    return errors


def _validate_rhs_decision(
    state: AdvisorState,
    decision: RhsExpressionDecision,
) -> list[str]:
    errors: list[str] = []

    value_source_hint = state.get("value_source_hint", "")
    compiled_rhs = (decision.compiled_rhs or "").strip()

    append_key = str(state.get("append_key", "") or "").strip()
    attribute_name = str(state.get("attribute_name", "") or "").strip()
    new_attribute_name = str(state.get("new_attribute_name", "") or "").strip()
    target_attribute_name = str(state.get("target_attribute_name", "") or "").strip()

    possible_keys = [
        append_key,
        attribute_name,
        new_attribute_name,
        target_attribute_name,
    ]

    if decision.did_compile and not compiled_rhs:
        errors.append("RHS compiler returned did_compile=true but compiled_rhs is empty.")

    if compiled_rhs and _looks_wrapped_as_key_value(compiled_rhs, possible_keys):
        errors.append(
            "compiled_rhs must contain only the RHS expression. It must not be wrapped "
            "as '<attribute_or_append_key>=<value>;'."
        )

    if compiled_rhs and _contains_sql_or_clob(compiled_rhs):
        errors.append(
            "compiled_rhs must not contain SQL, table names, TO_CLOB, COMMIT, or ROLLBACK."
        )

    unsupported_functions = _unsupported_function_calls_from_context(
        compiled_rhs=compiled_rhs,
        rag_context=state.get("rag_context"),
    )

    if unsupported_functions:
        errors.append(
            "compiled_rhs contains function-call syntax that was not found in retrieved "
            "Master RAG Guide context: "
            + ", ".join(unsupported_functions)
            + ". Do not invent SQL/programming-style functions."
        )

    if value_source_hint == "dto_json_path" and "VAL_" in compiled_rhs:
        errors.append(
            "value_source_hint is dto_json_path, but compiled_rhs contains VAL_. "
            "DTO/JSON values must not be compiled as static literals."
        )

    if value_source_hint == "session_variable" and "VAL_" in compiled_rhs:
        errors.append(
            "value_source_hint is session_variable, but compiled_rhs contains VAL_. "
            "Session values must not be compiled as static literals."
        )

    if value_source_hint == "conditional_mapping" and compiled_rhs:
        raw_rhs_value = str(state.get("raw_rhs_value", "") or "").strip()

        missing_terms = _missing_conditional_user_terms(
            raw_rhs_value=raw_rhs_value,
            compiled_rhs=compiled_rhs,
        )

        if missing_terms:
            errors.append(
                "conditional_mapping compiled_rhs appears to copy a retrieved example "
                "instead of using the user's actual mapping terms. Missing user terms: "
                + ", ".join(missing_terms)
            )

        errors.extend(
            _conditional_mapping_shape_errors(
                state=state,
                compiled_rhs=compiled_rhs,
            )
        )

    return errors


def _build_rhs_user_prompt(state: AdvisorState, rag_context_text: str) -> str:
    return f"""
User requirement:
{state.get("user_requirement", "")}

Normalized intent:
operation_type: {state.get("operation_type", "")}
template_id: {state.get("template_id", "")}
attribute_name: {state.get("attribute_name", "")}
target_attribute_name: {state.get("target_attribute_name", "")}
new_attribute_name: {state.get("new_attribute_name", "")}
append_key: {state.get("append_key", "")}
raw_rhs_value: {state.get("raw_rhs_value", "")}
value_source_hint: {state.get("value_source_hint", "")}

Important:
- Compile only raw_rhs_value into compiled_rhs.
- Do not assemble append_key=compiled_rhs;.
- Do not return attribute_name=compiled_rhs;.
- Do not write SQL.
- Do not use VAL_ for DTO/JSON/session values.
- For transformations, use only exact syntax from retrieved context.
- Do not invent function-call syntax.
- Retrieved examples are grammar examples only.
- Do not copy field names or values from retrieved examples unless the user actually mentioned them.
- Do not return a plain comma-separated list of extracted terms.

RAG query used:
{state.get("rag_query", "")}

Retrieved Master RAG Guide context:
{rag_context_text}

Task:
Return the RHS-only expression decision.
"""


def _invoke_rhs_compiler(
    state: AdvisorState,
    rag_context_text: str,
) -> tuple[RhsExpressionDecision, list[str]]:
    llm = _get_rhs_compiler_llm()

    user_prompt = _build_rhs_user_prompt(
        state=state,
        rag_context_text=rag_context_text,
    )

    decision = llm.invoke(
        [
            {"role": "system", "content": RHS_EXPRESSION_COMPILER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )

    errors = _validate_rhs_decision(state=state, decision=decision)

    if decision.did_compile and errors:
        retry_prompt = f"""
The previous RHS compiler output was rejected.

Validation errors:
{chr(10).join(f"- {error}" for error in errors)}

Retry with these hard constraints:
- Return only compiled_rhs.
- Do not return key=value;.
- Do not include append_key or attribute_name as wrapper.
- Do not write SQL.
- Do not return TO_CLOB.
- Do not invent function-call syntax.
- operation_type: {state.get("operation_type", "")}
- append_key: {state.get("append_key", "")}
- attribute_name: {state.get("attribute_name", "")}
- raw_rhs_value: {state.get("raw_rhs_value", "")}
- value_source_hint: {state.get("value_source_hint", "")}
- If value_source_hint is dto_json_path, compiled_rhs must not contain VAL_.
- If value_source_hint is session_variable, compiled_rhs must not contain VAL_.
- Advanced syntax is allowed only if supported by retrieved context.
- For transformation requests, use only exact syntax from retrieved context.
- If retrieved context does not clearly support the transformation, return did_compile=false.

For conditional_mapping:
- Do not copy field names or values from retrieved examples.
- Retrieved examples show syntax only.
- Use the user's actual source field, match value, output value, and otherwise/default value.
- raw_rhs_value is: {state.get("raw_rhs_value", "")}
- Do not return an unrelated example from the retrieved guide.
- Do not return comma-separated extracted terms.
- Apply the conditional mapping grammar from retrieved context.
- If retrieved context does not clearly support the required mapping grammar, return did_compile=false.

Original task:
{user_prompt}
"""

        decision = llm.invoke(
            [
                {"role": "system", "content": RHS_EXPRESSION_COMPILER_SYSTEM_PROMPT},
                {"role": "user", "content": retry_prompt},
            ]
        )

        errors = _validate_rhs_decision(state=state, decision=decision)

    return decision, errors


def rhs_expression_compilation_node(state: AdvisorState) -> dict[str, Any]:
    operation_type = state.get("operation_type", "unknown")
    existing_warnings = list(state.get("warnings", []) or [])
    existing_validation_errors = list(state.get("validation_errors", []) or [])

    if not _operation_needs_rhs_compilation(operation_type):
        reason = f"RHS compilation not required for operation_type={operation_type}."

        return {
            "rhs_compilation_did_compile": False,
            "rhs_compilation_confidence": 1.0,
            "rhs_compilation_reason": reason,
            "rhs_compilation_warnings": [],
            "expression_compilation_did_compile": False,
            "expression_compilation_confidence": 1.0,
            "expression_compilation_reason": reason,
            "expression_compilation_warnings": [],
        }

    rag_context_text = _format_rag_context(state.get("rag_context"))

    if not rag_context_text:
        warning = "RHS expression compilation skipped because no RAG context was retrieved."

        return {
            "rhs_compilation_did_compile": False,
            "rhs_compilation_confidence": 0.0,
            "rhs_compilation_reason": warning,
            "rhs_compilation_warnings": [warning],
            "warnings": existing_warnings + [warning],
            "expression_compilation_did_compile": False,
            "expression_compilation_confidence": 0.0,
            "expression_compilation_reason": warning,
            "expression_compilation_warnings": [warning],
        }

    decision, errors = _invoke_rhs_compiler(
        state=state,
        rag_context_text=rag_context_text,
    )

    reason_parts = [
        f"value_source_hint: {state.get('value_source_hint', '')}",
        f"value_source_category: {decision.value_source_category}",
        f"raw_rhs_value: {state.get('raw_rhs_value', '')}",
        f"compiled_rhs: {decision.compiled_rhs}",
        decision.reasoning,
        f"Rule source: {decision.rule_source}" if decision.rule_source else "",
        f"Rule evidence: {decision.rule_evidence}" if decision.rule_evidence else "",
    ]

    warnings = list(decision.warnings or [])

    updates: dict[str, Any] = {
        "rhs_compilation_did_compile": decision.did_compile,
        "rhs_compilation_confidence": decision.confidence,
        "rhs_compilation_reason": "\n".join(part for part in reason_parts if part),
        "rhs_compilation_warnings": warnings,
        "compiled_rhs": decision.compiled_rhs.strip(),
        "expression_compilation_did_compile": decision.did_compile,
        "expression_compilation_confidence": decision.confidence,
        "expression_compilation_reason": "\n".join(part for part in reason_parts if part),
        "expression_compilation_warnings": warnings,
    }

    if decision.did_compile and errors:
        warnings.extend(errors)

        updates.update(
            {
                "rhs_compilation_did_compile": False,
                "rhs_compilation_confidence": 0.0,
                "rhs_compilation_warnings": warnings,
                "compiled_rhs": "",
                "validation_errors": existing_validation_errors + errors,
                "warnings": existing_warnings + warnings,
                "expression_compilation_did_compile": False,
                "expression_compilation_confidence": 0.0,
                "expression_compilation_warnings": warnings,
            }
        )

        return updates

    if not decision.did_compile:
        warning = (
            "RHS compiler did not compile because no sufficiently supported Master RAG "
            "Guide rule was found."
        )
        warnings.append(warning)

        updates["rhs_compilation_warnings"] = warnings
        updates["expression_compilation_warnings"] = warnings
        updates["warnings"] = existing_warnings + warnings

        return updates

    if decision.confidence < 0.75:
        warning = "RHS compiler confidence is below 0.75. Review before using SQL."
        warnings.append(warning)

    updates["rhs_compilation_warnings"] = warnings
    updates["expression_compilation_warnings"] = warnings
    updates["warnings"] = existing_warnings + warnings

    return updates