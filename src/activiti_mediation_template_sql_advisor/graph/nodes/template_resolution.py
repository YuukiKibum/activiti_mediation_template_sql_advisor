from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import yaml

from activiti_mediation_template_sql_advisor.graph.state import (
    AdvisorState,
    append_error,
    append_warning,
)


def _project_root() -> Path:
    """
    Find project root by walking upward until data/template_registry exists.
    """
    current = Path.cwd().resolve()

    for path in [current, *current.parents]:
        if (path / "data" / "template_registry").exists():
            return path

    return current


def _registry_path() -> Path:
    return _project_root() / "data" / "template_registry" / "template_registry.yaml"


def _normalize(value: str) -> str:
    return " ".join((value or "").lower().split())


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize(left), _normalize(right)).ratio()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value if item is not None]

    if isinstance(value, tuple):
        return [str(item) for item in value if item is not None]

    if isinstance(value, str):
        return [value]

    return [str(value)]


def _load_registry() -> list[dict[str, Any]]:
    path = _registry_path()

    if not path.exists():
        raise FileNotFoundError(f"Template registry not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    records: list[dict[str, Any]] = []

    # Supported shape 1:
    # templates:
    #   - template_id: ...
    #     external_system: ...
    #     aliases: [...]
    if isinstance(data, dict) and isinstance(data.get("templates"), list):
        for item in data["templates"]:
            if isinstance(item, dict):
                records.append(item)

        return records

    # Supported shape 2:
    # MT_ECM_PRE_BASEPLAN:
    #   external_system: ECM
    #   aliases: [...]
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(value, dict):
                continue

            record = dict(value)
            record.setdefault("template_id", key)
            records.append(record)

        return records

    # Supported shape 3:
    # - template_id: ...
    #   aliases: [...]
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                records.append(item)

        return records

    return records


def _record_template_id(record: dict[str, Any]) -> str:
    return str(
        record.get("template_id")
        or record.get("id")
        or record.get("template")
        or ""
    ).strip()


def _record_external_system(record: dict[str, Any]) -> str:
    return str(
        record.get("external_system")
        or record.get("template_external_system")
        or record.get("system")
        or ""
    ).strip()


def _record_aliases(record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []

    for key in [
        "aliases",
        "alias",
        "template_aliases",
        "names",
        "name",
        "description",
        "synonyms",
    ]:
        aliases.extend(_as_list(record.get(key)))

    template_id = _record_template_id(record)

    if template_id:
        aliases.append(template_id)

    # IMPORTANT:
    # Do NOT append external_system as an alias.
    # Example: if we add "ECM" as alias, every request containing ECM will match
    # the first ECM template, such as BUNDLE_PREPAID_ECM_ATTRS_MT.
    # external_system should only filter candidates, not act as a matching alias.

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

    return requested_external_system.strip().lower() == record_external_system.strip().lower()


def _resolve_template(
    *,
    user_requirement: str,
    template_phrase: str,
    requested_external_system: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    user_text = _normalize(user_requirement)
    phrase_text = _normalize(template_phrase)

    best: dict[str, Any] | None = None
    best_score = 0.0
    best_alias = ""
    best_match_type = "not_found"
    best_reason = "No matching template registry alias found."

    for record in records:
        template_id = _record_template_id(record)
        external_system = _record_external_system(record)

        if not template_id:
            continue

        if not _external_system_matches(requested_external_system, external_system):
            continue

        aliases = _record_aliases(record)

        for alias in aliases:
            alias_norm = _normalize(alias)

            if not alias_norm:
                continue

            # Exact alias contained in user requirement.
            if alias_norm in user_text:
                return {
                    "template_id": template_id,
                    "external_system": external_system,
                    "match_type": "alias_exact",
                    "matched_text": alias,
                    "score": 1.0,
                    "reason": "Exact configured alias found in user requirement.",
                    "is_resolved": True,
                }

            # Exact planner phrase equals alias.
            if phrase_text and phrase_text == alias_norm:
                return {
                    "template_id": template_id,
                    "external_system": external_system,
                    "match_type": "planner_phrase_exact",
                    "matched_text": alias,
                    "score": 1.0,
                    "reason": "Planner template phrase exactly matched configured alias.",
                    "is_resolved": True,
                }

            # Fuzzy compare alias against planner phrase first, then full requirement.
            score = 0.0

            if phrase_text:
                score = max(score, _ratio(phrase_text, alias_norm))

            score = max(score, _ratio(user_text, alias_norm))

            if score > best_score:
                best = record
                best_score = score
                best_alias = alias
                best_match_type = "fuzzy"
                best_reason = "Best fuzzy registry alias match."

    if best and best_score >= 0.88:
        return {
            "template_id": _record_template_id(best),
            "external_system": _record_external_system(best),
            "match_type": best_match_type,
            "matched_text": best_alias,
            "score": round(best_score, 4),
            "reason": best_reason,
            "is_resolved": True,
        }

    return {
        "template_id": "",
        "external_system": requested_external_system or "",
        "match_type": "not_found",
        "matched_text": best_alias,
        "score": round(best_score, 4),
        "reason": (
            "No template registry match reached threshold 0.88. "
            f"Best candidate was '{best_alias}' with score {best_score:.4f}."
            if best_alias
            else "No template registry aliases were matched."
        ),
        "is_resolved": False,
    }


def template_resolution_node(state: AdvisorState) -> dict[str, Any]:
    plan = state.get("plan", {}) or {}

    user_requirement = state.get("user_requirement", "")
    template_phrase = str(plan.get("template_phrase", "") or "")
    requested_external_system = str(plan.get("external_system", "") or "")

    try:
        records = _load_registry()

        result = _resolve_template(
            user_requirement=user_requirement,
            template_phrase=template_phrase,
            requested_external_system=requested_external_system,
            records=records,
        )

        updates: dict[str, Any] = {
            "template": result,
        }

        if not result.get("is_resolved"):
            updates["warnings"] = append_warning(
                state,
                f"Template resolution failed: {result.get('reason', '')}",
            )

        return updates

    except Exception as exc:
        error = f"template_resolution_node failed: {exc}"

        return {
            "template": {
                "template_id": "",
                "external_system": requested_external_system,
                "match_type": "error",
                "matched_text": "",
                "score": 0.0,
                "reason": error,
                "is_resolved": False,
            },
            "errors": append_error(state, error),
        }