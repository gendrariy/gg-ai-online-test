# filters/date_router.py

def detect_date_column(user_query: str) -> str | None:
    """
    Возвращает одну из:
        "pdate"
        "ship_date"
        "request_date"
        "Casting_Date"
        None — если нет указания типа даты
    """
    if not user_query:
        return None

    U = user_query.lower()

    # -------------------------------
    # PDATE (received, inbound, incoming)
    # -------------------------------
    pdate_keys = [
        "received", "got", "inbound", "incoming",
        "entry", "order entry", "order received", "pdate"
    ]
    if any(k in U for k in pdate_keys):
        return "pdate"

    # -------------------------------
    # SHIP_DATE (shipped, sent, dispatched)
    # -------------------------------
    ship_keys = [
        "shipped", "shipping", "ship date",
        "sent", "dispatched", "outbound"
    ]
    # избегаем конфликтов с "shop" или "shape"
    if any(k in U for k in ship_keys) or U.startswith("ship "):
        return "ship_date"

    # -------------------------------
    # REQUEST_DATE (due, deliver by, request)
    # -------------------------------
    req_keys = [
        "request", "requested", "req",
        "request date", "due", "due date",
        "deliver by", "need by", "expected",
        "deadline"
    ]
    if any(k in U for k in req_keys):
        return "request_date"

    # -------------------------------
    # CASTING_DATE (casting, mold)
    # -------------------------------
    casting_keys = [
        "casting", "cast", "casted",
        "casting date", "mold", "molding", "casing"
    ]
    if any(k in U for k in casting_keys):
        return "Casting_Date"

    return None
