# Phase 1: Guide-compliant DSL RAG integration

Copy this package into the root of your existing project.

It adds:

- `src/activiti_mediation_template_sql_advisor/dsl_rag/`
- `data/expression_rules/util-dsl-kb.jsonl`
- `eval/test_queries.jsonl`
- `eval/run_eval.py`

It does not yet change your LangGraph nodes. First make DSL retrieval pass.

## Commands

```powershell
cd "C:\AI Agent Projects\Python_Projects\activiti_mediation_template_sql_advisor"
uv add scikit-learn openai
uv run python -m activiti_mediation_template_sql_advisor.dsl_rag.ingest
uv run python -m activiti_mediation_template_sql_advisor.dsl_rag.retrieve --test
uv run python eval/run_eval.py
```

Expected:

- 78 records loaded
- `OK: seconds-to-minutes unsupported record retrieved`
- 100% retrieval hit-rate

## LLM answer test

```powershell
$env:OPENAI_API_KEY="your-key"
uv run python -m activiti_mediation_template_sql_advisor.dsl_rag.answer "Convert freebies from seconds to minutes, cast to long"
```

Expected: unsupported. It should not invent `$MATH`, `$SEC_` reverse conversion, or any new token.
