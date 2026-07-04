import re


TEMPLATE_ID_PATTERN = re.compile(r"^[A-Z0-9_]+$", re.IGNORECASE)


def normalize_template_id(template_id: str) -> str:
    """
    Validate and normalize a TEMPLATE_ID.

    Allowed:
        MT_ECM_PRE_BASEPLAN
        MT_RTF_TC_PREP_PLAN
        BCRM
        COMS

    Not allowed:
        empty value
        spaces
        quotes
        semicolons
        SQL-like text
    """
    value = (template_id or "").strip().upper()

    if not value:
        raise ValueError("template_id cannot be empty.")

    if not TEMPLATE_ID_PATTERN.match(value):
        raise ValueError(
            "template_id contains invalid characters. "
            "Only letters, numbers, and underscores are allowed."
        )

    return value


def clean_attribute_name(attribute_name: str) -> str:
    """
    Validate an ACT_MEDIATION_PARAMETER.ATTRIBUTE_NAME value.

    Attribute names can be mixed case, so we do not uppercase them.
    Example:
        poAttributes
        cfsServiceIdentifier
        AddToBillFlag
    """
    value = (attribute_name or "").strip()

    if not value:
        raise ValueError("attribute_name cannot be empty.")

    if len(value) > 100:
        raise ValueError("attribute_name is too long. Maximum length is 100.")

    return value


def clean_search_keyword(keyword: str) -> str:
    """
    Clean a search keyword used for template/parameter lookup.

    We uppercase it because our SQL search will use UPPER(...).
    """
    value = (keyword or "").strip()

    if not value:
        raise ValueError("keyword cannot be empty.")

    if len(value) > 100:
        raise ValueError("keyword is too long. Maximum length is 100.")

    return value.upper()


def clamp_limit(limit: int, minimum: int = 1, maximum: int = 200) -> int:
    """
    Keep query result limits within a safe range.

    Example:
        limit = 20      -> 20
        limit = 10000   -> 200
        limit = -5      -> 1
        limit = "abc"   -> 20
    """
    try:
        number = int(limit)
    except Exception:
        number = 20

    return max(minimum, min(number, maximum))