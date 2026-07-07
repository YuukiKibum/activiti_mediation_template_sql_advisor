from __future__ import annotations

import re


def tokenizer(text: str) -> list[str]:
    """Tokenizer that preserves DSL-ish symbols and dotted JSON paths."""
    return re.findall(
        r"\$[A-Za-z0-9_.$^#|,\-]+|PARAM_\d+|VAL_|[A-Za-z_][A-Za-z0-9_.]*|\d+(?:\.\d+)?",
        text or "",
        flags=re.IGNORECASE,
    )
