import re


def parse_customer_filter(text: str) -> str:
    """
    Формирует SQL-фильтр по полю [customer].

    Работает только если в запросе явно есть слова,
    связанные с клиентом: customer / client / buyer / vendor / shop / store / cust.

    Поддерживает:
      - простые запросы:   "customer d4d" -> customer LIKE '%D4D%'
      - исключения:        "not customer d4d",
                           "customer not d4d"
         -> NOT (customer LIKE '%D4D%')
    """
    t = text.strip().lower()
    if not t:
        return ""

    # ключевые слова, при которых фильтр по customer разрешён
    customer_keys = ["customer", "client", "cust", "shop", "store", "vendor", "buyer"]

    # если ни одного "customer"-слова нет — фильтр по клиенту не строим
    if not any(k in t for k in customer_keys):
        return ""

    # --- список слов, которые игнорируем для customer ---
    # технические слова, даты, периоды, типы заказов и т.п.
    ignore_words = {
        "received", "receive",
        "casting", "cast",
        "ship", "shipping", "shipped",
        "due", "date", "pdate",
        "production",
        "order", "orders",
        "last", "next", "this", "previous",
        "week", "weeks", "month", "months", "year", "years", "day", "days",
        "from", "to", "up", "today", "yesterday", "tomorrow",
        "big", "small", "family", "single", "repair", "mold",
        "and", "or", "not",
        # месяцы
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        # МЕТАЛЛЫ и ЦВЕТА — ИГНОРИРУЕМ В CUSTOMER
        "gold", "silver", "slv", "plat", "platinum", "brass", "palladium",
        "white", "yellow", "rose", "red",
        # на всякий случай общие сокращения
        "wg", "yg", "rg",
        # ТИПЫ ИЗДЕЛИЙ — ТОЖЕ НЕ CUSTOMER
        "ring", "rings",
        "pendant", "pendants",
        "earring", "earrings",
        "necklace", "necklaces",
        "bracelet", "bracelets",
        # КАРАТЫ — тоже не customer
        "karat", "karats",
        "kt",
        "po", "so",
        "in", "process", "progress", "polish","jewellery", "jewelry"
        "setting", "qc", "quality", "repair", "rework", "finish", "finishing",
	# другие  
	"ready","not"


    }

    # --- 1) Отрицательные конструкции: "not customer d4d", "customer not d4d" ---

    neg_tokens = set()

    # "not customer d4d" / "not client d4d" / ...
    pattern1 = r"\bnot\s+(?:customer|client|cust|shop|store|vendor|buyer)\s+([a-z0-9_\-\\/]+)"
    # "customer not d4d" / "client not d4d" / ...
    pattern2 = r"\b(?:customer|client|cust|shop|store|vendor|buyer)\s+not\s+([a-z0-9_\-\\/]+)"

    for m in re.findall(pattern1, t):
        token = m.strip().strip(",;")
        if token:
            neg_tokens.add(token.lower())

    for m in re.findall(pattern2, t):
        token = m.strip().strip(",;")
        if token:
            neg_tokens.add(token.lower())
    neg_tokens = set()

    # "not customer d4d" / "not client d4d" / ...
    pattern1 = r"\bnot\s+(?:customer|client|cust|shop|store|vendor|buyer)\s+([a-z0-9_\-\\/]+)"
    # "customer not d4d" / "client not d4d" / ...
    pattern2 = r"\b(?:customer|client|cust|shop|store|vendor|buyer)\s+not\s+([a-z0-9_\-\\/]+)"
    # "not d4d" (без слова customer, но внутри запроса, где customer-слово уже есть)
    pattern3 = r"\bnot\s+([a-z0-9_\-\\/]+)"

    for m in re.findall(pattern1, t):
        token = m.strip().strip(",")
        if token:
            neg_tokens.add(token.lower())

    # Дополнительно: "not d4d" → тоже считаем отрицанием по customer,
    # но отбрасываем служебные слова, ключевые слова и чистые цифры.
    for m in re.findall(pattern3, t):
        token = m.strip().strip(",")
        if not token:
            continue
        wl = token.lower()
        if wl.isdigit():
            continue
        if wl in ignore_words:
            continue
        if wl in customer_keys:
            continue
        neg_tokens.add(wl)
#======

    neg_conditions = []
    for tok in sorted(neg_tokens):
        neg_conditions.append(
            f"NOT (UCase(LTrim(RTrim([customer]))) LIKE '%{tok.upper()}%')"
        )

    # --- 2) Положительные токены для LIKE (customer d4d, customer abc ...) ---

    # токены: буквы и цифры (d4d тоже поймаем)
    raw_tokens = re.findall(r"[a-z0-9]+", t)

    pos_tokens = []
    for w in raw_tokens:
        wl = w.lower()

        # Чисто числа (14, 10, 18, 2025 и т.п.) — не имена клиентов
        if wl.isdigit():
            continue

        if wl in ignore_words:
            continue
        if wl in customer_keys:
            continue
        if wl in neg_tokens:
            # уже используется в NOT customer, не добавляем как положительный
            continue
        pos_tokens.append(wl)

    pos_conditions = []
    for tok in sorted(set(pos_tokens)):
        pos_conditions.append(
            f"(UCase(LTrim(RTrim([customer]))) LIKE '%{tok.upper()}%')"
        )

    # --- 3) Формируем итоговый SQL-фрагмент ---

    if not pos_conditions and not neg_conditions:
        return ""

    clauses = []

    if pos_conditions:
        # (customer LIKE '%A%' OR customer LIKE '%B%')
        clauses.append("(" + " OR ".join(pos_conditions) + ")")

    if neg_conditions:
        # NOT(... ) AND NOT(... )
        clauses.append(" AND ".join(neg_conditions))

    # если есть и положительные, и отрицательные — объединяем через AND
    # AND ( (pos1 OR pos2 ...) AND NOT (...) AND NOT (...) )
    sql = " AND (" + " AND ".join(clauses) + ")"

    return sql
