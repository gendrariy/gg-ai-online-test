from __future__ import annotations
import re
from typing import List

COLOR_MAP = {
    "W": "W", "WHITE": "W", "WG": "W",
    "Y": "Y", "YEL": "Y", "YELLOW": "Y", "YG": "Y",
    "R": "R", "ROSE": "R", "RG": "R",
}

BASE_METALS = {
    "SILVER": "SLV", "SLV": "SLV",
    "PLATINUM": "PLAT", "PLAT": "PLAT",
    "BRASS": "BRASS",
    "PALLADIUM": "18WPL",
}

PALLADIUM_CODES = ["18WPL"]


def _uc(s: str) -> str:
    return s.strip().upper()


def _tokenize(q: str) -> List[str]:
    # разбиваем по пробелам и запятым
    return [t for t in re.split(r"[\s,]+", q) if t]


def _split_by_and(words: List[str]) -> List[List[str]]:
    groups: List[List[str]] = []
    cur: List[str] = []
    for w in words:
        if _uc(w) == "AND":
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def _field_norm(field: str) -> str:
    return "UCase(LTrim(RTrim(" + field + ")))"


def _gold_codes() -> List[str]:
    return [f"{k}{c}" for k in [9, 10, 14, 18] for c in ["W", "Y", "R"]]


def _parse_group_to_codes(group: List[str]) -> List[str]:
    g = [_uc(x) for x in group]

    NOISE = [
        "RECEIVED", "SEPTEMBER", "OCTOBER", "NOVEMBER", "AUGUST",
        "LAST", "WEEK", "MONTH", "THIS", "TODAY", "YESTERDAY",
        "BIG", "ORDER", "ENTRY", "FROM",
    ]
    g = [w for w in g if w not in NOISE]

    ITEM_WORDS = [
        "RING", "EARRING", "PENDANT", "NECKLACE", "BRACELET", "BANGLE",
        "CHAINS", "COLOR", "STONE", "DIAMONDS", "LOOSE", "BUTTERFLY", "SAMPLE",
    ]
    g = [w for w in g if w not in ITEM_WORDS]

    codes: List[str] = []
    text_group = " ".join(g)
    has_palladium_word = "PALLADIUM" in g
    has_wpl_token = any(t in ("WPL", "18WPL") for t in g)

    # palladium / 18WPL
    if has_palladium_word or has_wpl_token:
        codes.extend(PALLADIUM_CODES)
        return sorted(set(codes))

    # gold and silver
    if "GOLD" in g and "SILVER" in g:
        return sorted(set(_gold_codes() + ["SLV"] + codes))

    # platinum and brass (+ optional palladium)
    if "PLATINUM" in g and "BRASS" in g:
        base_codes = ["PLAT", "BRASS"]
        if has_palladium_word or has_wpl_token:
            base_codes.extend(PALLADIUM_CODES)
        return sorted(set(base_codes))

    # чистый platinum
    if "PLATINUM" in g:
        codes.append("PLAT")

    # базы: silver, brass, palladium
    for t in g:
        if t in BASE_METALS and t not in ["PLATINUM"]:
            codes.append(BASE_METALS[t])

    # явные коды типа 10YG / 9W / 14RG (позитивная часть)
    for t in g:
        m = re.fullmatch(r"(9|10|14|18)(WG|YG|RG|W|Y|R)G?", t)
        if m:
            num, col = m.groups()
            color = col[0]  # WG -> W, YG -> Y
            codes.append(num + color)

    nums = [t for t in g if t.isdigit() and t in ["9", "10", "14", "18"]]

    colors: List[str] = []
    for t in g:
        if t in COLOR_MAP:
            colors.append(COLOR_MAP[t])
        elif re.fullmatch(r"[WYRG]G?", t):
            colors.append(COLOR_MAP.get(t[0], t[0]))

    # white gold / yellow gold / rose gold
    if "GOLD" in g and colors and not nums:
        for n in ["9", "10", "14", "18"]:
            for c in colors:
                codes.append(f"{n}{c}")
        return sorted(set(codes))

    # 10 karat white / 14 kt yellow / ...
    karat_match = re.search(
        r"\b(9|10|14|18)\s*(KARAT|KARATS|CARAT|CARATS|KT|KRT|K)\b",
        text_group,
    )
    if karat_match:
        n = karat_match.group(1)
        if colors:
            # 10 karat white → 10W
            for c in colors:
                codes.append(n + c)
        elif has_palladium_word or has_wpl_token:
            # 18 karat palladium → уже добавили palladium выше
            pass
        else:
            # чистый "9 karat" → специальный код '9' (для последующей интерпретации)
            codes.append(n)

    # просто "gold"
    if "GOLD" in g and not nums and not colors:
        codes.extend(_gold_codes())

    # 10 gold (без цвета) → 10W/10Y/10R
    if "GOLD" in g and nums and not colors:
        for n in nums:
            for c in ["W", "Y", "R"]:
                codes.append(f"{n}{c}")

    # 10 white / 14 yellow
    if nums and colors:
        for n in nums:
            for c in colors:
                codes.append(f"{n}{c}")

    return sorted(set(codes))


