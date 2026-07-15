from __future__ import annotations

RULEBOOK_EVALUATOR = "RULEBOOK"

ALLOWED_EVALUATORS = {RULEBOOK_EVALUATOR}

ALLOWED_OPERATION_KINDS = {
    "fixed_literal",
    "source_field",
    "mapping",
    "unit_conversion_or_cast",
    "concat",
    "append_subkey",
    "unsupported",
}

APPEND_VALUE_OPERATION_KINDS = {
    "append_subkey",
    "fixed_literal",
    "source_field",
    "mapping",
    "unit_conversion_or_cast",
    "concat",
}

CONDITIONAL_SIGNALS = [
    " if ",
    "if ",
    " else",
    "otherwise",
    " when ",
    "map ",
    "mapping",
    " then ",
]

UNIT_CONVERSION_SIGNALS = [
    "convert",
    "seconds",
    "minutes",
    "hours",
    " to bytes",
    " to kb",
    " to mb",
    " to gb",
    "cast to",
    "as a long",
    "as an integer",
    "as a double",
]

SOURCE_FIELD_SIGNALS = [
    "dto field",
    "dto filed",
    "from dto",
    "from dto field",
    "source field",
    "input field",
    "take from field",
]

LIST_SIGNALS = [
    " as list ",
    " list from ",
    " split by ",
    " separated by comma",
    " comma separated",
]

COMPLEX_METHOD_SIGNALS = [
    "replace spaces with underscores",
    "replace space with underscore",
    "first item",
    "first value",
    "first element",
]

MAX_CLASSIFICATION_RETRIES = 1
MAX_EXPRESSION_EVALUATOR_RETRIES = 1

FIELD_PATH_PATTERN = r"(?:\$\.)?[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\[[^\]]+\])*"
