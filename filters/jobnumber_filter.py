import re


def _clean_code(code: str) -> str:
    code = (code or "").strip()
    # trim common trailing punctuation
    code = re.sub(r"[\s,;:.]+$", "", code)
    return code


def _is_valid_job_code(code: str) -> bool:
    if not code:
        return False
    if len(code) < 3:
        return False
    # must contain at least one digit
    return any(ch.isdigit() for ch in code)


def _build_like_variants(field_expr: str, code_u: str) -> str:
    # Access SQL: keep same style as your SO/PO filters: exact OR prefix-with-backslash OR prefix-with-hyphen
    # Escape single quotes for SQL literal
    safe = code_u.replace("'", "''")
    return (
        f"(({field_expr} = '{safe}') OR "
        f"({field_expr} LIKE '{safe}\\%') OR "
        f"({field_expr} LIKE '{safe}-%'))"
    )


def parse_jobnumber_filter(text: str) -> str:
    """
    Filter for [JobNumber].

    Recognizes JobNumber ONLY when explicitly prefixed by one of:
      - job 12345, job#12345, job:12345
      - jobnumber 12345
      - job number 12345
      - jn 12345

    Supports negatives:
      - not job 12345 / without job 12345 / no job 12345
      - job not 12345

    Returns SQL fragment starting with ' AND ...' or '' if nothing found.
    """
    if not text:
        return ""

    t = " ".join(text.strip().split())
    # Patterns capture the code in group 1
    # Allow letters/digits and separators like '-', '/', '\'
    code_pat = r"([A-Za-z0-9][A-Za-z0-9\-/]{1,})"

    pos_codes: list[str] = []
    neg_codes: list[str] = []

    # NEG: not/without/no + (job|job number|jobnumber|jn) + code
    neg_patterns = [
        rf"\b(?:not|no|without)\s+(?:job\s*number|jobnumber|job\s*#?|jn)\s*[:#]?\s*{code_pat}\b",
        rf"\bjob\s+not\s+{code_pat}\b",
    ]
    for pat in neg_patterns:
        for m in re.finditer(pat, t, flags=re.IGNORECASE):
            code = _clean_code(m.group(1))
            if _is_valid_job_code(code):
                neg_codes.append(code)

    # POS: (job|job number|jobnumber|jn) + code
    pos_patterns = [
        rf"\b(?:job\s*number|jobnumber|job\s*#?|jn)\s*[:#]?\s*{code_pat}\b",
    ]
    for pat in pos_patterns:
        for m in re.finditer(pat, t, flags=re.IGNORECASE):
            code = _clean_code(m.group(1))
            if _is_valid_job_code(code):
                pos_codes.append(code)

    # Normalize + de-duplicate
    def _uniq_upper(codes: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for c in codes:
            u = c.upper()
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    pos_u = _uniq_upper(pos_codes)
    neg_u = _uniq_upper(neg_codes)

    # If same code appears in both, keep it only in NEG (safer)
    if pos_u and neg_u:
        pos_u = [c for c in pos_u if c not in set(neg_u)]

    if not pos_u and not neg_u:
        return ""

    field = "UCase(LTrim(RTrim([JobNumber])))"
    sql = ""

    if pos_u:
        pos_clauses = [_build_like_variants(field, c) for c in pos_u]
        sql += " AND (" + " OR ".join(pos_clauses) + ")"

    if neg_u:
        neg_clauses = [_build_like_variants(field, c) for c in neg_u]
        sql += " AND NOT (" + " OR ".join(neg_clauses) + ")"

    return sql
