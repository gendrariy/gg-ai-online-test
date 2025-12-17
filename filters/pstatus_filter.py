import re


def parse_pstatus_filter(text: str) -> str:
    """
    Фильтр по полю [pstatus].

    Поддерживает:

      CANCEL:
        - Позитив:
            cancel / cancelled / canceled / void / voided / reject / rejected
                -> pstatus = 'CANCEL'
        - Негатив:
            not cancel / no cancel / without cancel / with out cancel
            does not include (any) cancel / cancelled / canceled / void / voided / reject / rejected
                -> pstatus <> 'CANCEL'

      HOLD:
        - Позитив:
            on hold order(s)/job(s)/SO/sales order(s)
            hold orders / hold jobs / hold SO
                -> pstatus = 'HOLD'
        - Негатив:
            not hold / no hold / without hold / with out hold
            not on hold / no on hold / without on hold
            does not include (any) hold / on hold
                -> pstatus <> 'HOLD'

      CLOSED:
        - Позитив:
            closed / finished / completed / done orders/jobs/SO/status
                -> pstatus = 'CLOSED'
        - Негатив:
            not closed / not close / not finished / not completed / not done
            no closed / without closed / with out closed
            does not include (any) closed / finished / completed / done
                -> pstatus <> 'CLOSED'

      OPEN:
        - open order(s)/job(s)/SO/sales order(s)
              -> pstatus = 'OPEN'

      REPORTED (in production):
        - in production / in process / in progress / reported orders
        - release and reported orders / order release and reported / reported and release orders
        - release and reported (без слова order)
              -> pstatus = 'REPORTED'

      RELEASE:
        - release(d) order(s) / orders for release
        - одиночное слово release / released
              -> pstatus = 'RELEASE'

      Комбинации отрицаний:
        - not hold and not cancel
        - not closed bracelet orders and not cancel
        - bracelet orders does not include cancel and closed
              -> AND (pstatus <> ...) AND (pstatus <> ...)

      Комбинации ПОЛОЖИТЕЛЬНЫХ статусов:
        - bracelet release and reported
        - order release and reported
        - release and reported
              -> pstatus IN ('RELEASE', 'REPORTED')
    """
    if not text:
        return ""

    t = text.lower()
    clean = t

    # ---------- отрицательные формы: not / no / without / with out / does not include / not include ----------

    neg_cancel_pat = re.compile(
        r"\b(?:not|no|without|with\s*out|does\s+not\s+include|not\s+include)"
        r"(?:\s+any)?\s+"
        r"(?:cancel(?:ed|led)?|void(?:ed)?|reject(?:ed)?)\b"
    )

    neg_hold_pat = re.compile(
        r"\b(?:not|no|without|with\s*out|does\s+not\s+include|not\s+include)"
        r"(?:\s+any)?\s+"
        r"(?:on\s+hold|hold(?:ing)?)\b"
    )

    neg_closed_pat = re.compile(
        r"\b(?:not|no|without|with\s*out|does\s+not\s+include|not\s+include)"
        r"(?:\s+any)?\s+"
        r"(?:close|closed|finished|completed|done)\b"
    )

    neg_release_pat = re.compile(
        r"\b(?:not|no|without|with\s*out|does\s+not\s+include|not\s+include)"
        r"(?:\s+any)?\s+"
        r"release[d]?\b"
    )

    neg_reported_pat = re.compile(
        r"\b("
        r"order\s+status\s+not\s+reported"                    # order status not reported
        r"|not\s+reported"                                    # not reported
        r"|orders?\s+not\s+in\s+(production|process|progress)"  # orders not in production/process/progress
        r"|orders?\s+without\s+reported"                      # orders without reported
        r"|orders?\s+do(?:es)?\s+not\s+include\s+reported"    # orders does/do not include reported
        r"|orders?\s+not\s+include\s+reported"                # orders not include reported
        r")\b"
    )

    # ---------- вырезаем отрицательные конструкции из текста ----------

    neg_cancel = bool(neg_cancel_pat.search(t))
    if neg_cancel:
        clean = neg_cancel_pat.sub(" ", clean)

    neg_hold = bool(neg_hold_pat.search(t))
    if neg_hold:
        clean = neg_hold_pat.sub(" ", clean)

    neg_closed = bool(neg_closed_pat.search(t))
    if neg_closed:
        clean = neg_closed_pat.sub(" ", clean)

    neg_release = bool(neg_release_pat.search(t))
    if neg_release:
        clean = neg_release_pat.sub(" ", clean)

    neg_reported = bool(neg_reported_pat.search(t))
    if neg_reported:
        clean = neg_reported_pat.sub(" ", clean)

    # ---------- CANCEL (позитив) ----------

    pos_cancel = bool(
        re.search(
            r"\b(cancel(?:ed|led)?|void(?:ed)?|reject(?:ed)?)\b",
            clean,
        )
    )

    # ---------- HOLD (позитив) ----------

    has_hold = False
    if "on hold" in clean:
        has_hold = True
    else:
        if re.search(r"\bhold(?:ing)?\b", clean) and re.search(
            r"\b(order|orders|job|jobs|so|sales order|sale order)\b", clean
        ):
            has_hold = True

    # ---------- CLOSED (позитив, расширенные варианты) ----------

    has_closed = bool(
    re.search(r"\b(closed|finished|completed|done)\b", clean)
    and re.search(
        r"\b(order|orders|job|jobs|so|sales\s+order|sale\s+order|status)\b",
        clean,
    )
)




    # ---------- OPEN (позитив) ----------

    has_open = bool(
        re.search(
            r"\bopen\s+(order|orders|job|jobs|so|sales\s+order|sale\s+order)\b",
            clean,
        )
    )

    # ---------- RE REPORTED (позитив) ----------

    has_reported = bool(
        re.search(r"\bin\s+production\b", clean)
        or re.search(r"\bin\s+process\b", clean)
        or re.search(r"\bin\s+progress\b", clean)
        or re.search(r"\border\s+status\s+reported\b", clean)
        or re.search(
            r"\breported\b(?:\s+(order|orders|job|jobs|so|sales\s+order|sale\s+order))?",
            clean,
        )
    )

    # доп. вариант: "release and reported" / "reported and release"
    if not has_reported:
        if re.search(r"\brelease[d]?\s+and\s+reported\b", clean) or re.search(
            r"\breported\s+and\s+release[d]?\b", clean
        ):
            has_reported = True

    # ---------- RELEASE (позитив) ----------

    has_release = bool(
        re.search(
            r"\brelease[d]?\b(?:\s+"
            r"(order|orders|job|jobs|so|sales\s+order|sale\s+order))?",
            clean,
        )
        or re.search(r"\bfor\s+release\b", clean)
    )

    # ---------- комбинированные ОТРИЦАТЕЛЬНЫЕ статусы ----------

    neg_flags = {
        "HOLD": neg_hold,
        "CANCEL": neg_cancel,
        "CLOSED": neg_closed,
        "RELEASE": neg_release,
        "REPORTED": neg_reported,
    }
    pos_flags = {
        "HOLD": has_hold,
        "CANCEL": pos_cancel,
        "CLOSED": has_closed,
        "RELEASE": has_release,
        "REPORTED": has_reported,
    }
    # "OPEN" по-прежнему считаем отдельной логикой (для него нет отрицания)
    other_pos = has_open

    if any(neg_flags.values()):
        # если одновременно позитив и негатив по одному статусу → считаем неоднозначно
        conflict = False
        for status, is_neg in neg_flags.items():
            if is_neg and pos_flags.get(status, False):
                conflict = True
                break
        if conflict or other_pos:
            return ""

        clauses = []
        if neg_hold:
            clauses.append("UCase(LTrim(RTrim([pstatus]))) <> 'HOLD'")
        if neg_cancel:
            clauses.append("UCase(LTrim(RTrim([pstatus]))) <> 'CANCEL'")
        if neg_closed:
            clauses.append("UCase(LTrim(RTrim([pstatus]))) <> 'CLOSED'")
        if neg_release:
            clauses.append("UCase(LTrim(RTrim([pstatus]))) <> 'RELEASE'")
        if neg_reported:
            clauses.append("UCase(LTrim(RTrim([pstatus]))) <> 'REPORTED'")

        if clauses:
            return " AND (" + ") AND (".join(clauses) + ")"
        else:
            return ""

    # ---------- ПОЛОЖИТЕЛЬНЫЕ статусы (без отрицаний) ----------

    positive_statuses = []

    if pos_cancel:
        positive_statuses.append("CANCEL")
    if has_hold:
        positive_statuses.append("HOLD")
    if has_open:
        positive_statuses.append("OPEN")
    if has_reported:
        positive_statuses.append("REPORTED")
    if has_release:
        positive_statuses.append("RELEASE")
    if has_closed:
        positive_statuses.append("CLOSED")

    if not positive_statuses:
        return ""

    # если один статус → обычное "="
    if len(positive_statuses) == 1:
        status = positive_statuses[0]
        return f" AND (UCase(LTrim(RTrim([pstatus]))) = '{status}')"

    # если несколько статусов → IN ('A','B',...)
    in_list = ",".join(f"'{s}'" for s in positive_statuses)
    return f" AND (UCase(LTrim(RTrim([pstatus]))) IN ({in_list}))"
