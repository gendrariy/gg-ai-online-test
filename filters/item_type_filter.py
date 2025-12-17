from __future__ import annotations
import re
from typing import List


# Все допустимые типы изделий из базы
ITEM_TYPES = [
    "RING", "EARRING", "PENDANT", "NECKLACE", "BRACELET",
    "BANGLE", "CHAINS", "COLOR STONE", "DIAMONDS",
    "LOOSE STONE", "PENDANT WITH CHAIN", "BUTTERFLY",
    "SAMPLE"
]


def _uc(s: str) -> str:
    return s.strip().upper()


def parse_item_type_filter(user_query: str, field: str = "[item_type]") -> str:
    """
    Создаёт SQL-фильтр item_type:
    - ring, pendant, bracelet ...
    - multiple types: ring and pendant
    - отрицания: NOT RING, NOT PENDANT, etc.
    """

    q = _uc(user_query)

    # -------------------------------------------------------------
    # 1) Выявляем отрицания (NOT RING, NOT PENDANT, ...)
    # -------------------------------------------------------------
    negations = []
    for itype in ITEM_TYPES:
        if f"NOT {itype}" in q:
            negations.append(itype)

    # -------------------------------------------------------------
    # 2) Выявляем позитивные item_type, исключая NOT
    # -------------------------------------------------------------
    matches: List[str] = []

    for itype in ITEM_TYPES:
        # точное нахождение слова
        pattern = r"\b" + re.escape(itype) + r"\b"

        if re.search(pattern, q):
            # если есть НАЙДЕННЫЙ тип, но также есть "NOT TYPE", не добавляем
            if f"NOT {itype}" not in q:
                matches.append(itype)

    # -------------------------------------------------------------
    # 3) Формируем SQL
    # -------------------------------------------------------------
    f = "UCase(LTrim(RTrim(" + field + ")))"
    sql_parts = []

    # Позитивные типы (например RING, PENDANT)
    if matches:
        pos_clause = "(" + " OR ".join([f"{f} = '{t}'" for t in matches]) + ")"
        sql_parts.append(pos_clause)

    # Отрицания (например NOT (item_type = 'RING'))
    if negations:
        neg_clause = " AND ".join([f"NOT ({f} = '{t}')" for t in negations])
        sql_parts.append(neg_clause)

    if not sql_parts:
        return ""

    return " AND " + " AND ".join(sql_parts)
