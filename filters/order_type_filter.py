import re

ORDER_TYPES = {
    "ACCESSORIES": ["ACCESSORIES", "ACCESSORY"],
    "BIG": ["BIG", "BIG ORDER"],
    "FAMILY": ["FAMILY"],
    "MOLD": ["MOLD"],
    "NONE": ["NONE"],  # only this word, any capitalization
    "REGULAR": ["REGULAR"],
    "REPAIR": ["REPAIR"],
    "SAMPLE": ["SAMPLE"],
    "SINGLE": ["SINGLE"]
}

# Words that should NOT trigger NONE
NONE_INVALID = ["NO", "NO ORDER", "EMPTY", "WITHOUT", "WITHOUT ORDER", "W/O", "NOORDER"]


def _uc(x: str) -> str:
    return x.strip().upper()


def parse_order_type_filter(user_query: str, field: str = "[order_type]"):
    """
    Возвращает SQL-фильтр по order_type:
    - позитивные фильтры: FAMILY, SINGLE, ...
    - негативные фильтры: NOT FAMILY, NOT SAMPLE, ...
    - группировка через AND
    """
    original = user_query
    U = _uc(user_query)

    # normalize spaces
    U = re.sub(r"\s+", " ", U)

    positives = set()
    negatives = set()

    # PREVENT invalid NONE: "no", "no order", "empty", etc.
    for bad in NONE_INVALID:
        if re.search(rf"\b{bad}\b", U):
            # ignore, do not treat as NONE
            U = re.sub(rf"\b{bad}\b", " ", U)

    # ---------- DETECT NEGATIVE ORDER TYPES ----------
    for otype, variants in ORDER_TYPES.items():
        for v in variants:
            # detect "NOT family"
            pattern = rf"\bNOT\s+{v}\b"
            if re.search(pattern, U, flags=re.IGNORECASE):
                negatives.add(otype)

    # ---------- DETECT POSITIVE ORDER TYPES ----------
    for otype, variants in ORDER_TYPES.items():
        if otype in negatives:
            continue  # skip positives if NOT detected
        for v in variants:
            pattern = rf"\b{v}\b"
            if re.search(pattern, U, flags=re.IGNORECASE):
                positives.add(otype)

    # If nothing detected — return empty (no filter)
    if not positives and not negatives:
        return ""

    sql_parts = []

    # ---------- POSITIVE CLAUSE ----------
    if positives:
        pos_sql = []
        for p in positives:
            pos_sql.append(
                f"UCase(LTrim(RTrim({field}))) = '{p}'"
            )
        sql_parts.append("(" + " OR ".join(pos_sql) + ")")

    # ---------- NEGATIVE CLAUSE ----------
    for n in negatives:
        sql_parts.append(
            f"NOT (UCase(LTrim(RTrim({field}))) = '{n}')"
        )

    # If both exist → AND join
    return " AND (" + " AND ".join(sql_parts) + ")"
