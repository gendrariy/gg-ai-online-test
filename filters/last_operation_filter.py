import re
from typing import Tuple, Set, Dict, List

NEGATION_WORDS = ("not", "no", "without", "except")

# Полный список всех LastOperation из Department-operation.xlsx
RAW_OPERATIONS: List[str] = [
    # Jewellers
    "Jeweller Center",
    "Jeweller In",
    "Jeweller On Hold",
    "Jeweller Out",
    "RP Jeweller In",
    "RP Jeweller Out",
    "Assembly In",
    "Assembly Out",
    "Cleaning In",
    "Cleaning Out",
    "Laser In",
    "Laser Out",
    "Waiting New Model",

    # Polishing
    "Grinding In",
    "Buffing In",
    "Buffing Out",
    "Final Polish In",
    "Final Polish Out",
    "Grinding Out",
    "Lapping Final In",
    "Lapping Mount In",
    "Lapping Out",
    "Polish Center",
    "Pre-Polish In",
    "Pre-Polish Out",
    "RP Final Polish In 1",
    "RP Final Polish In 2",
    "RP Final Polish Out 1",
    "RP Final Polish Out 2",
    "RP Pre-Polish In",
    "RP Pre-Polish Out",
    "Waiting to Polishig",
    "TumBling",

    # Quality Controls
    "Q.C. Center",
    "Q.C. Final In",
    "Q.C. Final Out",
    "Q.C. In",
    "Q.C. Mount In",
    "Q.C. Mount Out",
    "Q.C. Out",
    "Q.C. Setting In",
    "Q.C. Setting Out",
    "Q.C. waiting Finding",
    "QC On Hold",
    "Laser Marking",
    "Laser Marking Out",
    "Plating",
    "Plating Out",
    "Waiting Plating",
    "Rodium",
    "Waiting Q.C.",

    # Office Controls
    "Model Center",
    "Model Completed",
    "Model Out",
    "Model Worker",
    "Sample Completed",
    "Samples",
    "Send to sub BKK",
    "Waiting to Confirm",
    "WIP waiting Finding",
    "Waiting Assembly Tag",
    "Waiting Posts",
    "Show Room",

    # Orders & Packing
    "Packing",
    "Waiting to Packs",
    "Waiting Tags",
    "Waiting Pad",

    # Gold Control
    "Assignment",
    "Waiting to Cancel",
    "Waiting to Casting",
    "Waiting to Production",
    "Sorting In",
    "Sorting Out",
    "Spure Remove Dust",
    "Spure Remove In",
    "Spure Remove Out",

    # Setting
    "Setting Center",
    "Setting In",
    "Setting On Hold",
    "Setting Out",
    "Setting Out Sub",
    "RP Setting In",
    "RP Setting Out",
    "RP WaxSet In",
    "RP WaxSet Out",
    "Wait Setting Center",
    "Wax Seting In",
    "Wax Seting Out",
    "WaxSet Center",
    "Waiting to Setting Q.C.",

    # Subcontract
    "SUB Repair",
    "SUB Stock",

    # Wax
    "Wax In",
    "Wax Out",
    "Waiting for Re-Cast",
]

# Базовый маппинг: "точная фраза в запросе" → соответствующая операция
# (ключи в lower-case, значения – список LastOperation в базе)
OP_KEYWORDS: Dict[str, List[str]] = {
    op.lower(): [op] for op in RAW_OPERATIONS
}

