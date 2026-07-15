from __future__ import annotations

from activiti_mediation_template_sql_advisor.template_registry.loader import (
    get_template_registry,
)
from activiti_mediation_template_sql_advisor.template_registry.resolver import (
    resolve_template_from_plan,
)


def setup_function():
    get_template_registry.cache_clear()


def test_resolve_template_alias_exact():
    result = resolve_template_from_plan(
        user_requirement="For Prepaid Base Plan ECM request, add attribute X with value 1",
        template_phrase="Prepaid Base Plan ECM request",
        external_system="ECM",
    )

    assert result.is_resolved is True
    assert result.template_id == "MT_ECM_PRE_BASEPLAN"
    assert result.match_type in {"alias_exact", "planner_phrase_exact", "fuzzy"}


def test_resolve_template_not_found():
    result = resolve_template_from_plan(
        user_requirement="For Nonexistent Acme Widget Template 9999 request, add X",
        template_phrase="Nonexistent Acme Widget Template 9999 request",
        external_system="",
    )

    assert result.is_resolved is False
    assert result.template_id == ""
    assert result.match_type == "not_found"


def test_resolve_template_id_in_text():
    result = resolve_template_from_plan(
        user_requirement="Update MT_ECM_PRE_BASEPLAN attribute Foo to value 1",
        template_phrase="",
        external_system="",
    )

    assert result.is_resolved is True
    assert result.template_id == "MT_ECM_PRE_BASEPLAN"
    assert result.match_type == "template_id_exact"
