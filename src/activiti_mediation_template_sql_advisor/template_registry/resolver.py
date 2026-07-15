from __future__ import annotations

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
    "planner_phrase_exact",
    "alias_fuzzy",
    "fuzzy",
    "not_found",
    "error",
]

DEFAULT_MINIMUM_FUZZY_SCORE = 0.88


class TemplateResolutionResult(BaseModel):
    """Result of resolving a user/business phrase into a TEMPLATE_ID."""

    template_id: str = ""
    external_system: str = ""
    matched_text: str = ""
    match_type: MatchType = "not_found"
    score: float = 0.0
    reason: str = ""
    is_resolved: bool = False

    def to_graph_dict(self) -> dict[str, object]:
        return self.model_dump()


def _normalize(value: str) -> str:
    return " ".join((value or "").lower().split())


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _entry_aliases(entry: TemplateRegistryEntry) -> list[str]:
    aliases: list[str] = []

    if entry.description:
        aliases.append(entry.description)

    aliases.extend(entry.aliases)

    if entry.template_id:
        aliases.append(entry.template_id)

    seen: set[str] = set()
    unique_aliases: list[str] = []

    for alias in aliases:
        clean = " ".join(str(alias).split())
        if not clean:
            continue

        key = clean.lower()
        if key in seen:
            continue

        seen.add(key)
        unique_aliases.append(clean)

    return unique_aliases


def _external_system_matches(
    requested_external_system: str,
    record_external_system: str,
) -> bool:
    if not requested_external_system:
        return True

    if not record_external_system:
        return True

    return (
        requested_external_system.strip().lower()
        == record_external_system.strip().lower()
    )


def _template_id_in_text(user_text: str, template_id: str) -> bool:
    normalized_user_text = _normalize(user_text)
    normalized_template_id = _normalize(template_id)
    return normalized_template_id in normalized_user_text


def resolve_template_from_plan(
    *,
    user_requirement: str,
    template_phrase: str = "",
    external_system: str = "",
    minimum_fuzzy_score: float = DEFAULT_MINIMUM_FUZZY_SCORE,
) -> TemplateResolutionResult:
    """
    Resolve planner context into a TEMPLATE_ID using the cached typed registry.

    Matching order:
        1. Exact TEMPLATE_ID in user text
        2. Exact alias contained in user requirement
        3. Exact planner phrase equals alias
        4. Fuzzy alias match above threshold
    """
    registry = get_template_registry()
    user_text = _normalize(user_requirement)
    phrase_text = _normalize(template_phrase)

    for entry in registry.templates:
        if _template_id_in_text(user_requirement, entry.template_id):
            return TemplateResolutionResult(
                template_id=entry.template_id,
                external_system=entry.external_system,
                matched_text=entry.template_id,
                match_type="template_id_exact",
                score=1.0,
                reason="Exact TEMPLATE_ID found in user requirement.",
                is_resolved=True,
            )

    for entry in registry.templates:
        if not _external_system_matches(external_system, entry.external_system):
            continue

        for alias in _entry_aliases(entry):
            alias_norm = _normalize(alias)
            if alias_norm and alias_norm in user_text:
                return TemplateResolutionResult(
                    template_id=entry.template_id,
                    external_system=entry.external_system,
                    matched_text=alias,
                    match_type="alias_exact",
                    score=1.0,
                    reason="Exact configured alias found in user requirement.",
                    is_resolved=True,
                )

    for entry in registry.templates:
        if not _external_system_matches(external_system, entry.external_system):
            continue

        for alias in _entry_aliases(entry):
            alias_norm = _normalize(alias)
            if phrase_text and phrase_text == alias_norm:
                return TemplateResolutionResult(
                    template_id=entry.template_id,
                    external_system=entry.external_system,
                    matched_text=alias,
                    match_type="planner_phrase_exact",
                    score=1.0,
                    reason="Planner template phrase exactly matched configured alias.",
                    is_resolved=True,
                )

    best_entry: TemplateRegistryEntry | None = None
    best_score = 0.0
    best_alias = ""

    for entry in registry.templates:
        if not _external_system_matches(external_system, entry.external_system):
            continue

        for alias in _entry_aliases(entry):
            alias_norm = _normalize(alias)
            if not alias_norm:
                continue

            score = 0.0
            if phrase_text:
                score = max(score, _ratio(phrase_text, alias_norm))
            score = max(score, _ratio(user_text, alias_norm))

            if score > best_score:
                best_score = score
                best_entry = entry
                best_alias = alias

    if best_entry and best_score >= minimum_fuzzy_score:
        return TemplateResolutionResult(
            template_id=best_entry.template_id,
            external_system=best_entry.external_system,
            matched_text=best_alias,
            match_type="fuzzy",
            score=round(best_score, 4),
            reason="Best fuzzy registry alias match.",
            is_resolved=True,
        )

    return TemplateResolutionResult(
        template_id="",
        external_system=external_system or "",
        match_type="not_found",
        matched_text=best_alias,
        score=round(best_score, 4),
        reason=(
            f"No template registry match reached threshold {minimum_fuzzy_score}. "
            f"Best candidate was '{best_alias}' with score {best_score:.4f}."
            if best_alias
            else "No template registry aliases were matched."
        ),
        is_resolved=False,
    )