# department_filter.py
import re
from typing import Tuple, Set

# Маппинг "ключевые слова в запросе" → реальное DepartmentName
DEPARTMENT_KEYWORDS = {
    "gold control": "Gold Control",
    "jeweller": "Jewellers",
    "jewellers": "Jewellers",
    "jewellery": "Jewellers",
    "jewelry": "Jewellers",
    "managing director": "Managing Director",
    "model maker": "Model Maker & Design",
    "model & design": "Model Maker & Design",
    "model design": "Model Maker & Design",
    "office control": "Office Controls",
    "office controls": "Office Controls",
    "orders and packing": "Orders & Packing",
    "order and packing": "Orders & Packing",
    "packing": "Orders & Packing",
    "polish department": "Polishing",
    "polishing department": "Polishing",
    "polish": "Polishing",
    "polishing": "Polishing",
    "quality control": "Quality Controls",
    "quality controls": "Quality Controls",
    "qc department": "Quality Controls",
    "qc": "Quality Controls",
    "setting department": "Setting",
    "setting": "Setting",
    "stone department": "Stone",
    "stone": "Stone",
    "sub contractor": "Sub Contractor",
    "subcontractor": "Sub Contractor",
    "sub-contractor": "Sub Contractor",
}

NEGATION_WORDS = ("not", "no", "without", "except")


def _extract_dept_sets(query: str) -> Tuple[Set[str], Set[str]]:
    """
    Возвращает два множества:
    include_depts, exclude_depts (реальные имена DepartmentName).
    """
    q = query.lower()
    include, exclude = set(), set()

    # для этих ключей "not X out/in..." считаем, что X относится к операции, а не к департаменту
    special_for_ops = {
        "setting",
        "polish", "polishing",
        "jeweller", "jewellers", "jewellery", "jewelry",
    }
    # слова, которые идут после ключа, если это именно операция, а не департамент
    op_suffix_pattern = r"(?:out\b|in\b|on hold\b|center\b|centre\b|out sub\b)"

    for kw, dept in DEPARTMENT_KEYWORDS.items():
        kw_lower = kw.lower()

        if kw_lower in special_for_ops:
            # НЕ считаем отрицанием департамента конструкции вида:
            #   "not setting out", "without polish in", "not jeweller out"
            neg_pattern = (
                rf"(?:{'|'.join(NEGATION_WORDS)})\s+{re.escape(kw_lower)}"
                rf"(?!\s+{op_suffix_pattern})"
            )
        else:
            neg_pattern = rf"(?:{'|'.join(NEGATION_WORDS)})\s+{re.escape(kw_lower)}"

        # сначала проверяем отрицание
        if re.search(neg_pattern, q):
            exclude.add(dept)
            continue

        # если слово встречается в тексте — добавляем департамент в include
        if kw_lower in q:
            include.add(dept)

    return include, exclude
    """
    Возвращает два множества:
    include_depts, exclude_depts (реальные имена DepartmentName).
    """
    q = query.lower()
    include, exclude = set(), set()

    for kw, dept in DEPARTMENT_KEYWORDS.items():
        # отрицания: not polishing, without qc, except stone department и т.п.
        neg_pattern = rf"(?:{'|'.join(NEGATION_WORDS)})\s+{re.escape(kw)}"
        if re.search(neg_pattern, q):
            exclude.add(dept)
            continue

        # обычное упоминание департамента
        if kw in q:
            include.add(dept)

    return include, exclude


def parse_department_filter(query: str) -> str:
    """
    На основе текста запроса возвращает SQL-фрагмент для DepartmentName.
    Если ничего не найдено — пустая строка.
    """
    include_depts, exclude_depts = _extract_dept_sets(query)

    # если департамент одновременно в include и exclude —
    # считаем, что включение важнее и убираем его из исключений
    conflict = include_depts & exclude_depts
    if conflict:
        exclude_depts = exclude_depts - conflict

    clauses = []

    if include_depts:
        in_list = ", ".join(f"'{d.upper()}'" for d in sorted(include_depts))
        clauses.append(
            f"UCase(LTrim(RTrim([DepartmentName]))) IN ({in_list})"
        )

    if exclude_depts:
        not_in_list = ", ".join(f"'{d.upper()}'" for d in sorted(exclude_depts))
        clauses.append(
            f"UCase(LTrim(RTrim([DepartmentName]))) NOT IN ({not_in_list})"
        )

    if not clauses:
        return ""

    return " AND " + " AND ".join(clauses)
