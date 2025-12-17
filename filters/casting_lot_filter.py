from __future__ import annotations
import re


NEGATION_WORDS = ("NOT", "NO", "WITHOUT", "EXCEPT")


def _uc(s: str) -> str:
    return s.strip().upper()


def _field_norm(field: str) -> str:
    # Приводим к такому же виду, как в остальных фильтрах:
    # UCase(LTrim(RTrim([field])))
    return "UCase(LTrim(RTrim(" + field + ")))"


def parse_casting_lot_filter(user_query: str, field: str = "[casting_lot]") -> str:
    """
    Фильтр по номеру casting lot.

    Поддерживает:
      - "casting lot UT#1460"
      - "casting lot 1460"
      - "casting lot 1460 and 1470"
      - "casting lot UT#1460, US#1470"
      - "lot 1460" / "lot UT#1460"

    Логика:
      - если токен содержит только цифры (например, "1460"):
          → считаем, что пользователь не указал префикс,
            и ищем по подстроке:  field LIKE '%1460%'
      - если токен содержит буквы/символы (например, "UT#1460"):
          → считаем, что это полный код лота,
            и сравниваем строго: field = 'UT#1460'

      Отрицания:
        - "not casting lot 1460"
        - "without casting lot UT#1460"
        - "no lot 1460"
        - "except lot 1460"
    """

    U = _uc(user_query)

    # Если вообще нет слова LOT – ничего не делаем
    if "LOT" not in U:
        return ""

    # Ищем конструкции:
    #   CASTING LOT <values>
    #   LOT <values>
    #
    # <values> – последовательность токенов типа:
    #   1460
    #   UT#1460
    #   FG-123
    #   US/1460-1
    # разделённых запятой, AND, &
    pattern = r"(?:CASTING\s+LOT|LOT)\s+([A-Z0-9\-\/#]+(?:\s*(?:,|AND|&)\s*[A-Z0-9\-\/#]+)*)"

    lots: list[str] = []

    for m in re.finditer(pattern, U):
        values_str = m.group(1)
        parts = re.split(r"\s*(?:,|AND|&)\s*", values_str)
        for p in parts:
            p = p.strip()
            if p:
                lots.append(p)

    if not lots:
        return ""

    # Определяем отрицание:
    #  "not casting lot", "no lot", "without lot", "except lot"
    neg_pattern = r"(?:NOT|NO|WITHOUT|EXCEPT)\s+(?:CASTING\s+LOT|LOT)\b"
    is_neg = bool(re.search(neg_pattern, U))

    f = _field_norm(field)
    conds: list[str] = []

    for v in lots:
        # Только цифры → человек написал просто "1460"
        # => ищем это число как подстроку в лоте (UT#1460, XX-1460A и т.п.)
        if re.fullmatch(r"\d+", v):
            conds.append(f"{f} LIKE '%{v}%'")
        else:
            # Есть буквы/символы (#, -, /) → считаем это полным кодом
            conds.append(f"{f} = '{v}'")

    if not conds:
        return ""

    group_sql = "(" + " OR ".join(sorted(set(conds))) + ")"

    if is_neg:
        # NOT (...): исключаем указанные лоты
        return f" AND NOT {group_sql}"
    else:
        # Позитивный фильтр
        return f" AND {group_sql}"
