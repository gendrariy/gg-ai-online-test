import re


def parse_salesorder_filter(text: str) -> str:
    if not text:
        return ""

    t = text.strip().lower()

    # --- убираем даты и ИЗОЛИРОВАННЫЕ годы 20xx, не трогая их внутри кодов ---
    # dd/mm/yyyy, dd-mm-yyyy и т.п.
    t_no_dates = re.sub(r"\b\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}\b", "", t)
    # год 20xx удаляем только если он отдельным "словом"
    t_no_dates = re.sub(r"(?<!\S)20\d{2}(?!\S)", "", t_no_dates)

    # --- НОРМАЛИЗАЦИЯ "кривых" форм SO/PO перед разбором ---

    fix_text = t_no_dates

    # 1) Любые формы "so: XXX", "so#XXX", "so=XXX", "so XXX" → "so XXX"
    #    То же самое для "po"
    fix_text = re.sub(r"\bso\W+([a-z0-9\\/\-]+)", r"so \1", fix_text)
    fix_text = re.sub(r"\bpo\W+([a-z0-9\\/\-]+)", r"po \1", fix_text)

    # 1b) Формы без разделителя: po4620195375 / so123456 → "po 4620195375" / "so 123456"
    fix_text = re.sub(r"\bso(\d{3,})\b", r"so \1", fix_text)
    fix_text = re.sub(r"\bpo(\d{3,})\b", r"po \1", fix_text)


    # 2) Старые спец-кейсы, которые у тебя уже были:

    # SONS-113004 -> "so ns-113004"
    fix_text = re.sub(r"\bsons-(\d{3,})\b", r"so ns-\1", fix_text)
    # PONS-113004 -> "po ns-113004"
    fix_text = re.sub(r"\bpons-(\d{3,})\b", r"po ns-\1", fix_text)

    # SO#NS-113004 / SO-NS-113004 -> "so ns-113004"
    fix_text = re.sub(r"\bso[#-](ns-\d{3,})\b", r"so \1", fix_text)
    # PO#NS-113004 / PO-NS-113004 -> "po ns-113004"
    fix_text = re.sub(r"\bpo[#-](ns-\d{3,})\b", r"po \1", fix_text)

    # Po#AZ-110901 / So#AZ-110901 → "po az-110901" / "so az-110901"
    fix_text = re.sub(r"\bpo#([a-z0-9\\/\-]+)\b", r"po \1", fix_text)
    fix_text = re.sub(r"\bso#([a-z0-9\\/\-]+)\b", r"so \1", fix_text)

    # формы без пробела: "soNS-113004", "soDD-048260", "soSV-074668", "poNS-...", ...
    fix_text = re.sub(
        r"\bso(ns-\d{3,}|dd-\d{3,}|sv-\d{3,}|dj-\d{3,})\b",
        r"so \1",
        fix_text,
    )
    fix_text = re.sub(
        r"\bpo(ns-\d{3,}|dd-\d{3,}|sv-\d{3,}|dj-\d{3,})\b",
        r"po \1",
        fix_text,
    )

    # Po-AZ-110901 / So-AZ-110901 → "po az-110901" / "so az-110901"
    fix_text = re.sub(r"\bpo-([a-z0-9\\/\-]+)\b", r"po \1", fix_text)
    fix_text = re.sub(r"\bso-([a-z0-9\\/\-]+)\b", r"so \1", fix_text)

    # PoAZ-110901, PoNS-112899, SoNS-112899, SoDD-048260 → "po az-110901" / "so ns-112899"
    fix_text = re.sub(r"\bpo([a-z]{2,}-\d{3,})\b", r"po \1", fix_text)
    fix_text = re.sub(r"\bso([a-z]{2,}-\d{3,})\b", r"so \1", fix_text)

    t_no_dates = fix_text
    tokens = t_no_dates.split()

    # --- флаги PO / SO (для положительных фильтров) ---
    is_po = ("po" in tokens) or ("customer po" in t_no_dates)
    is_so = ("so" in tokens) or ("sales order" in t_no_dates) or ("sale order" in t_no_dates)

    field_po = "UCase(LTrim(RTrim([CustomerPO])))"
    field_so = "UCase(LTrim(RTrim([SalesOrder])))"

    # ---------- НАЧАЛО: поиск отрицательных кодов с синонимами ----------
    neg_prefix = r"(?:not|without|except|no)"

    #   without po AZ-110901\10-1009-73207
    neg_po_codes = [
        m.group(1)
        for m in re.finditer(
            rf"\b{neg_prefix}\s+po\s+([a-z0-9\\\/\-]+)",
            t_no_dates,
        )
    ]

    #   without so SV-075075
    neg_so_codes = [
        m.group(1)
        for m in re.finditer(
            rf"\b{neg_prefix}\s+so\s+([a-z0-9\\\/\-]+)",
            t_no_dates,
        )
    ]

    #   without NS-112811
    neg_both_codes = [
        m.group(1)
        for m in re.finditer(
            rf"\b{neg_prefix}\s+((?:ns|dd|sv|dj)[\-–_a-z0-9\\\/]+)",
            t_no_dates,
        )
    ]

    neg_all_lower = {c.lower() for c in (neg_po_codes + neg_so_codes + neg_both_codes)}

    # --- ЯВНЫЕ SalesOrder через 'so <код>' (особенно для случаев 'po ... and so ...') ---
    direct_so_codes: list[str] = []
    if is_so:
        direct_so_codes = [
            m.group(1)
            for m in re.finditer(r"\bso\s+([a-z0-9\\/\-]+)", t_no_dates)
        ]
    # ---------- КОНЕЦ: поиск отрицательных кодов ----------

    codes: list[str] = []

    # --- коды после PO ---
    if is_po:
        codes.extend(
            re.findall(r"\bpo\s+([a-z0-9\\\/\-]+)", t_no_dates)
        )

    # --- коды после SO ---
    if is_so:
        codes.extend(
            re.findall(r"\bso\s+([a-z0-9\\\/\-]+)", t_no_dates)
        )

    # убираем дубликаты (на всякий случай)
    if codes:
        seen = set()
        uniq = []
        for c in codes:
            cl = c.lower()
            if cl in seen:
                continue
            seen.add(cl)
            uniq.append(c)
        codes = uniq

    # Если пользователь указал po/so, но мы не нашли явных кодов —
    # тогда уже пробуем общие паттерны (NS-, DD-, SV-, DJ-) внутри этого контекста.
    if not codes and (is_po or is_so):
        codes = re.findall(r"(?:ns|dd|sv|dj)[\-–_a-z0-9\\\/]+", t_no_dates)

    # И совсем fallback "DD-103433" — ТОЛЬКО если есть po/so
    if not codes and (is_po or is_so):
        m = re.search(r"\b[a-z]{1,3}[-_]\d{3,}\b", t_no_dates)
        if m:
            codes = [m.group(0)]

    # Если нет ни положительных, ни отрицательных кодов — выходим
    if not codes and not (neg_po_codes or neg_so_codes or neg_both_codes):
        return ""

    # --- разделяем на положительные (include) и отрицательные (exclude) ---
    pos_codes = [c for c in codes if c.lower() not in neg_all_lower]

    include_clauses: list[str] = []
    exclude_clauses: list[str] = []

    # ----- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТРИЦАТЕЛЬНЫХ КОДОВ -----
    def add_exclude_for_code(raw_code: str, target: str):
        raw = raw_code.upper().strip()
        raw = raw.replace("–", "-")

        def exclude_short(field: str) -> str:
            return "(" + " AND ".join(
                [
                    f"{field} <> '{raw}'",
                    f"{field} NOT LIKE '{raw}\\%'",
                    f"{field} NOT LIKE '{raw}-%'",
                ]
            ) + ")"

        def exclude_exact(field: str) -> str:
            return f"({field} <> '{raw}')"

        is_short = ("\\" not in raw and "/" not in raw and raw.count("-") == 1 and len(raw) < 30)

        if target in ("po", "both"):
            if is_short:
                exclude_clauses.append(exclude_short(field_po))
            else:
                exclude_clauses.append(exclude_exact(field_po))

        if target in ("so", "both"):
            if is_short:
                exclude_clauses.append(exclude_short(field_so))
            else:
                exclude_clauses.append(exclude_exact(field_so))

    # ----- СТРОИМ ПОЛОЖИТЕЛЬНЫЕ УСЛОВИЯ (include_clauses) -----
    for code in pos_codes:
        raw = code.upper().strip()
        raw = raw.replace("–", "-")  # длинное тире → обычный дефис

        # Чисто числовой код (как в "po 309775") → CustomerPO LIKE '%309775%'
        if raw.isdigit() and is_po:
            include_clauses.append(f"({field_po} LIKE '%{raw}%')")
            continue

        # --- Звёздочка в коде: DD-103433* → LIKE 'DD-103433%' ---
        if "*" in raw:
            pattern = raw.replace("*", "%")
            if is_po:
                include_clauses.append(f"({field_po} LIKE '{pattern}')")
            elif is_so:
                include_clauses.append(f"({field_so} LIKE '{pattern}')")
            else:
                include_clauses.append(
                    f"(({field_so} LIKE '{pattern}') OR ({field_po} LIKE '{pattern}'))"
                )
            continue

        # --- Короткий код (например DD-103433, AZ-11090) ---
        if "\\" not in raw and "/" not in raw and raw.count("-") == 1 and len(raw) < 30:
            if is_po:
                parts = [
                    f"({field_po} = '{raw}')",
                    f"({field_po} LIKE '{raw}\\%')",
                    f"({field_po} LIKE '{raw}-%')",
                ]
                include_clauses.append("(" + " OR ".join(parts) + ")")
            elif is_so:
                parts = [
                    f"({field_so} = '{raw}')",
                    f"({field_so} LIKE '{raw}\\%')",
                    f"({field_so} LIKE '{raw}-%')",
                ]
                include_clauses.append("(" + " OR ".join(parts) + ")")
            else:
                parts = [
                    f"({field_so} = '{raw}')",
                    f"({field_so} LIKE '{raw}\\%')",
                    f"({field_so} LIKE '{raw}-%')",
                    f"({field_po} = '{raw}')",
                    f"({field_po} LIKE '{raw}\\%')",
                    f"({field_po} LIKE '{raw}-%')",
                ]
                include_clauses.append("(" + " OR ".join(parts) + ")")
            continue

        # --- Полный код с \ или / → точное совпадение ---
        if "\\" in raw or "/" in raw:
            if is_po:
                include_clauses.append(f"({field_po} = '{raw}')")
            elif is_so:
                include_clauses.append(f"({field_so} = '{raw}')")
            else:
                include_clauses.append(f"(({field_so} = '{raw}') OR ({field_po} = '{raw}'))")
            continue

        # --- fallback — точное совпадение по коду ---
        if is_po:
            include_clauses.append(f"({field_po} = '{raw}')")
        elif is_so:
            include_clauses.append(f"({field_so} = '{raw}')")
        else:
            include_clauses.append(f"(({field_so} = '{raw}') OR ({field_po} = '{raw}'))")

    # Дополнительно: явные "so XXX" (особенно в комбинированных запросах po + so)
    for so_code in direct_so_codes:
        if so_code.lower() in neg_all_lower:
            continue
        raw = so_code.upper().strip()
        raw = raw.replace("–", "-")
        include_clauses.append(f"({field_so} = '{raw}')")

    # ----- СТРОИМ ОТРИЦАТЕЛЬНЫЕ УСЛОВИЯ (exclude_clauses) -----
    for c in neg_po_codes:
        add_exclude_for_code(c, "po")

    for c in neg_so_codes:
        add_exclude_for_code(c, "so")

    for c in neg_both_codes:
        add_exclude_for_code(c, "both")

    # ----- ФИНАЛЬНАЯ СБОРКА SQL -----
    if not include_clauses and not exclude_clauses:
        return ""

    parts = []
    if include_clauses:
        parts.append("(" + " OR ".join(include_clauses) + ")")
    if exclude_clauses:
        parts.append(" AND ".join(exclude_clauses))

    return " AND " + " AND ".join(parts)