# Дополнительные ключи / группы / синонимы
EXTRA_KEYWORDS: Dict[str, List[str]] = {
    # --- Polishing группы ---

    # Buffing: общий запрос без In/Out
    "buffing": ["Buffing In", "Buffing Out"],

    # Обычный Final Polish (НЕ RP)
    "final polish": ["Final Polish In", "Final Polish Out"],
    "final polish in": ["Final Polish In"],
    "final polish out": ["Final Polish Out"],
    #Test

    "polish in": [
        "Final Polish In",
        "Pre-Polish In",
        "RP Final Polish In 1",
        "RP Final Polish In 2",
        "RP Pre-Polish In",
    ],
    "polish out": [
        "Final Polish Out",
        "Pre-Polish Out",
        "RP Final Polish Out 1",
        "RP Final Polish Out 2",
        "RP Pre-Polish Out",
    ],


    # RP Final Polish – отдельно от обычного
    "rp final polish in 1": ["RP Final Polish In 1"],
    "rp final polish in 2": ["RP Final Polish In 2"],
    "rp final polish out 1": ["RP Final Polish Out 1"],
    "rp final polish out 2": ["RP Final Polish Out 2"],
    # общий запрос по RP final polish (если без номера)
    "rp final polish in": ["RP Final Polish In 1", "RP Final Polish In 2"],
    "rp final polish out": ["RP Final Polish Out 1", "RP Final Polish Out 2"],
    "rp final polish": [
        "RP Final Polish In 1",
        "RP Final Polish In 2",
        "RP Final Polish Out 1",
        "RP Final Polish Out 2",
    ],

    # Pre-polish (обычный + RP)
    "pre-polish": ["Pre-Polish In", "Pre-Polish Out"],
    "pre polish": ["Pre-Polish In", "Pre-Polish Out"],
    "pre-polish in": ["Pre-Polish In"],
    "pre polish in": ["Pre-Polish In"],
    "pre-polish out": ["Pre-Polish Out"],
    "pre polish out": ["Pre-Polish Out"],

    "rp pre-polish": ["RP Pre-Polish In", "RP Pre-Polish Out"],
    "rp pre polish": ["RP Pre-Polish In", "RP Pre-Polish Out"],
    "rp pre-polish in": ["RP Pre-Polish In"],
    "rp pre-polish out": ["RP Pre-Polish Out"],

    # Lapping – строго как ты просил:
    #  - "lapping in"  → только Lapping Final In
    #  - "lapping out" → только Lapping Out
    "lapping final in": ["Lapping Final In"],
    "lapping in": ["Lapping Final In"],
    "lapping out": ["Lapping Out"],
    "lapping": ["Lapping Final In", "Lapping Mount In", "Lapping Out"],

    # Grinding (по аналогии: общий запрос + отдельные)
    "grinding": ["Grinding In", "Grinding Out"],
    "grinding in": ["Grinding In"],
    "grinding out": ["Grinding Out"],

    # Polish Center
    "polish center": ["Polish Center"],
    "polish centre": ["Polish Center"],

    # Tumbling
    "tumbling": ["TumBling"],
    "tumble": ["TumBling"],

    # --- QC группы и синонимы ---

    "qc center": ["Q.C. Center"],
    "q.c. centre": ["Q.C. Center"],
    "qc centre": ["Q.C. Center"],

    # QC Final
    "qc final in": ["Q.C. Final In"],
    "q.c. final in": ["Q.C. Final In"],
    "qc final out": ["Q.C. Final Out"],
    "q.c. final out": ["Q.C. Final Out"],
    "qc final": ["Q.C. Final In", "Q.C. Final Out"],
    "q.c. final": ["Q.C. Final In", "Q.C. Final Out"],

    # QC Mount
    "qc mount in": ["Q.C. Mount In"],
    "q.c. mount in": ["Q.C. Mount In"],
    "qc mount out": ["Q.C. Mount Out"],
    "q.c. mount out": ["Q.C. Mount Out"],
    "qc mount": ["Q.C. Mount In", "Q.C. Mount Out"],
    "q.c. mount": ["Q.C. Mount In", "Q.C. Mount Out"],

    # QC Setting
    "qc setting in": ["Q.C. Setting In"],
    "q.c. setting in": ["Q.C. Setting In"],
    "qc setting out": ["Q.C. Setting Out"],
    "q.c. setting out": ["Q.C. Setting Out"],
    "qc setting": ["Q.C. Setting Out"],
    "q.c. setting": ["Q.C. Setting Out"],

    # QC waiting / on hold
    "qc waiting": ["Q.C. waiting Finding"],
    "q.c. waiting": ["Q.C. waiting Finding"],
    "waiting qc": ["Waiting Q.C."],

    "qc on hold": ["QC On Hold"],

    # 🔹 QC IN / QC OUT (новые синонимы)
    "qc in": ["Q.C. In"],
    "q.c. in": ["Q.C. In"],
    "qc out": ["Q.C. Out"],
    "q.c. out": ["Q.C. Out"],

    # Laser (QC + Jewellers)
    "laser marking": ["Laser Marking"],
    "laser marking out": ["Laser Marking Out"],
    "laser in": ["Laser In"],
    "laser out": ["Laser Out"],
    "laser": ["Laser In", "Laser Out"],

    # Plating
    "plating": ["Plating"],
    "plating out": ["Plating Out"],
    "waiting plating": ["Waiting Plating"],

    # Rhodium
    "rhodium": ["Rodium"],
    "rodium": ["Rodium"],

    # --- Setting / Wax / Gold Control / прочее ---

    # Setting базовые
    "setting in": ["Setting In"],
    "setting out": ["Setting Out"],
    "setting center": ["Setting Center"],
    "setting centre": ["Setting Center"],
    "setting on hold": ["Setting On Hold"],
    "setting out sub": ["Setting Out Sub"],

    # RP Setting / WaxSet
    "rp setting in": ["RP Setting In"],
    "rp setting out": ["RP Setting Out"],
    "rp waxset in": ["RP WaxSet In"],
    "rp waxset out": ["RP WaxSet Out"],

    # Wax
    "wax in": ["Wax In"],
    "wax out": ["Wax Out"],
    "wax seting in": ["Wax Seting In"],
    "wax seting out": ["Wax Seting Out"],
    "waxset center": ["WaxSet Center"],
    "waiting for re-cast": ["Waiting for Re-Cast"],
    "waiting for recast": ["Waiting for Re-Cast"],

    # Gold Control waitings
    "waiting to cancel": ["Waiting to Cancel"],
    "waiting cancel": ["Waiting to Cancel"],
    "waiting to casting": ["Waiting to Casting"],
    "waiting casting": ["Waiting to Casting"],
    "waiting to production": ["Waiting to Production"],
    "waiting production": ["Waiting to Production"],

    "sorting in": ["Sorting In"],
    "sorting out": ["Sorting Out"],
    "spure remove dust": ["Spure Remove Dust"],
    "spure remove in": ["Spure Remove In"],
    "spure remove out": ["Spure Remove Out"],

    # Office / WIP
    "model center": ["Model Center"],
    "model out": ["Model Out"],
    "model completed": ["Model Completed"],
    "model worker": ["Model Worker"],

    "sample completed": ["Sample Completed"],
    "samples": ["Samples"],

    "send to sub bkk": ["Send to sub BKK"],
    "send to sub": ["Send to sub BKK"],

    "wip waiting finding": ["WIP waiting Finding"],
    "waiting assembly tag": ["Waiting Assembly Tag"],
    "waiting posts": ["Waiting Posts"],
    "waiting tags": ["Waiting Tags"],
    "waiting pad": ["Waiting Pad"],

    "show room": ["Show Room"],

    # Orders & Packing
    "packing": ["Packing"],
    "waiting to packs": ["Waiting to Packs"],

    # Subcontract
    "sub repair": ["SUB Repair"],
    "sub stock": ["SUB Stock"],

    # Jewellers
    "jeweller center": ["Jeweller Center"],
    "jeweller in": ["Jeweller In"],
    "jeweller on hold": ["Jeweller On Hold"],
    "jeweller out": ["Jeweller Out"],
    "rp jeweller in": ["RP Jeweller In"],
    "rp jeweller out": ["RP Jeweller Out"],
    # короткие формы и синонимы
    "jewellery in": ["Jeweller In", "RP Jeweller In"],
    "jewelry in": ["Jeweller In", "RP Jeweller In"],
    "jewelery in": ["Jeweller In", "RP Jeweller In"],

    "jewellery out": ["Jeweller Out", "RP Jeweller Out"],
    "jewelry out": ["Jeweller Out", "RP Jeweller Out"],
    "jewelery out": ["Jeweller Out", "RP Jeweller Out"], 

    "jewellery out": ["Jeweller Out"],   # UK
    "jewelry out": ["Jeweller Out"],     # US
    "jewelery out": ["Jeweller Out"],    # твоя опечатка
    "waiting new model": ["Waiting New Model"],
    
    # Assignment
    "assignment": ["Assignment"],
}

