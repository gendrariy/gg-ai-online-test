from __future__ import annotations
import re


def _uc(s: str) -> str:
    return s.strip().upper()


def _field_norm(field: str) -> str:
    return "UCase(LTrim(RTrim(" + field + ")))"


def parse_item_size_filter(user_query: str, field: str = "[item_size]") -> str:
    """
    Фильтр по размеру кольца.

    Логика:
      - срабатывает только если в запросе есть слово SIZE / SIZES
      - берём ТОЛЬКО часть запроса ПОСЛЕ первого SIZE / SIZES
      - в этой части:
          * числовые размеры: 3, 3.5, 6, 7.25, 10.5 и т.п.
          * UK-буквы: F, G, H, ..., F.5, G.5 и т.п.
      - ЧИСЛА:
          * точное совпадение ('7')
          * как US-часть после дефиса ('N-7', 'Q.5-8.5')
          * как начало диапазона ('7-...') — на будущее
      - ВАЖНО:
          * если после числа сразу идёт KARAT / KT / K – считаем,
            что это карат, и НЕ используем его как размер.
      - БУКВЫ:
          * начало строки ('L%', 'M%', 'N.5%' и т.п.)
    """

    U = _uc(user_query)

    # Если в запросе вообще нет слова SIZE — размер не фильтруем
    if "SIZE" not in U and "SIZES" not in U:
        return ""

    # Берём только часть после первого SIZE / SIZES,
    # чтобы не цеплять числа типа "10 KARAT" как размер.
    m = re.search(r"\bSIZES?\b\s*(.*)", U)
    if m:
        size_part = m.group(1)
    else:
        # fallback, если вдруг regex не сработал
        size_part = U

    # Ищем токены только в size_part
    tokens = re.findall(r"[A-Z0-9\.]+", size_part)

    size_nums = []
    size_letters = []

    KARAT_WORDS = {"KARAT", "KARATS", "CARAT", "CARATS", "KT", "KRT", "K"}

    for i, t in enumerate(tokens):
        if t in ("SIZE", "SIZES"):
            continue

        next_tok = tokens[i + 1] if i + 1 < len(tokens) else ""

        # Числовой размер: 3, 3.5, 7.25, 10, 10.75 и т.п.
        if re.fullmatch(r"\d+(\.\d+)?", t):
            # Если после числа сразу идёт KARAT/KT/K — это карат, НЕ размер
            if next_tok in KARAT_WORDS:
                continue
            size_nums.append(t)
            continue

        # UK буквы: F, G, H, ... + половинки типа F.5, G.5
        if re.fullmatch(r"[A-Z](?:\.5)?", t):
            size_letters.append(t)
            continue

    if not size_nums and not size_letters:
        return ""

    f = _field_norm(field)
    conds = []

    # 🔹 Числовые размеры — БЕЗ '%n%', чтобы не ловить 11.75 при size 7
    for n in size_nums:
        # точный размер (только число)
        conds.append(f"{f} = '{n}'")
        # размер как US-часть после дефиса: N-7, N-7.25
        conds.append(f"{f} LIKE '%-{n}'")
        # если когда-нибудь появятся форматы '7-8', '7-7.5'
        conds.append(f"{f} LIKE '{n}-%'")

    # 🔹 UK размеры — по началу строки (L%, M%, N.5% и т.п.)
    for l in size_letters:
        conds.append(f"{f} LIKE '{l}%'")

    conds = sorted(set(conds))
    if not conds:
        return ""

    return " AND (" + " OR ".join(conds) + ")"
