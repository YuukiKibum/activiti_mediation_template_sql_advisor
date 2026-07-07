from __future__ import annotations

import argparse
import json
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer

from activiti_mediation_template_sql_advisor.dsl_rag.paths import index_path, kb_path
from activiti_mediation_template_sql_advisor.dsl_rag.tokenization import tokenizer


def build_embedding_text(record: dict[str, Any]) -> str:
    """
    Build embedding/index text from only the fields required by the guide:
    token, description, example_request, trigger_phrases, constraints.
    """
    parts = [
        str(record.get("token", "") or ""),
        str(record.get("description", "") or ""),
        str(record.get("example_request", "") or ""),
        " ".join(str(x) for x in (record.get("trigger_phrases", []) or [])),
        " ".join(str(x) for x in (record.get("constraints", []) or [])),
    ]
    return "\n".join(part for part in parts if part.strip())


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"KB not found at {path}. Put util-dsl-kb.jsonl in data/expression_rules/."
        )

    records: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc}") from exc

            if "id" not in record:
                raise ValueError(f"Invalid record at line {line_number}: missing id")

            records.append(record)

    return records


def build_token_index(records: list[dict[str, Any]]) -> dict[str, list[int]]:
    token_index: dict[str, list[int]] = defaultdict(list)

    for idx, record in enumerate(records):
        values = [
            str(record.get("id", "") or ""),
            str(record.get("token", "") or ""),
            str(record.get("syntax", "") or ""),
        ]

        for value in values:
            if value:
                token_index[value.lower()].append(idx)

        token = str(record.get("token", "") or "")
        prefix_match = re.match(r"^(\$[A-Za-z_]+|PARAM_\d+|VAL_)", token)
        if prefix_match:
            token_index[prefix_match.group(1).lower()].append(idx)

    return dict(token_index)


def ingest(kb_file: Path | None = None, output_file: Path | None = None) -> dict[str, Any]:
    kb_file = kb_file or kb_path()
    output_file = output_file or index_path()

    records = load_records(kb_file)
    embedding_texts = [build_embedding_text(record) for record in records]

    vectorizer = TfidfVectorizer(tokenizer=tokenizer, lowercase=True, token_pattern=None)
    matrix = vectorizer.fit_transform(embedding_texts)

    payload = {
        "records": records,
        "embedding_texts": embedding_texts,
        "vectorizer": vectorizer,
        "matrix": matrix,
        "token_index": build_token_index(records),
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("wb") as file:
        pickle.dump(payload, file)

    counts = Counter(str(record.get("evaluator", "missing")) for record in records)

    return {
        "total_records": len(records),
        "counts_by_evaluator": dict(sorted(counts.items())),
        "kb_path": str(kb_file),
        "index_path": str(output_file),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest util-dsl-kb.jsonl into local hybrid index.")
    parser.add_argument("--kb", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    summary = ingest(args.kb, args.out)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
