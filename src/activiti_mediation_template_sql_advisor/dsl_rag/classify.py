from __future__ import annotations

import argparse
import re
from typing import Optional


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _has_any(text: str, markers: list[str]) -> bool:
    normalized = f" {_normalize_spaces(text).lower()} "
    return any(marker.lower() in normalized for marker in markers)


def _has_dotted_json_path(text: str) -> bool:
    """
    Detect JSON-looking dotted paths like:

    allowances.voicePlanAllowances.preferredNumberAllowance.freebies

    We require at least 2 dots to avoid classifying ordinary words too aggressively.
    """
    return bool(
        re.search(
            r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){2,}\b",
            text or "",
        )
    )


def _mentions_evaluator_c_context(query: str) -> bool:
    """
    Evaluator C — evalAttribute.

    JSON-config-driven / positional-parameter evaluator.
    """
    return _has_any(
        query,
        [
            " param_",
            " positional parameter ",
            " positional parameters ",
            " positional param ",
            " positional params ",
            " config map ",
            " contents map ",
            " content map ",
            " contents dictionary ",
            " config dictionary ",
            " contents/config ",
            " paramvalues ",
            " param values ",
            " pipe-separated input ",
            " pipe separated input ",
            " $c. ",
            " $c ",
        ],
    ) or "param_" in (query or "").lower() or "$c." in (query or "").lower()


def _mentions_evaluator_b_context(query: str) -> bool:
    """
    Evaluator B — getCorrespondingAttributeValue.

    Bespoke project DTO attribute / projectDTOJsonValue / poAttributes evaluator.
    """
    return _has_any(
        query,
        [
            " dto ",
            " dto field ",
            " dto attribute ",
            " dto variable ",
            " project dto ",
            " bespokeproject ",
            " bespoke project ",
            " poattributes ",
            " poattribute ",
            " json payload ",
            " json path ",
            " json field ",
            " payload field ",
            " from dto ",
            " from json ",
            " from payload ",
            " projectdtojsonvalue ",
            " project dto json value ",
            " mapped into dto ",
            " mapping into dto ",
        ],
    ) or _has_dotted_json_path(query)


def _mentions_evaluator_a_context(query: str) -> bool:
    """
    Evaluator A — getDynamicparamValue.

    ActivitiMediationParameter / workflow mediation / session-only evaluator.
    """
    return _has_any(
        query,
        [
            " mediation parameter ",
            " workflow parameter ",
            " activiti parameter ",
            " activitimediationparameter ",
            " session-only ",
            " session only ",
            " session variable ",
            " pure session value ",
            " workflow variable ",
            " order-info context ",
            " order info context ",
            " $sc_ ",
            " $oc_ ",
        ],
    )


def classify(query: str) -> Optional[str]:
    """
    Cheap deterministic evaluator classifier.

    Returns:
        "A" for getDynamicparamValue
            ActivitiMediationParameter / workflow mediation / session-only.

        "B" for getCorrespondingAttributeValue
            Bespoke project DTO attribute / projectDTOJsonValue / poAttributes.

        "C" for evalAttribute
            JSON-config-driven / PARAM_ / contents map / positional params.

        None when ambiguous.

    Decision order:
        1. C if query mentions PARAM_, positional params, config/contents map, $C.
        2. B if query mentions DTO/project attribute/poAttributes/JSON path.
        3. A if query mentions mediation/workflow/session-only with no DTO/JSON context.
        4. None if ambiguous.

    No LLM call is used here.
    """
    query = query or ""

    mentions_c = _mentions_evaluator_c_context(query)
    mentions_b = _mentions_evaluator_b_context(query)
    mentions_a = _mentions_evaluator_a_context(query)

    # C wins first because PARAM_/contents/config context changes how paths are evaluated.
    if mentions_c:
        return "C"

    # B wins over A when JSON/DTO/project attribute context exists.
    # Example: "session variable inside DTO mapping" still needs care, but if DTO path
    # context is present, the expression runs in DTO evaluator unless C is explicit.
    if mentions_b and not mentions_c:
        return "B"

    # A is only safe when it is mediation/workflow/session-only without DTO/JSON/C context.
    if mentions_a and not mentions_b and not mentions_c:
        return "A"

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify target evaluator A/B/C.")
    parser.add_argument("query", nargs="+")
    args = parser.parse_args()

    print(classify(" ".join(args.query)))


if __name__ == "__main__":
    main()