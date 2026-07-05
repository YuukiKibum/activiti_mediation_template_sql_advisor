import re
from difflib import SequenceMatcher
from typing import Literal

from pydantic import BaseModel, Field

from activiti_mediation_template_sql_advisor.template_registry.loader import (
    TemplateRegistryEntry,
    get_template_registry,
)


MatchType = Literal[
    "template_id_exact",
    "alias_exact",
    "alias_fuzzy",
    "not_found",
]


class TemplateResolutionResult(BaseModel):
    """
    Result of resolving a user/business phrase into a TEMPLATE_ID.
    """

    template_id: str = ""
    external_system: str = ""
    matched_text: str = ""
    match_type: MatchType = "not_found"
    score: float = 0.0
    reason: str = ""


def normalize_text(value: str) -> str:
    """
    Normalize text for matching.

    Example:
        "Prepaid Base Plan ECM request"
        -> "PREPAID BASE PLAN ECM REQUEST"
    """
    value = value or ""
    value = value.upper()
    value = re.sub(r"[^A-Z0-9_]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _token_score(user_text: str, candidate_text: str) -> float:
    """
    Calculate how many important candidate words appear in the user text.

    Example:
        user_text:
            FOR PREPAID BASE PLAN ECM REQUEST RENAME POATTRIBUTES

        candidate_text:
            PREPAID BASE PLAN ECM REQUEST

        score:
            1.0
    """
    user_tokens = set(normalize_text(user_text).replace("_", " ").split())
    candidate_tokens = set(normalize_text(candidate_text).replace("_", " ").split())

    if not candidate_tokens:
        return 0.0

    matched_tokens = user_tokens.intersection(candidate_tokens)

    return len(matched_tokens) / len(candidate_tokens)


def _sequence_score(user_text: str, candidate_text: str) -> float:
    """
    Calculate rough text similarity using Python's built-in difflib.
    """
    normalized_user_text = normalize_text(user_text)
    normalized_candidate_text = normalize_text(candidate_text)

    if not normalized_user_text or not normalized_candidate_text:
        return 0.0

    return SequenceMatcher(
        None,
        normalized_user_text,
        normalized_candidate_text,
    ).ratio()


def _candidate_score(user_text: str, candidate_text: str) -> float:
    """
    Combine token matching and sequence matching.

    Token matching is more important for our use case because user requirements
    usually contain extra words like rename, add, change, attribute, etc.
    """
    token_score = _token_score(user_text, candidate_text)
    sequence_score = _sequence_score(user_text, candidate_text)

    return (token_score * 0.75) + (sequence_score * 0.25)


def _template_id_appears_in_text(user_text: str, template_id: str) -> bool:
    """
    Check if an exact TEMPLATE_ID appears in the user requirement.

    We use upper-case comparison because TEMPLATE_ID values are case-insensitive
    in normal user input, but stored as uppercase in Oracle.
    """
    normalized_user_text = normalize_text(user_text)
    normalized_template_id = normalize_text(template_id)

    return normalized_template_id in normalized_user_text


def _resolve_by_exact_template_id(
    user_text: str,
    entries: list[TemplateRegistryEntry],
) -> TemplateResolutionResult | None:
    """
    Resolve when the user directly typed a real TEMPLATE_ID.
    """
    for entry in entries:
        if _template_id_appears_in_text(user_text, entry.template_id):
            return TemplateResolutionResult(
                template_id=entry.template_id,
                external_system=entry.external_system,
                matched_text=entry.template_id,
                match_type="template_id_exact",
                score=1.0,
                reason="Exact TEMPLATE_ID found in user requirement.",
            )

    return None


def _resolve_by_exact_alias(
    user_text: str,
    entries: list[TemplateRegistryEntry],
) -> TemplateResolutionResult | None:
    """
    Resolve when a configured alias appears in the user requirement.
    """
    normalized_user_text = normalize_text(user_text)

    for entry in entries:
        for alias in entry.aliases:
            normalized_alias = normalize_text(alias)

            if normalized_alias and normalized_alias in normalized_user_text:
                return TemplateResolutionResult(
                    template_id=entry.template_id,
                    external_system=entry.external_system,
                    matched_text=alias,
                    match_type="alias_exact",
                    score=1.0,
                    reason="Exact configured alias found in user requirement.",
                )

    return None


def _resolve_by_fuzzy_alias(
    user_text: str,
    entries: list[TemplateRegistryEntry],
    minimum_score: float,
) -> TemplateResolutionResult | None:
    """
    Resolve using fuzzy alias matching.

    This helps when the user says something close to an alias, but not exactly.
    """
    best_entry: TemplateRegistryEntry | None = None
    best_alias = ""
    best_score = 0.0

    for entry in entries:
        candidates = [entry.template_id, *entry.aliases]

        for candidate in candidates:
            score = _candidate_score(user_text, candidate)

            if score > best_score:
                best_score = score
                best_entry = entry
                best_alias = candidate

    if best_entry is None or best_score < minimum_score:
        return None

    return TemplateResolutionResult(
        template_id=best_entry.template_id,
        external_system=best_entry.external_system,
        matched_text=best_alias,
        match_type="alias_fuzzy",
        score=round(best_score, 4),
        reason=(
            "Best fuzzy match from template registry. "
            "Oracle inspection should still confirm the template exists."
        ),
    )


def resolve_template(
    user_text: str,
    minimum_fuzzy_score: float = 0.82,
) -> TemplateResolutionResult:
    """
    Resolve user/business text into a TEMPLATE_ID.

    Matching order:
        1. Exact TEMPLATE_ID
        2. Exact alias
        3. Fuzzy alias/template match
        4. Not found
    """
    registry = get_template_registry()
    entries = registry.templates

    exact_template_id_result = _resolve_by_exact_template_id(user_text, entries)
    if exact_template_id_result is not None:
        return exact_template_id_result

    exact_alias_result = _resolve_by_exact_alias(user_text, entries)
    if exact_alias_result is not None:
        return exact_alias_result

    fuzzy_result = _resolve_by_fuzzy_alias(
        user_text=user_text,
        entries=entries,
        minimum_score=minimum_fuzzy_score,
    )
    if fuzzy_result is not None:
        return fuzzy_result

    return TemplateResolutionResult(
        match_type="not_found",
        score=0.0,
        reason=(
            "No TEMPLATE_ID or configured alias could be resolved from the "
            "user requirement."
        ),
    )


if __name__ == "__main__":
    examples = [
        "Rename poAttributes to poAttributeList for MT_ECM_PRE_BASEPLAN",
        "For Prepaid Base Plan ECM request, rename existing attribute poAttributes to poAttributeList.",
        "For Prepaid STK Notify Store request, change POType from Add-on to Base Plan.",
        "For Prepaid IN Group Offer, set ThirdPartySub_Category so third party subscription enabled true maps to 1 and false maps to 0 as a long value.",
        "For Prepaid Base Plan XYZ request, add AddToBillFlagCopy.",
    ]

    for example in examples:
        result = resolve_template(example)

        print("=" * 100)
        print("Input:", example)
        print("Result:", result.model_dump())