def _build_like_clause(field: str, codes: List[str]) -> str:
    if not codes:
        return ""
    f = _field_norm(field)
    return "(" + " OR ".join(f"{f} LIKE '{c}%'" for c in codes) + ")"


# ---- отрицания 9/10/14/18 + W/Y/R ----
def _extract_negated_karat_color_codes(gU: List[str], full_upper: str) -> List[str]:
    """
    NOT 10Yg / NOT 10YG / NOT 10 YELLOW / NO 9WG / WITHOUT 14 YG /
    DOES NOT INCLUDE 18RG / NOT INCLUDE 18RG / WITH OUT 18RG
    → ['10Y', '9W', ...]
    """
    NEG_WORDS = ("NOT", "NO", "WITHOUT")
    PHRASES = ("DOES NOT INCLUDE", "NOT INCLUDE", "WITH OUT")
    NUMS = ("9", "10", "14", "18")
    COLOR_WORDS = ("WHITE", "YELLOW", "ROSE")
    COLOR_CODES = ("WG", "YG", "RG")

    phrase_neg = any(p in full_upper for p in PHRASES)
    has_neg_word = any(t in NEG_WORDS for t in gU)

    # если нет локального NOT/NO/WITHOUT и нет фраз — нет отрицания
    if not has_neg_word and not phrase_neg:
        return []

    codes: set[str] = set()

    # 1) слитные токены: 10YG, 10Y, 10WG и т.п.
    for idx, t in enumerate(gU):
        m = re.fullmatch(r"(9|10|14|18)(WG|YG|RG|W|Y|R)G?", t)
        if not m:
            continue

        # считаем отрицанием только если:
        #   - есть фраза типа "DOES NOT INCLUDE" ИЛИ
        #   - прямо перед токеном стоит NOT/NO/WITHOUT
        if not phrase_neg and not (idx > 0 and gU[idx - 1] in NEG_WORDS):
            continue

        num, col = m.groups()
        color = col[0]  # WG -> W, YG -> Y и т.д.
        codes.add(num + color)

    # 2) раздельно: 10 + YELLOW / 10 + YG
    for i, t in enumerate(gU):
        if t not in NUMS:
            continue

        # тот же принцип: отрицание должно быть либо фразой, либо прямо перед числом
        if not phrase_neg and not (i > 0 and gU[i - 1] in NEG_WORDS):
            continue

        for j in range(i + 1, min(len(gU), i + 3)):
            col_tok = gU[j]
            color = None
            if col_tok in COLOR_CODES:
                color = col_tok[0]
            elif col_tok in COLOR_WORDS:
                color = COLOR_MAP[col_tok]
            if color:
                codes.add(t + color)
                break

    return sorted(codes)


# ---- not 9 karat / not 10 kt / ... → только карат ----
def _extract_negated_karat_only(gU: List[str], full_upper: str) -> List[str]:
    """
    NOT 9 KARAT / NOT 10 KT / NO 14K / WITHOUT 18 CARAT /
    DOES NOT INCLUDE 9 KARAT / NOT INCLUDE 9 KARAT / WITH OUT 9 KARAT
    → ['9'], ['10'], ...
    """
    NEG_WORDS = ("NOT", "NO", "WITHOUT")
    PHRASES = ("DOES NOT INCLUDE", "NOT INCLUDE", "WITH OUT")
    NUMS = ("9", "10", "14", "18")
    KARAT_TOKENS = ("KARAT", "KARATS", "CARAT", "CARATS", "KT", "KRT", "K")

    phrase_neg = any(p in full_upper for p in PHRASES)
    has_neg_word = any(t in NEG_WORDS for t in gU)

    if not has_neg_word and not phrase_neg:
        return []

    nums: set[str] = set()

    for i, t in enumerate(gU):
        if t not in NUMS:
            continue

        # отрицание должно быть либо фразой, либо прямо перед числом
        if not phrase_neg and not (i > 0 and gU[i - 1] in NEG_WORDS):
            continue

        for j in range(i + 1, min(len(gU), i + 3)):
            if gU[j] in KARAT_TOKENS:
                nums.add(t)
                break

    return sorted(nums)


