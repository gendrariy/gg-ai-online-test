import re


def parse_bagnumber_filter(text: str) -> str:
    """
    Фильтр по полю [BagNumber].

    Примеры, которые должен ловить:
      - FG2520018
      - FG-2520018
      - FG#2520018
      - bag FG2520018
      - FG2520018 orders
      - repair orders FG2520018
    """
    if not text:
        return ""

    t_raw = text.upper()

    # Нормализация:
    #   FG-2522981 / FG#2522981 → FG2522981
    t = re.sub(r"\bFG\W*([0-9]{4,}[A-Z0-9]*)\b", r"FG\1", t_raw)

    # BagNumber: ТОЛЬКО коды, начинающиеся с FG + минимум 4 цифры
    bag_pattern = re.compile(r"\b(FG[0-9]{4,}[A-Z0-9]*)\b")

    candidates: set[str] = set()

    for m in bag_pattern.finditer(t):
        token = m.group(1).strip()
        if not token:
            continue
        candidates.add(token)

    if not candidates:
        return ""

    field = "UCase(LTrim(RTrim([BagNumber])))"

    if len(candidates) == 1:
        bag = next(iter(candidates)).replace("'", "''")
        return f" AND ({field} = '{bag}')"

    quoted = ["'" + b.replace("'", "''") + "'" for b in sorted(candidates)]
    in_list = ",".join(quoted)
    return f" AND ({field} IN ({in_list}))"

    for m in bag_pattern.finditer(t):
        token = m.group(1).strip()
        if not token:
            continue
        candidates.add(token)

    if not candidates:
        return ""

    field = "UCase(LTrim(RTrim([BagNumber])))"

    if len(candidates) == 1:
        bag = next(iter(candidates)).replace("'", "''")
        return f" AND ({field} = '{bag}')"

    # несколько BagNumber -> IN ('FG2520018','FG2520019',...)
    quoted = ["'" + b.replace("'", "''") + "'" for b in sorted(candidates)]
    in_list = ",".join(quoted)
    return f" AND ({field} IN ({in_list}))"
