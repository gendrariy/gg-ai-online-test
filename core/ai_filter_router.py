import os
print(">>> AI ROUTER LOADED FROM:", os.path.abspath(__file__))

import re

from filters.date_filter import parse_date_range
from filters.metal_filter import parse_metal_filter
from filters.order_type_filter import parse_order_type_filter
from filters.item_type_filter import parse_item_type_filter
from filters.customer_filter import parse_customer_filter
from filters.customer_shortname_filter import parse_customer_shortname_filter
from filters.salesorder_filter import parse_salesorder_filter
from filters.jobnumber_filter import parse_jobnumber_filter
from filters.item_size_filter import parse_item_size_filter  # фильтр по размеру
from filters.pstatus_filter import parse_pstatus_filter      # фильтр по pstatus (CANCEL/HOLD)
from filters.department_filter import parse_department_filter      # фильтр по DepartmentName
from filters.last_operation_filter import parse_last_operation_filter  # фильтр по LastOperation
from filters.casting_lot_filter import parse_casting_lot_filter  # фильтр по casting_lot
from filters.order_group_filter import parse_order_group_filter
from filters.style_filter import parse_style_filter
from filters.bagnumber_filter import parse_bagnumber_filter




def _strip_and(part: str) -> str:
    """Убираем ведущий 'AND ' у фрагментов parse_*_filter."""
    if not part:
        return ""
    p = part.strip()
    if p.upper().startswith("AND "):
        return p[4:].strip()
    return p


def _build_metal_item_pair_clause(text: str) -> str:
    """Обрабатывает пары:
         'silver ring and gold pendant'
         '10 karat ring and 14 karat pendant'
         'earring yellow and ring white' и т.п.

    Логика:
      1) режем текст по ' and '
      2) для каждого сегмента:
         - metal_part = parse_metal_filter(segment)
           * если металла нет, но есть цвет (white/yellow/rose/red) и item_type,
             пробуем трактовать как GOLD (добавляем слово 'gold')
         - item_part  = parse_item_type_filter(segment)
         - обрезаем ведущий 'AND ' у обоих
         - если есть и металл, и тип изделия → группа (metal AND item)
      3) если найдено минимум 2 группы → AND (group1 OR group2 ...)

    Если уверенных пар < 2 — возвращаем пустую строку.
    Ничего не ломаем, только ДОПОЛНИТЕЛЬНО сужаем результат.
    """
    if not text:
        return ""

    segments = [s.strip() for s in text.split(" and ") if s.strip()]
    if len(segments) < 2:
        return ""

    groups = []
    color_tokens = {"white", "yellow", "rose", "red"}

    for seg in segments:
        seg_lower = seg.lower()

        # Базовый разбор
        metal_part = parse_metal_filter(seg)
        item_part = parse_item_type_filter(seg)

        # Если металл не распознан, но в сегменте есть цвет и тип изделия,
        # пробуем трактовать это как GOLD (например 'earring yellow' -> 'yellow gold')
        if not metal_part:
            has_color = any(tok in seg_lower.split() for tok in color_tokens)
            if has_color:
                # добавляем 'gold' в конец сегмента только для metal-фильтра
                metal_part = parse_metal_filter(seg + " gold")

        metal_cond = _strip_and(metal_part)
        item_cond = _strip_and(item_part)

        if metal_cond and item_cond:
            groups.append(f"({metal_cond} AND {item_cond})")

    if len(groups) < 2:
        return ""

    return " AND (" + " OR ".join(groups) + ")"


