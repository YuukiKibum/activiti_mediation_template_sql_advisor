from __future__ import annotations

from typing import Any, Literal, TypedDict


OperationType = Literal[
    "rename_attribute",
    "add_attribute",
    "update_attribute_value",
    "append_attribute_value",
    "delete_attribute",
    "unknown",
]


class RequestPlan(TypedDict, total=False):
    """
    Clean intent extracted from the user requirement.

    This is intentionally expression-light.
    No DSL syntax should be generated in the planner.
    """

    operation_type: OperationType

    # Template / system targeting
    template_phrase: str
    external_system: str

    # Existing/new attribute targeting
    attribute_name: str
    new_attribute_name: str

    # Append-specific targeting
    container_attribute_name: str
    append_key: str

    # Human-language RHS request only.
    # Example:
    # "dto variable sample"
    # "if subscriberType is PREPAID show 1 else 0"
    # "convert DTO field x to long"
    rhs_request: str

    confidence: float
    reason: str


class TemplateResolutionResult(TypedDict, total=False):
    """
    Result of resolving the template from the registry.
    """

    template_id: str
    external_system: str

    match_type: str
    matched_text: str
    score: float
    reason: str

    is_resolved: bool


class ExpressionResult(TypedDict, total=False):
    """
    Result of DSL expression compilation.

    This is the only place where compiled RHS lives.
    """

    did_compile: bool
    is_supported: bool

    selected_record_id: str
    selected_evaluator: str

    # RHS only. Never SQL. Never TO_CLOB.
    compiled_rhs: str

    # For append operation only.
    # Example:
    # append_key = "CustomerType"
    # compiled_rhs = "subscriberType#PREPAID|1,ELSE|0"
    # append_fragment = "CustomerType=subscriberType#PREPAID|1,ELSE|0;"
    append_fragment: str

    confidence: float
    reason: str
    unsupported_guidance: str

    warnings: list[str]
    errors: list[str]


class OracleInspectionResult(TypedDict, total=False):
    """
    Result of reading the current Oracle state through MCP.
    """

    can_generate_sql: bool

    param_id: str
    template_id: str
    attribute_name: str
    current_attribute_value: str

    exists: bool
    duplicate_append_key: bool

    warnings: list[str]
    errors: list[str]


class SqlGenerationResult(TypedDict, total=False):
    """
    Final generated SQL and rollback SQL.
    """

    can_execute: bool
    recommended_sql: str
    rollback_sql: str

    reason: str
    warnings: list[str]
    errors: list[str]


class AdvisorState(TypedDict, total=False):
    """
    Minimal graph state.

    Keep this clean to prevent context pollution.

    Each node should read only what it needs and write only its own nested result.
    """

    user_requirement: str

    plan: RequestPlan
    template: TemplateResolutionResult
    expression: ExpressionResult
    oracle: OracleInspectionResult
    sql: SqlGenerationResult

    final_answer: str

    warnings: list[str]
    errors: list[str]

    # Only for optional debug data.
    # Do not put large RAG context here unless debug mode is enabled.
    debug: dict[str, Any]


def create_initial_state(user_requirement: str) -> AdvisorState:
    return {
        "user_requirement": user_requirement,
        "warnings": [],
        "errors": [],
        "debug": {},
    }


def append_warning(state: AdvisorState, warning: str) -> list[str]:
    warnings = list(state.get("warnings", []) or [])
    warnings.append(warning)
    return warnings


def append_error(state: AdvisorState, error: str) -> list[str]:
    errors = list(state.get("errors", []) or [])
    errors.append(error)
    return errors