def parse_metal_filter(user_query, field="[metal]") -> str:
    U = _uc(user_query)
    words = _tokenize(U)
    groups = _split_by_and(words)

    positive_groups: List[str] = []
    negative_groups: List[str] = []

    # NOT GOLD / NOT SILVER / ...
    negated: List[str] = []
    for m in ["GOLD", "SILVER", "PLATINUM", "BRASS", "PALLADIUM"]:
        if f"NOT {m}" in U:
            negated.append(m)

    neg_specific_per_group: List[List[str]] = []
    neg_karat_only_per_group: List[List[str]] = []
    for g in groups:
        gU = [_uc(x) for x in g]
        neg_specific_per_group.append(_extract_negated_karat_color_codes(gU, U))
        neg_karat_only_per_group.append(_extract_negated_karat_only(gU, U))

    all_nums: List[str] = []
    all_colors: List[str] = []

    for g in groups:
        gU = [_uc(x) for x in g]
        nums = [t for t in gU if t.isdigit() and t in ["9", "10", "14", "18"]]
        colors = [COLOR_MAP[t] for t in gU if t in COLOR_MAP]

        all_nums.extend(nums)
        all_colors.extend(colors)

    inherited_karat = all_nums[0] if len(all_nums) == 1 else None

    # позитивные группы
    for idx, g in enumerate(groups):
        gU = [_uc(x) for x in g]
        has_nums = any(t.isdigit() and t in ["9", "10", "14", "18"] for t in gU)
        has_colors = any(t in COLOR_MAP for t in gU)

        # если явно "NOT GOLD" и т.п. — не добавляем позитив
        skip_group = False
        for m in negated:
            if m in gU:
                skip_group = True
                break
        if skip_group:
            continue

        codes = _parse_group_to_codes(g)

        group_neg_specific = neg_specific_per_group[idx]
        group_neg_karat_only = neg_karat_only_per_group[idx]

        # GOLD + not 10 yellow → позитив: всё золото
        if "GOLD" in gU and group_neg_specific:
            codes = list(set(codes) | set(_gold_codes()))

        # GOLD + not 9 karat → позитив: всё золото
        if "GOLD" in gU and group_neg_karat_only:
            codes = list(set(codes) | set(_gold_codes()))

        # если группа говорит только "not 9 wg / not 10 yg / not 9 karat"
        # и НЕ содержит GOLD/SILVER/... → оставляем только NOT
        if (group_neg_specific or group_neg_karat_only) and not any(
            m in gU for m in ["GOLD", "SILVER", "PLATINUM", "BRASS", "PALLADIUM"]
        ):
            codes = [
                c for c in codes
                if c not in group_neg_specific and c not in group_neg_karat_only
            ]

        # наследование карата: "10 white and yellow" -> 10W и 10Y
        if inherited_karat and has_colors and not has_nums:
            inherited_codes = [
                inherited_karat + COLOR_MAP[t]
                for t in gU if t in COLOR_MAP
            ]
            codes.extend(inherited_codes)

        if codes:
            positive_groups.append(_build_like_clause(field, sorted(set(codes))))

    # стандартные NOT GOLD / NOT SILVER / ...
    def _not_clause(m: str) -> str:
        f = _field_norm(field)
        if m == "GOLD":
            return "NOT (" + " OR ".join(
                f"{f} LIKE '{k}%'" for k in _gold_codes()
            ) + ")"
        if m == "SILVER":
            return f"NOT ({f} LIKE 'SLV%')"
        if m == "PLATINUM":
            return f"NOT ({f} LIKE 'PLAT%')"
        if m == "BRASS":
            return f"NOT ({f} LIKE 'BRASS%')"
        if m == "PALLADIUM":
            return "NOT (" + " OR ".join(
                f"{f} LIKE '{k}%'" for k in PALLADIUM_CODES
            ) + ")"
        return ""

    for m in negated:
        negative_groups.append(_not_clause(m))

    # конкретные NOT 10YG / NOT 9WG / NOT 9 karat
    all_neg_specific = sorted({code for codes in neg_specific_per_group for code in codes})
    all_neg_karat_only = sorted({num for nums in neg_karat_only_per_group for num in nums})

    if all_neg_specific or all_neg_karat_only:
        f = _field_norm(field)

        for code in all_neg_specific:
            negative_groups.append(f"NOT ({f} LIKE '{code}%')")

        # NOT 9 karat → NOT 9W%, NOT 9Y%, NOT 9R%
        for num in all_neg_karat_only:
            for col in ["W", "Y", "R"]:
                negative_groups.append(f"NOT ({f} LIKE '{num}{col}%')")

    sql_parts: List[str] = []

    if positive_groups:
        sql_parts.append("(" + " OR ".join(positive_groups) + ")")

    if negative_groups:
        sql_parts.extend(negative_groups)

    if not sql_parts:
        return ""

    return " AND " + " AND ".join(sql_parts)