# Обновляем основной словарь дополнительными ключами
for k, v in EXTRA_KEYWORDS.items():
    OP_KEYWORDS[k.lower()] = v


def _extract_op_sets(query: str) -> Tuple[Set[str], Set[str]]:
    """
    Разбираем текст запроса и строим 2 множества:
      include_ops, exclude_ops
    элементы уже в UPPER и соответствуют точным значениям LastOperation.
    """
    q = query.lower()
    include_ops: Set[str] = set()
    exclude_ops: Set[str] = set()

    # Сканируем ключи по убыванию длины:
    # "rp final polish in 1" поймается раньше, чем "final polish in".
    for kw in sorted(OP_KEYWORDS.keys(), key=len, reverse=True):
        kw_lower = kw.lower()

        # шаблон для отрицаний: not/no/without/except + фраза
        neg_pattern = rf"(?:{'|'.join(NEGATION_WORDS)})\s+{re.escape(kw_lower)}"

        # 1) Отрицание
        if re.search(neg_pattern, q):
            for op in OP_KEYWORDS[kw]:
                exclude_ops.add(op.upper())
            # затираем фразу, чтобы не сработал более общий ключ
            q = q.replace(kw_lower, " " * len(kw_lower))
            continue

        # 2) Положительное упоминание
        if kw_lower in q:
            for op in OP_KEYWORDS[kw]:
                include_ops.add(op.upper())
            # тоже затираем, чтобы не зацепить более общий вариант
            q = q.replace(kw_lower, " " * len(kw_lower))

    return include_ops, exclude_ops


def parse_last_operation_filter(query: str) -> str:
    """
    На основе текста запроса возвращает SQL-фрагмент для LastOperation.
    Если ничего не найдено — пустая строка.
    """
    include_ops, exclude_ops = _extract_op_sets(query)

    clauses = []

    if include_ops:
        in_list = ", ".join(f"'{o}'" for o in sorted(include_ops))
        clauses.append(
            f"UCase(LTrim(RTrim([LastOperation]))) IN ({in_list})"
        )

    if exclude_ops:
        not_in_list = ", ".join(f"'{o}'" for o in sorted(exclude_ops))
        clauses.append(
            f"UCase(LTrim(RTrim([LastOperation]))) NOT IN ({not_in_list})"
        )

    if not clauses:
        return ""

    return " AND " + " AND ".join(clauses)
