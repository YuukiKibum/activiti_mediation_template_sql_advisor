from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]

RUNTIME_SPEC_PATH = (
    PROJECT_ROOT
    / "data"
    / "expression_rules"
    / "attribute_value_runtime_spec.json"
)


@lru_cache(maxsize=1)
def load_attribute_value_runtime_spec() -> dict[str, Any]:
    """
    Backward-compatible public function name.

    Loads the advisor-owned ATTRIBUTE_VALUE runtime specification.

    The project previously used a rulebook-shaped JSON file. The new file is
    organised around the SQL advisor compiler:
    - storage contracts
    - expression grammar
    - delimiter/mapping rules
    - runtime edge cases
    - advisor generation policy
    - coverage matrix
    """
    if not RUNTIME_SPEC_PATH.exists():
        raise FileNotFoundError(
            f"ATTRIBUTE_VALUE runtime spec not found at: {RUNTIME_SPEC_PATH}"
        )

    with RUNTIME_SPEC_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError("ATTRIBUTE_VALUE runtime spec must be a JSON object.")

    return data


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def _build_rulebook_prompt_summary() -> str:
    """
    Backward-compatible public function name used by the DSL expression compiler.

    Returns a compact prompt-safe summary from the new runtime spec.
    """
    spec = load_attribute_value_runtime_spec()

    header = spec.get("spec_header", {}) or {}
    target = header.get("target", {}) or {}
    runtime_model = spec.get("runtime_model", {}) or {}
    storage_contracts = spec.get("storage_contracts", {}) or {}
    grammar = spec.get("expression_grammar", {}) or {}
    delimiter_rules = spec.get("delimiter_and_mapping_rules", {}) or {}
    policy = spec.get("advisor_generation_policy", {}) or {}
    coverage = spec.get("coverage_matrix", {}) or {}

    prefix_families = grammar.get("prefix_operations_by_family", {}) or {}
    prefix_summary: list[str] = []

    for family_name, rules in prefix_families.items():
        tokens = [
            str(rule.get("token", ""))
            for rule in rules
            if isinstance(rule, dict) and rule.get("token")
        ]
        if tokens:
            prefix_summary.append(f"- {family_name}: {', '.join(tokens)}")

    normal_shape = storage_contracts.get("normal_attribute_row", {}) or {}
    container_shape = storage_contracts.get("container_attribute_row", {}) or {}

    return f"""
ATTRIBUTE_VALUE RUNTIME SPEC SUMMARY

Spec:
- Name: {header.get("name", "Mediation ATTRIBUTE_VALUE Runtime Specification")}
- Version: {header.get("version", "")}
- Target table: {target.get("table", "ACT_MEDIATION_PARAMETER")}
- Target column: {target.get("column", "ATTRIBUTE_VALUE")}
- Runtime entry point: {target.get("runtime_entry_point", "")}

Compiler model:
{runtime_model.get("expression_value_shape", "")}

Storage contracts:
1. Normal/atomic ATTRIBUTE_VALUE
   - Store only the compiled expression.
   - ATTRIBUTE_NAME is already the row key.
   - Do NOT generate key=value; for normal rows.
   - Examples:
{_json_block(normal_shape.get("examples", [])[:3])}

2. Composite/container ATTRIBUTE_VALUE
   - Store semicolon-delimited key=value; segments.
   - For append_subkey, the compiler returns only RHS expression.
   - Python/SQL layer wraps as append_key=<compiledExpression>;
   - Examples:
{_json_block(container_shape.get("examples", [])[:4])}

Core expression rules:
- VAL_<text> means static/literal text.
- Plain field/path means DTO/source JSON path lookup.
- Do NOT convert DTO/source paths into VAL_<path>.
- Mapping uses sourceField#conditionValue|resultValue,ELSE|elseValue.
- Mapping sourceField is the input field being tested, not the target ATTRIBUTE_NAME or append key.
- If exact syntax cannot be confirmed, return unsupported instead of guessing.

Prefix families:
{chr(10).join(prefix_summary)}

Fallback/source path:
{_json_block(grammar.get("fallback_source_path_resolution", {}))}

Complex methods:
{_json_block(grammar.get("complex_function_calls", {}).get("methods", []))}

Delimiter and mapping rules:
{_json_block(delimiter_rules)}

Advisor generation policy:
{_json_block(policy)}

Coverage:
- Prefix rules: {coverage.get("counts", {}).get("prefix_rules")}
- Complex methods: {coverage.get("counts", {}).get("complex_methods")}
- Few-shot/runtime examples: {coverage.get("counts", {}).get("few_shot_examples")}
- Storage shape examples: normal={coverage.get("counts", {}).get("storage_shape_examples_normal")}, container={coverage.get("counts", {}).get("storage_shape_examples_container")}
""".strip()


@lru_cache(maxsize=1)
def get_rulebook_prompt_summary() -> str:
    """
    Cached prompt-safe summary from the ATTRIBUTE_VALUE runtime spec.
    """
    return _build_rulebook_prompt_summary()


def warmup_rulebook_prompt_summary() -> str:
    """Eagerly build the cached rulebook summary at application startup."""
    return get_rulebook_prompt_summary()
