import re

# Явные customer-имена / коды, которые НЕЛЬЗЯ считать стилем
EXCLUDED_STYLE_TOKENS = {
    "AUSRTALIA",  # так, как у тебя в базе
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
    "TALON",
    "TROY",
    "VANCOUVER",
    "VISTA",
}


def parse_style_filter(text: str) -> str:
    """
    Фильтр по полю [style].

    Идея:
      - вытаскиваем кандидатов на style из текста
      - игнорируем очевидные не-style токены:
          * любые коды, начинающиеся с SO/PO/FG
          * NS-/DD-/SV-/DJ- префиксы
          * customer-имена из EXCLUDED_STYLE_TOKENS
      - по каждому найденному стилю строим:
          UCase(LTrim(RTrim([style]))) LIKE '%.%'

    Также поддерживает отрицания:
      not 4710 / style not 4710 / orders without 4710 / does not include 4710
      -> AND NOT ( ... LIKE '%4710%' ... )

    Возвращает:
      ""  — если ничего не найдено
      " AND (...)" / " AND NOT (...)" — SQL-фрагмент для WHERE
    """
    if not text:
        return ""

    token_re = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\./\\]*")
    style_codes: list[str] = []
    neg_style_codes: list[str] = []

    # Числа, которые явно относятся к "casting lot" или "lot" — их не считаем стилем
    lot_numbers: set[str] = set()

    # casting lot 1460 / casting lots 1460 / casting lot UT#1460
    for m in re.finditer(
        r"\bcasting\s+lots?\s+([A-Za-z0-9#\-]+)\b", text, flags=re.IGNORECASE
    ):
        raw = m.group(1).strip()
        if not raw:
            continue
        m_num = re.search(r"(\d+)", raw)
        if m_num:
            lot_numbers.add(m_num.group(1))

    # lot 1460 / lot UT#1460
    for m in re.finditer(
        r"\blot\s+([A-Za-z0-9#\-]+)\b", text, flags=re.IGNORECASE
    ):
        raw = m.group(1).strip()
        if not raw:
            continue
        m_num = re.search(r"(\d+)", raw)
        if m_num:
            lot_numbers.add(m_num.group(1))

    casting_lot_numbers: set[str] = set()
    for m in re.finditer(r"\bcasting\s+lots?\s+(\d+)\b", text, flags=re.IGNORECASE):
        lot_num = m.group(1).strip()
        if lot_num:
            casting_lot_numbers.add(lot_num)

    # --- НОВОЕ: коды после "po ..." — НЕ style ---
    # Примеры:
    #   po 7162946
    #   po AZ-110986
    #   po DD-103433\TB-BC-2025-1
    po_tokens: set[str] = set()
    for m in re.finditer(r"\bpo\s+([A-Za-z0-9\\\/\-]+)", text, flags=re.IGNORECASE):
        code = m.group(1).strip()
        if code:
            po_tokens.add(code.upper())

    # --- НОВОЕ: коды после "job / job number / jobnumber / jn ..." — НЕ style ---
    job_tokens: set[str] = set()
    for m in re.finditer(
        r"\b(?:job\s*number|jobnumber|job|jn)\s*#?\s*([A-Za-z0-9\\\/\-]+)\b",
        text,
        flags=re.IGNORECASE,
    ):
        code = m.group(1).strip()
        if code:
            job_tokens.add(code.upper())

   
    so_tokens: set[str] = set()
    for m in re.finditer(r"\bso\s+([A-Za-z0-9\\\/\-]+)", text, flags=re.IGNORECASE):
        code = m.group(1).strip()
        if code:
            so_tokens.add(code.upper())


    # --- НОВОЕ: отрицания по style ---
    # Поддержка:
    #   not 4710
    #   style not 4710
    #   orders without 4710 / without style 4710
    #   does not include 4710 / not include 4710
    neg_tokens: set[str] = set()
    neg_patterns = [
        r"\b(?:style\s+)?not\s+([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bwithout\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bdoes\s+not\s+include\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bdoesn't\s+include\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bdon't\s+include\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bdont\s+include\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bnot\s+include\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bnot\s+included\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
        r"\bnot\s+including\s+(?:style\s+)?([A-Za-z0-9][A-Za-z0-9\-\./\\]*)",
    ]
    for pat in neg_patterns:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            raw = m.group(1).strip()
            if raw:
                neg_tokens.add(raw.upper())

    for m in token_re.finditer(text):
        token = m.group(0).strip()
        if len(token) < 3:
            continue

        lower = token.lower()
        upper = token.upper()

        # Любые коды, начинающиеся с SO / PO / FG — не style
        # (это SalesOrder, CustomerPO и BagNumber)
        if upper.startswith("SO") or upper.startswith("PO") or upper.startswith("FG"):
            continue

        # Посчитаем количество цифр
        digit_count = sum(1 for ch in token if ch.isdigit())

        # Должна быть хотя бы одна цифра
        if digit_count == 0:
            continue

        # --- НЕ считать год стилем ---
        if token.isdigit() and len(token) == 4:
            year = int(token)
            if 1900 <= year <= 2099:
                continue

        # --- Если токен — номер casting lot, не считаем его стилем ---
        # Например, в запросе "casting lot 1462" число 1462
        if token in casting_lot_numbers:
            continue

        if token in lot_numbers:
            continue

        # --- НОВОЕ: если токен явно пришёл из "po ...", не считаем стилем ---
        if upper in po_tokens:
            continue

        if upper in job_tokens:
            continue

        if upper in so_tokens:
            continue


        # --- Короткие коды с одной цифрой (типа D4D, A3B, X1Z) считаем НЕ style ---
        # len <= 4 и ровно 1 цифра → вероятнее customer / внутренний код, чем style
        if len(token) <= 4 and digit_count == 1:
            continue

        # --- Если токен выглядит как BagNumber (FG2520018...), НЕ считаем стилем ---
        # На сегодня стандарт: префикс FG + минимум 4 цифры
        if re.match(r"^FG[0-9]{4,}[A-Z0-9]*$", upper):
            continue

        if upper in EXCLUDED_STYLE_TOKENS:
            continue

        # Коды вида AZ-110901 — это PO / заказ, не style
        if re.match(r"^az-\d{3,}$", lower):
            continue

        # Всё, что выглядит как PO-/SO-код, не считаем стилем.
        if re.match(r"^(so|po)[#\-][A-Za-z0-9]", lower):
            continue
        if re.match(r"^(so|po)[a-z]{2,}-\d{3,}", lower):
            continue

        # Явные префиксы кодов NS-/DD-/SV-/DJ- — тоже не style
        if re.match(r"^(ns|dd|sv|dj)[\-\_\\\/]", lower):
            continue

        # --- BagNumber вида FG2522981 / FG-2522981 / FG#2522981 НЕ считаем стилем ---
        # Все bag-номера у тебя начинаются с FG + цифры → выкидываем такие токены из style
        if re.match(r"^FG[-#]?\d{4,}$", upper):
            continue

        # Коды с обратным слэшем/слэшем типично для PO: AZ-110901\10-1009-73207 — НЕ считаем стилем
        if "\\" in token or "/" in token:
            continue

        # Коды с обратным слэшем/слэшем типично для PO: AZ-110901\10-1009-73207 — НЕ считаем стилем
        if "\\" in token or "/" in token:
            continue

        # Если это токен, явно попавший в отрицание — считаем его отрицательным style
        # (и НЕ добавляем в позитивные style_codes)
        if upper in neg_tokens:
            neg_style_codes.append(token)
            continue

        # Исключение: сложные ювелирные стили типа FI-2603-WT-925-W считаем style,
        # даже если там несколько числовых сегментов (иначе их съедает логика длинных PO/SO).
        if lower.startswith("fi-"):
            style_codes.append(token)
            continue

        # Если очень похоже на длинный PO/SO (3+ сегмента с цифрами) — тоже пропустим
        parts = token.split("-")
        digit_segments = sum(1 for p in parts if p.isdigit() and len(p) >= 3)
        if digit_segments >= 2 and len(parts) >= 3:
            continue

        style_codes.append(token)

    if not style_codes and not neg_style_codes:
        return ""

    def _normalize(codes: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for c in codes:
            u = c.upper().replace("'", "''")  # экранируем '
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    pos = _normalize(style_codes)
    neg = _normalize(neg_style_codes)

    field = "UCase(LTrim(RTrim([style])))"
    sql = ""

    if pos:
        pos_clauses = [f"{field} LIKE '%{code}%'" for code in pos]
        if len(pos_clauses) == 1:
            sql += f" AND ({pos_clauses[0]})"
        else:
            sql += " AND (" + " OR ".join(pos_clauses) + ")"

    if neg:
        neg_clauses = [f"{field} LIKE '%{code}%'" for code in neg]
        if len(neg_clauses) == 1:
            sql += f" AND NOT ({neg_clauses[0]})"
        else:
            sql += " AND NOT (" + " OR ".join(neg_clauses) + ")"

    return sql
