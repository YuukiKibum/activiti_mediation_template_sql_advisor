from __future__ import annotations

from pathlib import Path


def find_project_root() -> Path:
    """Find the project root by walking upward from cwd and this file."""
    candidates = [Path.cwd().resolve(), Path(__file__).resolve()]

    for start in candidates:
        for path in [start, *start.parents]:
            if (path / "pyproject.toml").exists() or (path / "data" / "expression_rules").exists():
                return path

    return Path.cwd().resolve()


def data_dir() -> Path:
    return find_project_root() / "data" / "expression_rules"


def kb_path() -> Path:
    return data_dir() / "util-dsl-kb.jsonl"


def index_path() -> Path:
    return data_dir() / "dsl_index.pkl"


def system_prompt_path() -> Path:
    return Path(__file__).resolve().parent / "system_prompt.md"
