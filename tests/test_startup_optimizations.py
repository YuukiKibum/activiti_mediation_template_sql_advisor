from activiti_mediation_template_sql_advisor.dsl_rules.attribute_value_runtime_spec import (
    get_rulebook_prompt_summary,
)
from activiti_mediation_template_sql_advisor.graph.builder import (
    build_advisor_graph,
    get_advisor_graph,
)


def test_get_advisor_graph_is_singleton():
    first = get_advisor_graph()
    second = get_advisor_graph()

    assert first is second
    assert first is not build_advisor_graph()


def test_get_rulebook_prompt_summary_is_cached():
    first = get_rulebook_prompt_summary()
    second = get_rulebook_prompt_summary()

    assert first is second
    assert "ATTRIBUTE_VALUE RUNTIME SPEC SUMMARY" in first
