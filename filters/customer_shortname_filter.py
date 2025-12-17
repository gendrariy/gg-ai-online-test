import re

# Короткие имена / коды, которые считаем именно customer (а не style и т.п.)
KNOWN_CUSTOMER_TOKENS = {
    "AUSRTALIA",  # так, как в базе
    "AZURE",
    "CHARM",
    "D4D",
    "DJ",
    "EMPRESS",
    "IJC",
    "LEDUC",
    "ONT",
    "ROGERS",
    "SHINY",
    "STAFF",
    "SUNCOR",
}

# Шаблон для отрицаний: not / no / without / does not include / not include
NEG_PREFIX = r"(?:NOT|NO|WITHOUT|WITH\s*OUT|DOES\s+NOT\s+INCLUDE|NOT\s+INCLUDE)"


def parse_customer_shortname_filter(text: str) -> str:
    """
    Дополнительный фильтр по полю [customer] для коротких имён/кодов без слова 'customer'.

    Примеры, для которых он НУЖЕН:
      - casting family not SUNCOR and not D4D
      - casting family SUNCOR orders

    ВАЖНО:
      - если в тексте есть слово "customer" -> этот фильтр НИЧЕГО не делает
        (чтобы не мешать основному customer_filter).
    """
    if not text:
        return ""

    t = text.upper()

    # 🔴 ВАЖНО:
    # если пользователь явно пишет "customer" / "not customer",
    # пусть полностью отрабатывает ТВОЙ основной customer_filter,
    # а этот дополнительный фильтр вообще не лезет.
    if "CUSTOMER" in t:
        return ""

    clean = t

    # --- 1. Отрицательные конструкции: not SUNCOR / without D4D / does not include AZURE ---

    # Собираем группу имён через | для регекса
    names_group = "|".join(sorted(KNOWN_CUSTOMER_TOKENS, key=len, reverse=True))
    neg_pattern = re.compile(rf"\b{NEG_PREFIX}\s+({names_group})\b")

    exclude: set[str] = set()

    for m in neg_pattern.finditer(t):
        name = m.group(1).upper()
        exclude.add(name)
        # вырезаем эту часть из clean, чтобы потом не считать её позитивом
        clean = clean.replace(m.group(0), " ")

    # --- 2. Позитивные упоминания имён (без not/without/does not include) ---

    include: set[str] = set()

    for name in KNOWN_CUSTOMER_TOKENS:
        if re.search(rf"\b{name}\b", clean):
            include.add(name)

    # если имя и в include, и в exclude -> отрицание важнее
    include -= exclude

    # если нет ни include, ни exclude — этот фильтр не нужен
    if not include and not exclude:
        return ""

    field = "UCase(LTrim(RTrim([customer])))"
    clauses = []

    # Позитивные customer:
    #   (customer LIKE '%SUNCOR%' OR customer LIKE '%AZURE%')
    if include:
        parts = [f"{field} LIKE '%{name}%'" for name in sorted(include)]
        if len(parts) == 1:
            clauses.append(parts[0])
        else:
            clauses.append("(" + " OR ".join(parts) + ")")

    # Отрицательные customer:
    #   NOT (customer LIKE '%SUNCOR%')
    for name in sorted(exclude):
        clauses.append(f"NOT ({field} LIKE '%{name}%')")

    if not clauses:
        return ""

    if len(clauses) == 1:
        return " AND (" + clauses[0] + ")"

    return " AND (" + " AND ".join(clauses) + ")"
