from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]

RULEBOOK_PATH = (
    PROJECT_ROOT
    / "data"
    / "expression_rules"
    / "attribute_value_rulebook.json"
)


@lru_cache(maxsize=1)
def load_attribute_value_rulebook() -> dict[str, Any]:
    """
    Load the ATTRIBUTE_VALUE rulebook.

    This rulebook is the source of truth for ACT_MEDIATION_PARAMETER.ATTRIBUTE_VALUE
    DSL syntax such as VAL_, source fields, mappings, conversions, and composite
    key=value; structures.
    """
    if not RULEBOOK_PATH.exists():
        raise FileNotFoundError(
            f"ATTRIBUTE_VALUE rulebook not found at: {RULEBOOK_PATH}"
        )

    with RULEBOOK_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("ATTRIBUTE_VALUE rulebook must be a JSON object.")

    return data


def get_rulebook_prompt_summary() -> str:
    """
    Return a compact prompt-safe summary for the LLM.

    We do not dump the full 700+ line JSON into every prompt.
    This summary gives the model the critical rules it needs for RHS generation.
    """
    rulebook = load_attribute_value_rulebook()

    metadata = rulebook.get("rulebook_metadata", {}) or {}
    shapes = rulebook.get("attribute_value_shapes", {}) or {}
    guidelines = (
        rulebook.get("generation_guidelines_for_llm", {}) or {}
    ).get("when_building_attribute_value", [])

    common_patterns = (
        rulebook.get("generation_guidelines_for_llm", {}) or {}
    ).get("common_patterns", {})

    return f"""
ATTRIBUTE_VALUE RULEBOOK SUMMARY

Rulebook:
- Name: {metadata.get("name", "ACT_MEDIATION_PARAMETER ATTRIBUTE_VALUE Rulebook")}
- Target table: {metadata.get("target_table", "ACT_MEDIATION_PARAMETER")}
- Target column: {metadata.get("target_column", "ATTRIBUTE_VALUE")}

Core DSL rules:
1. VAL_<text>
   Means static/literal value. Example: value 123 => VAL_123.

2. Plain field/path
   Means DTO/source field lookup. Example: dto field allowances.sms.freebies => allowances.sms.freebies.
   Do NOT convert DTO/source fields into VAL_<path>.

3. Mapping
   Use <sourcePath>#<conditionValue>|<resultValue>,ELSE|<elseValue>.
   Example: if addToBill is false set false otherwise true
   => addToBill#false|false,ELSE|true.

4. Append inside composite/container attributes
   If user says inside existing poAttributes / inside poAttributes / within existing poAttributes,
   operation_kind MUST be append_subkey.
   The expression should be RHS only.
   Example: add CustomerType with value 123 inside poAttributes
   => expression: VAL_123
   Python will wrap it as CustomerType=VAL_123;

5. Atomic ATTRIBUTE_VALUE shape
   ATTRIBUTE_NAME is the target attribute.
   ATTRIBUTE_VALUE is just one expression.
   Example:
   ATTRIBUTE_NAME = gundu
   ATTRIBUTE_VALUE = VAL_123
   Do NOT generate gundu=VAL_123 for atomic rows.

6. Composite ATTRIBUTE_VALUE shape
   ATTRIBUTE_NAME is a container such as poAttributes.
   ATTRIBUTE_VALUE contains key=value; pairs.
   Example:
   CustomerType=VAL_123;

7. Type/conversion/session prefixes
   Use prefixes from the rulebook only when the request clearly asks for that transformation:
   $S_, $NUM_, $INT_, $STR_, $BYTE_, $KBYTE_, $SEC_, $HOUR_, $CONCAT_,
   $JSONPATH_, $DATE_, $NOW_, $BOOL_, etc.

8. Unsupported
   If the user asks for a transformation but the exact DSL syntax cannot be confirmed,
   return unsupported instead of guessing.

Attribute value shapes:
{json.dumps(shapes, indent=2, ensure_ascii=False)}

Generation guidelines:
{json.dumps(guidelines, indent=2, ensure_ascii=False)}

Common patterns:
{json.dumps(common_patterns, indent=2, ensure_ascii=False)}
""".strip()