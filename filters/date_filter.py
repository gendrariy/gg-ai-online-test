from __future__ import annotations
import re
from datetime import datetime, timedelta, date
from typing import Tuple, Optional

MONTHS = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}


def _today() -> date:
    return datetime.now().date()


def _month_bounds(year: int, month: int) -> Tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _last_week_bounds(today: date) -> Tuple[date, date]:
    this_monday = today - timedelta(days=today.weekday())
    last_sunday = this_monday - timedelta(days=1)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def _parse_numeric_date_token(tok: str) -> Optional[date]:
    m = re.fullmatch(r"(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})", tok.strip())
    if not m:
        return None
    mm, dd, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if yy < 100:
        yy += 2000
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def parse_date_range(user_query: str) -> Tuple[Optional[date], Optional[date], str]:
    q = user_query.strip().lower()
    today = _today()
    start_date = None
    end_date = None

    # --- NEW: last N days / past N days ---
    match_last_days = re.search(r"\b(last|past)\s+(\d+)\s+days\b", q)
    if match_last_days:
        n = int(match_last_days.group(2))
        if n > 0:
            start_date = today - timedelta(days=n - 1)
            end_date = today
            q = q.replace(match_last_days.group(0), "")

    # --- NEW: last N months (calendar months) ---
    match_last_months = re.search(r"\b(last|past)\s+(\d+)\s+months?\b", q)
    if match_last_months and not start_date:
        n = int(match_last_months.group(2))
        if n > 0:
            year = today.year
            month = today.month

            # determine end month (previous full month)
            end_year = year
            end_month = month - 1
            if end_month == 0:
                end_month = 12
                end_year -= 1
            _, end_date = _month_bounds(end_year, end_month)

            # start month
            start_month = end_month - (n - 1)
            start_year = end_year
            while start_month <= 0:
                start_month += 12
                start_year -= 1

            start_date, _ = _month_bounds(start_year, start_month)

            q = q.replace(match_last_months.group(0), "")

    # --- NEW: from <numeric date> up to date/today ---
    match_num_to_date = re.search(
        r"\bfrom\s+(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})\s+(?:up\s+to|to|until)\s+(?:date|today)\b",
        q
    )
    if match_num_to_date and not start_date:
        start_token = match_num_to_date.group(1)
        start_date = _parse_numeric_date_token(start_token)
        end_date = today
        q = re.sub(
            r"\bfrom\s+\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}\s+(?:up\s+to|to|until)\s+(?:date|today)\b",
            "",
            q
        )

    # --- NEW: month and month (e.g., "september and october") ---
    match_two_months = re.search(
        r"\b([a-z]+)\s+and\s+([a-z]+)\b", q
    )
    if match_two_months and not start_date:
        m1, m2 = match_two_months.group(1).upper(), match_two_months.group(2).upper()
        if m1 in MONTHS and m2 in MONTHS:
            y = today.year
            start_date, _ = _month_bounds(y, MONTHS[m1])
            _, end_date = _month_bounds(y, MONTHS[m2])
            q = re.sub(r"\b[a-z]+\s+and\s+[a-z]+\b", "", q)

    # --- from <month> up to date ---
    match_to_date = re.search(r"\bfrom\s+([a-z]+)\s+(?:up\s+to|to|until)\s+date\b", q)
    if match_to_date and not start_date:
        month_word = match_to_date.group(1).upper()
        if month_word in MONTHS:
            y = today.year
            m = MONTHS[month_word]
            start_date = date(y, m, 1)
            end_date = today
            q = re.sub(r"\bfrom\s+[a-z]+\s+(?:up\s+to|to|until)\s+date\b", "", q)

    # --- from <month/numeric> to <month/numeric> ---
    if not start_date:
        match = re.search(r"\bfrom\s+([a-z0-9\/\.\-]+)\s+(?:up\s+to|to|until)\s+([a-z0-9\/\.\-]+)", q)
        if match:
            start_token, end_token = match.group(1), match.group(2)
            if start_token.upper() in MONTHS:
                sm = MONTHS[start_token.upper()]
                start_date, _ = _month_bounds(today.year, sm)
            else:
                start_date = _parse_numeric_date_token(start_token)

            if end_token.upper() in MONTHS:
                em = MONTHS[end_token.upper()]
                _, end_date = _month_bounds(today.year, em)
            else:
                end_date = _parse_numeric_date_token(end_token)

            q = re.sub(r"\bfrom\s+[a-z0-9\/\.\-]+\s+(?:up\s+to|to|until)\s+[a-z0-9\/\.\-]+", "", q)

    # --- NEW: "up to / until / till <numeric date>" (без "from") ---
    if not start_date and not end_date:
        m = re.search(
            r"\b(?:up\s+to|until|till)\s+(\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4})\b",
            q
        )
        if m:
            d = _parse_numeric_date_token(m.group(1))
            if d:
                end_date = d
                q = re.sub(
                    r"\b(?:up\s+to|until|till)\s+\d{1,2}[\/\.\-]\d{1,2}[\/\.\-]\d{2,4}\b",
                    "",
                    q
                )

    # --- single month ---
    if not start_date and not end_date:
        for name, mm in MONTHS.items():
            if re.search(rf"\b{name.lower()}\b", q):
                start_date, end_date = _month_bounds(today.year, mm)
                q = re.sub(rf"\b{name.lower()}\b", "", q)
                break

    # --- explicit numeric date ---
    if not start_date and not end_date:
        m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", q)
        if m:
            d = _parse_numeric_date_token(m.group(1))
            start_date = d
            end_date = d
            q = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", "", q)

    # --- year only ---
    if not start_date and not end_date:
        m = re.search(r"\b(20\d{2})\b", q)
        if m:
            yy = int(m.group(1))
            start_date = date(yy, 1, 1)
            end_date = date(yy, 12, 31)
            q = re.sub(r"\b20\d{2}\b", "", q)

    # --- keywords ---
    if "last week" in q:
        start_date, end_date = _last_week_bounds(today)
        q = q.replace("last week", "")
    elif "this week" in q:
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
        q = q.replace("this week", "")
    elif "yesterday" in q:
        start_date = today - timedelta(days=1)
        end_date = start_date
        q = q.replace("yesterday", "")
    elif "today" in q:
        start_date = end_date = today
        q = q.replace("today", "")
    elif "this month" in q:
        start_date, end_date = _month_bounds(today.year, today.month)
        q = q.replace("this month", "")
    elif "last month" in q:
        m = today.month - 1 or 12
        y = today.year - (1 if today.month == 1 else 0)
        start_date, end_date = _month_bounds(y, m)
        q = q.replace("last month", "")

    return start_date, end_date, q.strip()
