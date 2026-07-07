from __future__ import annotations

import argparse
import json
from pathlib import Path

from activiti_mediation_template_sql_advisor.dsl_rag.classify import classify
from activiti_mediation_template_sql_advisor.dsl_rag.retrieve import retrieve

ROOT = Path(__file__).resolve().parent
TEST_FILE = ROOT / "test_queries.jsonl"


def load_tests(path: Path = TEST_FILE) -> list[dict]:
    tests: list[dict] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                tests.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

    return tests


def run_retrieval_eval(tests: list[dict]) -> tuple[int, int]:
    passed = 0

    for test in tests:
        query = test["query"]
        expected_id = test.get("expected_record_id")
        evaluator = classify(query)
        records = retrieve(query, evaluator_filter=evaluator)
        ids = {record.get("id") for record in records}

        ok = expected_id in ids
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] retrieval | expected={expected_id} | evaluator={evaluator} | query={query}")

        if ok:
            passed += 1
        else:
            print("  retrieved_ids=", ", ".join(str(x) for x in sorted(ids)))

    return passed, len(tests)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate DSL retrieval hit-rate.")
    parser.add_argument("--file", type=Path, default=TEST_FILE)
    args = parser.parse_args()

    tests = load_tests(args.file)
    passed, total = run_retrieval_eval(tests)
    pct = (passed / total * 100) if total else 0.0
    print(f"\nRetrieval hit-rate: {passed}/{total} = {pct:.1f}%")

    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
