from __future__ import annotations

import argparse
import json
import math
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from activiti_mediation_template_sql_advisor.dsl_rag.ingest import ingest
from activiti_mediation_template_sql_advisor.dsl_rag.tokenization import tokenizer
from activiti_mediation_template_sql_advisor.dsl_rag.paths import index_path

TOP_K = 12


def load_index(path: Path | None = None) -> dict[str, Any]:
    path = path or index_path()

    if not path.exists():
        # Keep first-run user experience simple.
        ingest()

    with path.open("rb") as file:
        return pickle.load(file)


def _allowed_by_filter(record: dict[str, Any], evaluator_filter: Optional[str]) -> bool:
    if evaluator_filter is None:
        return record.get("evaluator") in {"A", "B", "C", "mapping", "unsupported"}

    return record.get("evaluator") == evaluator_filter


def _normal_candidates(records: list[dict[str, Any]], evaluator_filter: Optional[str]) -> list[int]:
    return [
        i
        for i, record in enumerate(records)
        if _allowed_by_filter(record, evaluator_filter)
    ]


def _mapping_indices(records: list[dict[str, Any]]) -> list[int]:
    return [i for i, record in enumerate(records) if record.get("evaluator") == "mapping"]


def _unsupported_indices(records: list[dict[str, Any]]) -> list[int]:
    return [i for i, record in enumerate(records) if record.get("evaluator") == "unsupported"]


def _dedupe_indices(indices: list[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []

    for idx in indices:
        if idx in seen:
            continue

        seen.add(idx)
        result.append(idx)

    return result


def _direct_lookup(query: str, index: dict[str, Any]) -> list[int]:
    """
    Pin exact token/id matches at top.

    Guide patterns:
    - $TOKEN
    - PARAM_<n>
    - bare VAL_
    """
    token_index: dict[str, list[int]] = index["token_index"]

    literals = re.findall(r"\$[A-Za-z_]+|PARAM_\d+|VAL_", query or "")
    hits: list[int] = []

    for literal in literals:
        hits.extend(token_index.get(literal.lower(), []))

    # Direct ID mentions help eval/debug commands.
    for record_id in re.findall(r"[A-Z]+-[A-Za-z0-9_\-]+", query or ""):
        hits.extend(token_index.get(record_id.lower(), []))

    return _dedupe_indices(hits)


def _vector_search(
    query: str,
    index: dict[str, Any],
    candidate_indices: list[int],
    top_k: int,
) -> list[tuple[int, float]]:
    vectorizer = index["vectorizer"]
    matrix = index["matrix"]

    if not query or not candidate_indices:
        return []

    query_vector = vectorizer.transform([query])
    candidate_matrix = matrix[candidate_indices]
    scores = (candidate_matrix @ query_vector.T).toarray().ravel()

    ranked = [
        (candidate_indices[i], float(score))
        for i, score in enumerate(scores)
        if score > 0
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:top_k]


def _bm25_search(
    query: str,
    index: dict[str, Any],
    candidate_indices: list[int],
    top_k: int,
) -> list[tuple[int, float]]:
    records = index["records"]
    texts = index["embedding_texts"]

    query_tokens = tokenizer(query)

    if not query_tokens or not candidate_indices:
        return []

    tokenized_docs = [tokenizer(texts[i]) for i in candidate_indices]
    doc_freq: Counter[str] = Counter()

    for tokens in tokenized_docs:
        for token in set(token.lower() for token in tokens):
            doc_freq[token] += 1

    avg_doc_len = sum(len(tokens) for tokens in tokenized_docs) / max(len(tokenized_docs), 1)
    total_docs = len(tokenized_docs)
    k1 = 1.5
    b = 0.75

    results: list[tuple[int, float]] = []

    for local_i, doc_tokens in enumerate(tokenized_docs):
        doc_len = len(doc_tokens) or 1
        term_freq = Counter(token.lower() for token in doc_tokens)
        score = 0.0

        for token in [token.lower() for token in query_tokens]:
            freq = term_freq.get(token, 0)

            if freq == 0:
                continue

            df = doc_freq.get(token, 0)
            idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
            denom = freq + k1 * (1 - b + b * doc_len / max(avg_doc_len, 1))
            score += idf * ((freq * (k1 + 1)) / denom)

        record = records[candidate_indices[local_i]]
        query_lower = query.lower()

        for phrase in record.get("trigger_phrases", []) or []:
            phrase_lower = str(phrase).lower().strip()

            if phrase_lower and phrase_lower in query_lower:
                score += 10.0

        if score > 0:
            results.append((candidate_indices[local_i], score))

    results.sort(key=lambda item: item[1], reverse=True)
    return results[:top_k]


def _rrf_merge(ranked_lists: list[list[tuple[int, float]]], k: int = 60) -> list[int]:
    scores: dict[int, float] = defaultdict(float)

    for ranked in ranked_lists:
        for rank, (idx, _score) in enumerate(ranked, start=1):
            scores[idx] += 1.0 / (k + rank)

    return [idx for idx, _score in sorted(scores.items(), key=lambda item: item[1], reverse=True)]


def retrieve(query: str, evaluator_filter: Optional[str] = None, *, top_k: int = TOP_K) -> list[dict[str, Any]]:
    """
    Hybrid retrieval from util-dsl-kb.jsonl.

    Implements the uploaded guide:
    - vector search top 12
    - BM25 search top 12
    - direct exact token lookup pinned at top
    - evaluator filter for normal results when known
    - always include mapping records
    - always include full unsupported partition
    - return full JSON payloads
    """
    index = load_index()
    records: list[dict[str, Any]] = index["records"]

    candidate_indices = _normal_candidates(records, evaluator_filter)

    direct_indices = _direct_lookup(query, index)
    direct_rank = [(idx, 1.0) for idx in direct_indices if idx in candidate_indices]

    vector_rank = _vector_search(query, index, candidate_indices, top_k=top_k)
    bm25_rank = _bm25_search(query, index, candidate_indices, top_k=top_k)

    fused = _rrf_merge([direct_rank, vector_rank, bm25_rank])

    final_indices: list[int] = []
    final_indices.extend(direct_indices)
    final_indices.extend(fused[:top_k])

    # Always include mapping and unsupported partitions, regardless of evaluator filter.
    final_indices.extend(_mapping_indices(records))
    final_indices.extend(_unsupported_indices(records))

    final_indices = _dedupe_indices(final_indices)

    return [records[i] for i in final_indices]


def assert_seconds_to_minutes_retrieval() -> None:
    records = retrieve("convert freebies from seconds to minutes", evaluator_filter="B")
    ids = {record.get("id") for record in records}
    assert "UNSUPPORTED-seconds-to-minutes" in ids, (
        "Retrieval is broken: UNSUPPORTED-seconds-to-minutes was not returned."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve Util.java DSL KB records.")
    parser.add_argument("query", nargs="*")
    parser.add_argument("--evaluator", choices=["A", "B", "C"], default=None)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        assert_seconds_to_minutes_retrieval()
        print("OK: seconds-to-minutes unsupported record retrieved")
        return

    context = retrieve(" ".join(args.query), evaluator_filter=args.evaluator)
    print(json.dumps(context, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
