import re

NEG_PREFIX = r"(?:not|no|without|with\s*out|does\s+not\s+include|not\s+include|exclude|except)"


def parse_order_group_filter(text: str) -> str:
    """
    Фильтр по полю [order_grp].

    Значения в Access:
      Ausrtalia / Canada / Thailand / UK / USA

    Поддерживает:

      Позитив:
        - ready to ship order usa
        - reported orders uk
        - canada repair orders
        - thailand jobs
        - usa and canada orders

      Негатив:
        - orders not uk
        - not usa orders
        - ready to ship repair orders not canada
        - orders without uk
        - orders does not include uk
        - orders not include uk
        - orders exclude uk
        - orders except uk

      Комбинации:
        - orders not uk and not usa
            -> NOT IN ('UK','USA')
        - canada orders not uk
            -> IN ('CANADA') AND NOT IN ('UK')
    """
    if not text:
        return ""

    t = text.lower()
    clean = t  # сюда будем вырезать отрицательные конструкции

    # --- отрицательные паттерны для стран ---

    neg_usa_pat = re.compile(
        rf"\b{NEG_PREFIX}\s+(?:usa|u\.s\.a\.?|united\s+states|america)\b",
        re.I,
    )
    neg_canada_pat = re.compile(
        rf"\b{NEG_PREFIX}\s+canada\b",
        re.I,
    )
    neg_thailand_pat = re.compile(
        rf"\b{NEG_PREFIX}\s+(?:thailand|thai)\b",
        re.I,
    )
    neg_uk_pat = re.compile(
        rf"\b{NEG_PREFIX}\s+(?:uk|u\.k\.?|united\s+kingdom|england|britain|british)\b",
        re.I,
    )
    neg_aus_pat = re.compile(
        rf"\b{NEG_PREFIX}\s+(?:australia|aussie|australian)\b",
        re.I,
    )

    neg_usa = bool(neg_usa_pat.search(t))
    if neg_usa:
        clean = neg_usa_pat.sub(" ", clean)

    neg_canada = bool(neg_canada_pat.search(t))
    if neg_canada:
        clean = neg_canada_pat.sub(" ", clean)

    neg_thailand = bool(neg_thailand_pat.search(t))
    if neg_thailand:
        clean = neg_thailand_pat.sub(" ", clean)

    neg_uk = bool(neg_uk_pat.search(t))
    if neg_uk:
        clean = neg_uk_pat.sub(" ", clean)

    neg_aus = bool(neg_aus_pat.search(t))
    if neg_aus:
        clean = neg_aus_pat.sub(" ", clean)

    include: set[str] = set()
    exclude: set[str] = set()

    # --- отрицательные группы ---

    if neg_usa:
        exclude.add("USA")
    if neg_canada:
        exclude.add("CANADA")
    if neg_thailand:
        exclude.add("THAILAND")
    if neg_uk:
        exclude.add("UK")
    if neg_aus:
        # в базе опечатка: "Ausrtalia"
        exclude.add("AUSRTALIA")

    # --- позитивные группы (ищем уже в clean, где negative-конструкции вырезаны) ---

    # USA
    if (
        re.search(r"\busa\b", clean)
        or re.search(r"\bu\.s\.a\.?\b", clean)
        or re.search(r"\bunited\s+states\b", clean)
        or re.search(r"\bamerica\b", clean)
    ):
        include.add("USA")

    # CANADA
    if re.search(r"\bcanada\b", clean) or re.search(r"\bcanadian\b", clean):
        include.add("CANADA")

    # THAILAND
    if re.search(r"\bthailand\b", clean) or re.search(r"\bthai\b", clean):
        include.add("THAILAND")

    # UK / UNITED KINGDOM
    if (
        re.search(r"\buk\b", clean)
        or re.search(r"\bu\.k\.?\b", clean)
        or re.search(r"\bunited\s+kingdom\b", clean)
        or re.search(r"\bengland\b", clean)
        or re.search(r"\bbritain\b", clean)
        or re.search(r"\bbritish\b", clean)
    ):
        include.add("UK")

    # AUSTRALIA (в базе: "Ausrtalia")
    if (
        re.search(r"\baustralia\b", clean)
        or re.search(r"\baussie\b", clean)
        or re.search(r"\baustralian\b", clean)
    ):
        include.add("AUSRTALIA")

    # --- если ни позитивов, ни негативов — фильтр не нужен ---

    if not include and not exclude:
        return ""

    # Если какая-то страна одновременно и в include, и в exclude — исключение имеет приоритет
    # (на практике такое возможно, если пользователь напишет что-то противоречивое).
    include = include - exclude

    clauses = []

    field = "UCase(LTrim(RTrim([order_grp])))"

    if include:
        in_list = ",".join(f"'{g}'" for g in sorted(include))
        clauses.append(f"{field} IN ({in_list})")

    if exclude:
        not_in_list = ",".join(f"'{g}'" for g in sorted(exclude))
        clauses.append(f"{field} NOT IN ({not_in_list})")

    if not clauses:
        return ""

    return " AND (" + " AND ".join(clauses) + ")"
