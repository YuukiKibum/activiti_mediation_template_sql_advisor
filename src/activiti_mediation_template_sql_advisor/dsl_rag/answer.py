from __future__ import annotations

import argparse
import json
import os
from dotenv import load_dotenv
from typing import Any, Optional

from activiti_mediation_template_sql_advisor.dsl_rag.classify import classify
from activiti_mediation_template_sql_advisor.dsl_rag.paths import system_prompt_path
from activiti_mediation_template_sql_advisor.dsl_rag.retrieve import retrieve

load_dotenv()

EVALUATOR_DECISION_INSTRUCTIONS = """
You must decide which of THREE evaluators a given expression will run through
BEFORE choosing any DSL token. Do not skip this step. Tokens from one
evaluator are not valid in another, even when they look identical.

EVALUATOR A — getDynamicparamValue (ActivitiMediationParameter / workflow mediation)
Signals that point here:
  - Query mentions: "mediation parameter", "workflow parameter", "Activiti
    parameter", "session-only", "session variable" with NO mention of a
    DTO, JSON payload, or project attribute.
  - The target is something consumed by an Activiti workflow step, not a
    DTO/JSON field.
  - No JSON document is involved at all — only the session map, or the
    workflow/order-info context objects ($SC_ / $OC_).

EVALUATOR B — getCorrespondingAttributeValue (Bespoke project DTO attribute)
Signals that point here:
  - Query mentions: "DTO field", "DTO attribute", "project DTO",
    "poAttributes", "BespokeProject", or a dotted JSON-looking path such as
    "allowances.something.something".
  - The target is a field being mapped INTO a DTO from a JSON payload
    (projectDTOJsonValue).
  - No mention of positional/pipe-separated parameters or a "contents"
    config map.
  - IMPORTANT: this evaluator does NOT normalize a leading '$.' — whatever
    is authored is passed verbatim into JsonPath.read(). If '$.' matters
    for the answer, this is the evaluator where it actually matters.

EVALUATOR C — evalAttribute (JSON-config-driven, newer evaluator)
Signals that point here:
  - Query mentions: "PARAM_", "positional parameter", "config map",
    "contents map", or "$C." lookups.
  - The context explicitly involves paramValues (pipe-separated inputs)
    or a contents/config dictionary alongside the DTO JSON.
  - IMPORTANT: this evaluator strips a leading '$.' before its real
    JsonPath call regardless of whether the author included it — so '$.'
    is functionally optional here, unlike Evaluator B.

DECISION PROCEDURE (follow in order):
1. Does the query mention positional params (PARAM_) or a config/contents
   map? -> Evaluator C.
2. Otherwise, does the query mention a DTO/project attribute, or a JSON
   field path, with no mention of a mediation/workflow parameter? ->
   Evaluator B.
3. Otherwise, does the query mention a mediation parameter, workflow
   variable, or pure session value with no JSON/DTO context? -> Evaluator A.
4. If none of the above signals are clearly present, or the query is
   genuinely ambiguous (e.g. it just says "this field" with no context
   about where the field lives), DO NOT GUESS. State your best guess
   evaluator explicitly as an assumption, and ask the user to confirm
   which evaluator applies before finalizing the expression — especially
   if the correct token or the '$.' prefix requirement would differ
   between evaluators for this specific request.

Use only the retrieved KB records. The retriever has already filtered normal
records by evaluator and included mapping/unsupported records. Never mix syntax
from two evaluators in one final answer.
""".strip()


ANSWER_SAFETY_RULES = """
Additional answer safety rules:

1. Use only retrieved KB records.
   Do not invent tokens, wrappers, prefixes, suffixes, or helper functions.

2. Do not prepend $EVAL_ to the whole expression.
   $EVAL_ is only valid inside a mapping RESULT value when the selected KB
   record explicitly supports MAP-eval behavior.

   Correct MAP-eval-style usage inside mapping result:
     someField#true|$EVAL_otherField,ELSE|0

   Wrong top-level usage:
     $EVAL_someField#true|1,ELSE|0

3. For MAP-general:
   - The mapping syntax is a suffix on the evaluated source expression.
   - Choose the source expression shape based on the selected evaluator and the
     retrieved KB records.
   - For Evaluator B, if the KB says leading '$.' is required for JsonPath, use:
       $.fieldName#KEY|RESULT,ELSE|DEFAULT
   - For Evaluator C, if the KB says leading '$.' is optional/inert, prefer:
       fieldName#KEY|RESULT,ELSE|DEFAULT

4. Never output $fieldName unless the selected KB syntax explicitly requires that shape.
   In particular:
     Wrong: $subscriberType#PREPAID|1,ELSE|0

5. Do not return placeholders in the final expression.
   Wrong:
     $.<attribute>#PREPAID|1,ELSE|0

6. If an unsupported retrieved record matches the request, treat it as authoritative.
   Return unsupported and include the record guidance.

7. If the selected expression depends on an assumption, say the assumption clearly.
""".strip()


def load_system_prompt() -> str:
    return system_prompt_path().read_text(encoding="utf-8")


def build_context(records: list[dict[str, Any]]) -> str:
    blocks: list[str] = []

    for record in records:
        record_id = record.get("id", "UNKNOWN")
        blocks.append(
            f"[Record {record_id}]\n"
            + json.dumps(record, indent=2, ensure_ascii=False)
        )

    return "\n\n".join(blocks)


def build_user_message(
    *,
    query: str,
    evaluator_filter: Optional[str],
    records: list[dict[str, Any]],
) -> str:
    context = build_context(records)

    evaluator_text = evaluator_filter or "ambiguous / not deterministically classified"

    return f"""
Deterministic evaluator classification result:
{evaluator_text}

Evaluator decision instructions:
{EVALUATOR_DECISION_INSTRUCTIONS}

Answer safety rules:
{ANSWER_SAFETY_RULES}

Retrieved context:
{context}

User request:
{query}

Task:
Return the best DSL answer using only the retrieved KB records.

Your answer must:
- State the evaluator being used.
- State the selected KB record id.
- Return either a supported final RHS expression or an explicit unsupported answer.
- If supported, return one final expression clearly.
- If unsupported, include the retrieved correct_response_guidance when available.
""".strip()


def answer(query: str, evaluator: Optional[str] = None) -> str:
    """
    Assemble context and return the raw LLM response.

    No post-processing is done. If retrieval/context is wrong, fix retrieval instead
    of injecting syntax after the LLM call.
    """
    evaluator_filter = evaluator or classify(query)
    records = retrieve(query, evaluator_filter=evaluator_filter)
    system_prompt = load_system_prompt()

    user_message = build_user_message(
        query=query,
        evaluator_filter=evaluator_filter,
        records=records,
    )

    try:
        from openai import OpenAI
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The openai package is required for answer generation. Install it with: uv add openai"
        ) from exc

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")
    client = OpenAI()

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    return response.choices[0].message.content or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Answer a Util.java DSL translation request.")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--evaluator", choices=["A", "B", "C"], default=None)
    parser.add_argument("--show-context", action="store_true")
    args = parser.parse_args()

    query = " ".join(args.query)
    evaluator_filter = args.evaluator or classify(query)
    records = retrieve(query, evaluator_filter=evaluator_filter)

    if args.show_context:
        print(build_context(records))
        return

    print(answer(query, evaluator=args.evaluator))


if __name__ == "__main__":
    main()