def ai_parse_query(user_query: str) -> str:
    """Центральный маршрутизатор фильтров."""

    q = user_query.strip().lower()
    sql = "SELECT * FROM [T_Local_Snapshot] WHERE 1=1"

    # --- Проверка на кривой запрос "shipping last" без периода ---
    if ("ship" in q or "shipping" in q or "shipped" in q) and "last" in q:
        if not re.search(r"(week|month|months|day|days|year|years|\d+\s+days|\d+\s+months)", q):
            return (
                "Invalid request: “shipping last” requires a time period. "
                "Examples: shipping last week, shipping last 2 months, shipping last 45 days."
            )

    # --- Определяем поле даты (ПРИОРИТЕТ: due/request -> casting -> shipping -> pdate) ---
    if "request" in q or "due date" in q:
        date_field = "[request_date]"
    elif "casting" in q:
        date_field = "[Casting_Date]"
    elif "ship" in q or "shipping" in q or "shipped" in q:
        date_field = "[ship_date]"
    elif "due" in q or "production" in q:
        date_field = "[pdate]"
    else:
        date_field = "[pdate]"

    # --- Разбор дат ---
    original_q = q  # исходный текст (lowercase)
    start, end, cleaned_text = parse_date_range(q)

    # Очищенный текст без дат идёт дальше в фильтры
    q = cleaned_text

    # Флаг: есть ли вообще диапазон дат по выбранному полю
    has_date_range = bool(start or end)

    # Есть ли в запросе явное упоминание pstatus (open/closed/cancel/release/reported)?
    pstatus_mentioned = bool(
        re.search(
            r"\b(open|closed?|close|cancel(?:ed|led)?|cancel|release[ds]?|reported?)\b",
            original_q,
        )
    )

    # --- Флаг "ready to ship" (готово к отправке, но ещё не отправлено) ---
    # Примеры: "ready to ship", "ready for shipping", "ready items for shipping"
    ready_to_ship = bool(
        re.search(
            r"ready\s+(items?\s+)?(to|for)\s+ship(?:ping)?",
            original_q,
        )
    )

    # --- ДАТА-ФИЛЬТР ---
    if start or end:
        if start and end:
            sql += (
                f" AND ({date_field} >= #{start.strftime('%m/%d/%Y')}# "
                f"AND {date_field} <= #{end.strftime('%m/%d/%Y')}#)"
            )
        elif start:
            sql += f" AND ({date_field} >= #{start.strftime('%m/%d/%Y')}#)"
        elif end:
            sql += f" AND ({date_field} <= #{end.strftime('%m/%d/%Y')}#)"

    # --- Order type filter ---
    sql += parse_order_type_filter(q)

    # --- Metal filter (по ИСХОДНОМУ запросу, чтобы видеть 'not gold' и т.п.) ---
    metal_part_1 = parse_metal_filter(original_q)

    # Fallback: если металл не распознан, но есть только цвет (white/yellow/rose/red),
    # трактуем его как GOLD-цвет (yellow gold, white gold, rose gold).
    if not metal_part_1:
        color_tokens = ("white", "yellow", "rose", "red")
        base_tokens = ("gold", "silver", "slv", "platinum", "plat", "brass", "palladium")
        has_color = any(re.search(rf"\b{ct}\b", original_q) for ct in color_tokens)
        has_base = any(bt in original_q for bt in base_tokens)
        if has_color and not has_base:
            metal_part_1 = parse_metal_filter(original_q + " gold")

    if metal_part_1:
        sql += metal_part_1

    # --- Item type filter ---
    sql += parse_item_type_filter(q)

    # --- Item size filter ---
    sql += parse_item_size_filter(q)

    # --- Специальная логика пар "metal + item" через AND ---
    pair_clause = _build_metal_item_pair_clause(q)
    if pair_clause:
        sql += pair_clause

    # --- SalesOrder / PO ---
    salesorder_sql = parse_salesorder_filter(original_q)
    if salesorder_sql:
        sql += salesorder_sql

    # --- JobNumber ---
    sql += parse_jobnumber_filter(original_q)


    # --- BagNumber ---
    sql += parse_bagnumber_filter(original_q)

    # --- Style ---
    sql += parse_style_filter(original_q)

    # --- Order Group (region/office: USA / Canada / Thailand / UK / Ausrtalia) ---
    sql += parse_order_group_filter(original_q)

    # --- Customer ---
    sql += parse_customer_filter(q)

    # --- Customer (короткие имена без слова "customer": SUNCOR, D4D, AZURE, ...) ---
    sql += parse_customer_shortname_filter(q)

    # --- Casting lot ---
    sql += parse_casting_lot_filter(original_q)

    # --- PSTATUS (пока только CANCEL / HOLD и т.п. из pstatus_filter) ---
    sql += parse_pstatus_filter(original_q)

    # --- DepartmentName ---
    sql += parse_department_filter(original_q)

    # --- LastOperation ---
    sql += parse_last_operation_filter(original_q)

    # ===================== CASTING-СТАТУС =====================

    # 1) Спец-правило: "casting + SalesOrder/PO"
    if "casting" in original_q and salesorder_sql:
        has_so = "[SalesOrder]" in salesorder_sql
        has_po = "[CustomerPO]" in salesorder_sql
        if has_so or has_po:
            casting_on_date = (date_field == "[Casting_Date]" and has_date_range)
            if not casting_on_date:
                neg_casting = bool(
                    re.search(r"(not\s+casting|no\s+casting|not\s+ready\s+casting)", original_q)
                )
                if neg_casting:
                    sql += " AND ([Casting] = 0)"
                    # по умолчанию исключаем CANCEL и CLOSED,
                    # если пользователь сам явно не указал статус
                    if not pstatus_mentioned:
                        sql += " AND (UCase(LTrim(RTrim([pstatus]))) NOT IN ('CANCEL','CLOSED'))"
                else:
                    sql += " AND ([Casting] <> 0)"

    # 2) Общее правило "casting" БЕЗ SO/PO
    if "casting" in original_q and not salesorder_sql:
        casting_on_date = (date_field == "[Casting_Date]" and has_date_range)
        if not casting_on_date:
            neg_casting = bool(
                re.search(r"(not\s+casting|no\s+casting|not\s+ready\s+casting)", original_q)
            )
            if neg_casting:
                sql += " AND ([Casting] = 0)"
                if not pstatus_mentioned:
                    sql += " AND (UCase(LTrim(RTrim([pstatus]))) NOT IN ('CANCEL','CLOSED'))"
            else:
                sql += " AND ([Casting] <> 0)"

    # ===================== SPECIAL OR RULE =====================
    # "in production / in process / in progress" + "not casting" ->
    # объединяем как OR:
    #   (pstatus='REPORTED') OR (Casting=0)
    if (
        re.search(r"\bin\s+(production|process|progress)\b", original_q)
        and re.search(r"\b(not\s+casting|no\s+casting|without\s+casting|not\s+ready\s+casting)\b", original_q)
        and not re.search(r"\b(cancel|closed?|hold|open|release[d]?)\b", original_q)
    ):
        p_field = "UCase(LTrim(RTrim([pstatus])))"

        p_pat = re.compile(
            r"\s+AND\s+\(\s*UCase\(LTrim\(RTrim\(\[pstatus\]\)\)\)\s*=\s*'REPORTED'\s*\)",
            re.IGNORECASE,
        )
        c_pat = re.compile(r"\s+AND\s+\(\s*\[Casting\]\s*=\s*0\s*\)", re.IGNORECASE)
        # --- спец-правило: in process/production/progress + not casting = OR-объединение ---
        if (
            re.search(r"\bin\s+(production|process|progress)\b", original_q, re.IGNORECASE)
            and re.search(r"\b(not\s+casting|no\s+casting|without\s+casting)\b", original_q, re.IGNORECASE)
        ):
            # если есть и pstatus=REPORTED, и Casting=0 → заменить пересечение на OR
            if p_pat.search(sql) and c_pat.search(sql):
                sql = p_pat.sub("", sql, count=1)
                sql = c_pat.sub("", sql, count=1)
                sql += (
                    " AND ((UCase(LTrim(RTrim([pstatus])))='REPORTED') OR ([Casting]=0))"
                )


        if p_pat.search(sql) and c_pat.search(sql):
            # убираем пересечение REPORTED AND Casting=0
            sql = p_pat.sub("", sql, count=1)
            sql = c_pat.sub("", sql, count=1)

            # добавляем объединение (OR)
            sql += f" AND (({p_field} = 'REPORTED') OR (Nz([Casting],0)=0))"


    # ===================== SHIPPING-СТАТУС =====================

    # Особый случай: "ready to ship" / "ready for shipping" / "ready items for shipping"
    # Логика:
    #   pstatus = 'CLOSED'
    #   LastOperation = 'Packing'
    #   ship_date IS NULL
    if ready_to_ship:
        sql += " AND (UCase(LTrim(RTrim([pstatus]))) = 'CLOSED')"
        sql += " AND (UCase(LTrim(RTrim([LastOperation]))) = 'PACKING')"
        sql += " AND ([ship_date] IS NULL)"
    else:
        # 1) "shipping + SalesOrder/PO"
        if ("ship" in original_q or "shipping" in original_q or "shipped" in original_q) and salesorder_sql:
            has_so = "[SalesOrder]" in salesorder_sql
            has_po = "[CustomerPO]" in salesorder_sql
            if has_so or has_po:
                neg_ship = bool(
                    re.search(
                        r"(not\s+ship(?:ped|ping)?|no\s+shipping|not\s+shipped|not\s+ready\s+ship(?:ping)?)",
                        original_q,
                    )
                )
                if neg_ship:
                    sql += " AND ([ship_date] IS NULL)"
                else:
                    sql += " AND ([ship_date] IS NOT NULL)"

        # 2) Общее правило "shipping/ship/shipped" БЕЗ SO/PO
        if ("ship" in original_q or "shipping" in original_q or "shipped" in original_q) and not salesorder_sql:
            shipping_on_date = (date_field == "[ship_date]" and has_date_range)
            if not shipping_on_date:
                neg_ship = bool(
                    re.search(
                        r"(not\s+ship(?:ped|ping)?|no\s+shipping|not\s+shipped|not\s+ready\s+ship(?:ping)?)",
                        original_q,
                    )
                )
                if neg_ship:
                    sql += " AND ([ship_date] IS NULL)"
                else:
                    sql += " AND ([ship_date] IS NOT NULL)"

    return sql


def ai_router(user_query: str) -> str:
    return ai_parse_query(user_query)
