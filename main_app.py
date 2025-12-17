import sys, os
import re
import streamlit as st
import pandas as pd
from datetime import datetime

# Make sure core/filters are in the path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, "core"))
sys.path.append(os.path.join(BASE_DIR, "filters"))

from core.ai_filter_router import ai_parse_query
from core.db_utils import execute_access_query

from ui.tables.casting import render_casting_layout

# ----- Logging setup -----
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "ai_usage_log.txt")


def log_event(
    event_type: str,
    query: str = "",
    sql: str = "",
    layout: str = "",
    rows: int | None = None,
    error: str = "",
):
    """Write simple log line into logs/ai_usage_log.txt."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sql_short = sql.replace("\n", " ")[:500]
        err_short = error.replace("\n", " ")[:300]

        line = (
            f"{ts}\t{event_type}\t"
            f"query={query!r}\t"
            f"rows={rows}\t"
            f"layout={layout}\t"
            f"sql={sql_short!r}\t"
            f"error={err_short!r}\n"
        )
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


# ----- Presets & date formatting -----

PRESET_QUERIES = {
    # Received
    "received_today": "received order today",
    "received_week": "received orders this week",
    "received_month": "received orders this month",

    # Casting
    "casting_today": "casting orders today",
    "casting_week": "casting orders this week",
    "casting_month": "casting orders this month",

    # Shipping
    "shipping_today": "shipping orders today",
    "shipping_last_week": "shipping orders last week",
    "shipping_last_month": "shipping orders last month",
}

DATE_COLS = ["pdate", "request_date", "Casting_Date", "ship_date"]


def format_dates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%m/%d/%Y")
    return df


def render_total_box(df: pd.DataFrame):
    total_qty = None
    total_orders = None

    if "quan" in df.columns:
        df_qty = pd.to_numeric(df["quan"], errors="coerce")
        total_qty = df_qty.sum(skipna=True)

    if "SalesOrder" in df.columns:
        total_orders = df["SalesOrder"].nunique(dropna=True)

    if total_qty is None and total_orders is None:
        return

    if total_orders is not None and total_qty is not None:
        html = f"""
        <div class="total-qty-box">
          <div class="total-line">
            <span class="total-label">Orders (SO):</span>
            <span class="total-number">{total_orders:,}</span>
          </div>
          <div class="total-line">
            <span class="total-label">Total Qty:</span>
            <span class="total-number">{total_qty:,.0f}</span>
          </div>
        </div>
        """
    elif total_qty is not None:
        html = f"""
        <div class="total-qty-box">
          <div class="total-line">
            <span class="total-label">Total Qty:</span>
            <span class="total-number">{total_qty:,.0f}</span>
          </div>
        </div>
        """
    else:
        html = ""

    if html:
        st.markdown(html, unsafe_allow_html=True)


# ---------- RECEIVED LAYOUT ----------

def show_received_layout(df: pd.DataFrame):
    if df is None or df.empty:
        st.warning("⚠️ No records found for this filter.")
        return

    period_text = None
    if "pdate" in df.columns:
        pdates = pd.to_datetime(df["pdate"], errors="coerce")
        if not pdates.isna().all():
            start = pdates.min()
            end = pdates.max()
            if pd.notna(start) and pd.notna(end):
                if start.date() == end.date():
                    period_text = start.strftime("%m/%d/%Y")
                else:
                    period_text = f"{start.strftime('%m/%d/%Y')} – {end.strftime('%m/%d/%Y')}"

    df = format_dates(df)

    base_required = {"order_type", "metal", "quan"}
    if not base_required.issubset(set(df.columns)):
        st.dataframe(df)
        render_total_box(df)
        return

    family_mask = df["order_type"].astype(str).str.upper().str.contains("FAMILY", na=False)
    df_family = df[family_mask].copy()

    st.subheader("1️⃣ Family orders — quantity by metal")
    if period_text:
        st.markdown(f"**Period (pdate):** {period_text}")

    if not df_family.empty:
        fam_series = (
            df_family.groupby("metal")["quan"]
            .sum()
            .sort_index()
        )
        total_all = fam_series.sum()
        fam_table = fam_series.to_frame().T
        fam_table.index = ["Qty"]
        fam_table["Total"] = total_all
        st.dataframe(fam_table)
    else:
        st.info("No family orders in this period.")

    st.subheader("2️⃣ Orders summary by order type (SO count & total qty)")
    summary_required = {"order_type", "SalesOrder", "quan"}
    if summary_required.issubset(set(df.columns)):
        type_summary = (
            df.groupby("order_type", as_index=False)
            .agg(
                SO_Count=("SalesOrder", "nunique"),
                Total_Qty=("quan", "sum"),
            )
            .rename(columns={"order_type": "Order Type"})
        )
        type_summary.insert(0, "No.", range(1, len(type_summary) + 1))
        st.dataframe(type_summary.set_index("No."))
    else:
        st.info("Summary by order type is not available (missing SalesOrder or quan columns).")

    st.subheader("3️⃣ Detailed received orders")
    st.dataframe(df)
    render_total_box(df)


# ---------- CASTING / SHIPPING COMMON HELPERS ----------

KARAT_PURITY = {
    "9": 0.375,
    "10": 0.4167,
    "14": 0.585,
    "18": 0.750,
}


def purity_factor(metal_code: str) -> float | None:
    code = str(metal_code).strip().upper()
    if code.startswith("SLV"):
        return 1.0
    if code.startswith("BRASS"):
        return 1.0
    if code.startswith("PLAT"):
        return 1.0

    digits = ""
    for ch in code:
        if ch.isdigit():
            digits += ch
        else:
            break

    if digits in KARAT_PURITY:
        return KARAT_PURITY[digits]
    return None


def sort_metal_for_casting(code: str):
    c = str(code).strip().upper()
    if c.startswith("SLV"):
        return (0, c)
    if c.startswith("BRASS"):
        return (1, c)
    if c.startswith("PLAT"):
        return (2, c)
    return (3, c)


def _metal_group_masks(grouped: pd.DataFrame):
    def mask_silver(m): return str(m).strip().upper().startswith("SLV")
    def mask_brass(m): return str(m).strip().upper().startswith("BRASS")
    def mask_platinum(m): return str(m).strip().upper().startswith("PLAT")

    def mask_gold(m):
        c = str(m).strip().upper()
        return not (mask_silver(c) or mask_brass(c) or mask_platinum(c))

    silver_mask = grouped["metal"].apply(mask_silver)
    brass_mask = grouped["metal"].apply(mask_brass)
    plat_mask = grouped["metal"].apply(mask_platinum)
    gold_mask = grouped["metal"].apply(mask_gold)
    return silver_mask, brass_mask, plat_mask, gold_mask


# ---------- CASTING LAYOUT ----------

def show_casting_layout(df: pd.DataFrame, query: str):
    # UI rendering delegated to ui/tables/casting.py (refactor only)
    return render_casting_layout(df, query, format_dates=format_dates, render_total_box=render_total_box)

# ---------- SHIPPING LAYOUT ----------

def show_shipping_layout(df: pd.DataFrame):
    if df is None or df.empty:
        st.warning("⚠️ No records found for this filter.")
        return

    df_local = df.copy()

    period_text = None
    if "ship_date" in df_local.columns:
        sdates = pd.to_datetime(df_local["ship_date"], errors="coerce")
        if not sdates.isna().all():
            start = sdates.min()
            end = sdates.max()
            if pd.notna(start) and pd.notna(end):
                if start.date() == end.date():
                    period_text = start.strftime("%m/%d/%Y")
                else:
                    period_text = f"{start.strftime('%m/%d/%Y')} – {end.strftime('%m/%d/%Y')}"

    required = {"metal", "quan", "LastWeight"}
    if not required.issubset(set(df_local.columns)):
        st.warning("⚠️ Shipping layout: missing required columns (need metal, quan, LastWeight).")
        df_fmt = format_dates(df_local)
        st.dataframe(df_fmt)
        render_total_box(df_fmt)
        return

    grouped = (
        df_local.groupby("metal", as_index=False)
        .agg(
            Qty=("quan", "sum"),
            Weight=("LastWeight", "sum"),
        )
    )
    grouped["PurityFactor"] = grouped["metal"].apply(purity_factor)
    grouped["PureMetal"] = grouped["Weight"] * grouped["PurityFactor"]
    grouped["__order"] = grouped["metal"].apply(sort_metal_for_casting)
    grouped = grouped.sort_values("__order").drop(columns="__order")

    grouped["Weight"] = grouped["Weight"].round(3)
    grouped["PureMetal"] = grouped["PureMetal"].round(3)

    st.subheader("1️⃣ Shipping by metal")
    if period_text:
        st.markdown(f"**Period (ship_date):** {period_text}")

    table = grouped[["metal", "Qty", "Weight", "PureMetal"]].copy()
    table.insert(0, "No.", range(1, len(table) + 1))
    st.dataframe(table.set_index("No."))

    silver_mask, brass_mask, plat_mask, gold_mask = _metal_group_masks(grouped)

    gold_qty = grouped.loc[gold_mask, "Qty"].sum()
    gold_weight = grouped.loc[gold_mask, "Weight"].sum()
    gold_pure = grouped.loc[gold_mask, "PureMetal"].sum()

    silver_qty = grouped.loc[silver_mask, "Qty"].sum()
    silver_weight = grouped.loc[silver_mask, "Weight"].sum()
    silver_pure = grouped.loc[silver_mask, "PureMetal"].sum()

    brass_qty = grouped.loc[brass_mask, "Qty"].sum()
    brass_weight = grouped.loc[brass_mask, "Weight"].sum()
    brass_pure = grouped.loc[brass_mask, "PureMetal"].sum()

    plat_qty = grouped.loc[plat_mask, "Qty"].sum()
    plat_weight = grouped.loc[plat_mask, "Weight"].sum()
    plat_pure = grouped.loc[plat_mask, "PureMetal"].sum()

    total_qty = grouped["Qty"].sum()
    total_weight = grouped["Weight"].sum()
    total_pure = grouped["PureMetal"].sum()

    summary = pd.DataFrame(
        {
            "Metal group": [
                "Gold",
                "Silver",
                "Brass",
                "Platinum",
                "TOTAL (all metals)",
            ],
            "Total qty": [
                gold_qty,
                silver_qty,
                brass_qty,
                plat_qty,
                total_qty,
            ],
            "Total weight": [
                round(gold_weight, 3),
                round(silver_weight, 3),
                round(brass_weight, 3),
                round(plat_weight, 3),
                round(total_weight, 3),
            ],
            "Total pure metal": [
                round(gold_pure, 3),
                round(silver_pure, 3),
                round(brass_pure, 3),
                round(plat_pure, 3),
                round(total_pure, 3),
            ],
        }
    )

    st.subheader("2️⃣ Shipping summary by metal group")
    st.dataframe(summary.set_index("Metal group"))

    st.subheader("3️⃣ Detailed shipping records")
    df_fmt = format_dates(df_local)
    st.dataframe(df_fmt)
    render_total_box(df_fmt)


# ---------- MAIN APP ----------

def main():
    st.set_page_config(page_title="AI Assistant — Jewelry Production (test v1)", layout="wide")
    st.title("💎 AI Assistant — Jewelry Production (test v1)")

    st.markdown(
        """
        <style>
        /* All Streamlit buttons: same size */
        div.stButton > button {
            width: 190px;
            height: 2.2em;
            padding: 0.2rem 0.2rem;
            font-size: 0.85rem;
            font-weight: 500;
            border-radius: 6px;
            border: 1px solid #555555;
        }

        /* Header text for quick groups – ONLY underline */
        .quick-header {
            padding-bottom: 0.25rem;
            margin-bottom: 0.35rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.16);
        }
        .quick-header-text {
            text-align: center;
            font-weight: 600;
            color: #4ea8de;
            font-size: 0.9rem;
        }

        .quick-buttons div.stButton {
            margin-bottom: 0.3rem;
        }

        .total-qty-box {
            margin-top: 0.5rem;
            margin-bottom: 0.0rem;
            padding: 0.4rem 0.9rem;
            border-radius: 8px;
            display: inline-block;
            background-color: rgba(255, 215, 0, 0.06);
            border: 1px solid rgba(255, 215, 0, 0.55);
        }
        .total-line { display: flex; flex-direction: row; align-items: baseline; }
        .total-line + .total-line { margin-top: 0.1rem; }
        .total-label { font-size: 0.9rem; color: #f7c948; font-weight: 500; }
        .total-number { font-size: 1.15rem; color: #ffe083; font-weight: 700; margin-left: 0.35rem; }

        .casting-title { color: #4caf50 !important; font-weight: 600; }
        .casting-title-not { color: #4ea8de !important; font-weight: 600; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Quick queries / คำถามด่วน")

    # session state: query (last executed) and query_input (current text in box)
    if "query" not in st.session_state:
        st.session_state["query"] = ""
    if "query_input" not in st.session_state:
        st.session_state["query_input"] = ""

    preset_query = None
    run_now = False

    col_rec, col_cast, col_ship, _ = st.columns([1, 1, 1, 2])

    # ----- Received -----
    with col_rec:
        st.markdown(
            '<div class="quick-header"><div class="quick-header-text">'
            'Received (orders) / รับออร์เดอร์เข้า'
            '</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
        if st.button("Today / วันนี้", key="btn_rec_today"):
            preset_query = PRESET_QUERIES["received_today"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("This week / สัปดาห์นี้", key="btn_rec_week"):
            preset_query = PRESET_QUERIES["received_week"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("This month / เดือนนี้", key="btn_rec_month"):
            preset_query = PRESET_QUERIES["received_month"]
            st.session_state["query_input"] = preset_query
            run_now = True
        st.markdown("</div>", unsafe_allow_html=True)

    # ----- Casting -----
    with col_cast:
        st.markdown(
            '<div class="quick-header"><div class="quick-header-text">'
            'Casting / หล่อ'
            '</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
        if st.button("Today / วันนี้", key="btn_cast_today"):
            preset_query = PRESET_QUERIES["casting_today"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("This week / สัปดาห์นี้", key="btn_cast_week"):
            preset_query = PRESET_QUERIES["casting_week"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("This month / เดือนนี้", key="btn_cast_month"):
            preset_query = PRESET_QUERIES["casting_month"]
            st.session_state["query_input"] = preset_query
            run_now = True
        st.markdown("</div>", unsafe_allow_html=True)

    # ----- Shipping -----
    with col_ship:
        st.markdown(
            '<div class="quick-header"><div class="quick-header-text">'
            'Shipping / จัดส่ง'
            '</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="quick-buttons">', unsafe_allow_html=True)
        if st.button("Today / วันนี้", key="btn_ship_today"):
            preset_query = PRESET_QUERIES["shipping_today"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("Last week / สัปดาห์ที่แล้ว", key="btn_ship_last_week"):
            preset_query = PRESET_QUERIES["shipping_last_week"]
            st.session_state["query_input"] = preset_query
            run_now = True
        if st.button("Last month / เดือนที่แล้ว", key="btn_ship_last_month"):
            preset_query = PRESET_QUERIES["shipping_last_month"]
            st.session_state["query_input"] = preset_query
            run_now = True
        st.markdown("</div>", unsafe_allow_html=True)

    # если нажали preset – фиксируем его как последний запрос тоже
    if preset_query:
        st.session_state["query"] = preset_query

    # ---- форма для ручного ввода (Enter = Run) ----
    with st.form("query_form"):
        st.text_input(
            "Enter your query for AI:",
            key="query_input",
        )
        submit = st.form_submit_button("🔍 Run (Enter)")

    if submit:
        st.session_state["query"] = st.session_state["query_input"]
        run_now = True

    query = st.session_state["query"]

    if query:
        try:
            sql = ai_parse_query(query)
            log_event("PARSE_OK", query=query, sql=sql)

            st.subheader("📘 Generated SQL")
            st.code(sql, language="sql")

            if run_now:
                try:
                    df = execute_access_query(sql)
                except Exception as run_err:
                    log_event("RUN_ERROR", query=query, sql=sql, error=str(run_err))
                    raise

                if df is not None and not df.empty:
                    q_lower = query.lower()
                    rows_count = len(df)

                    if "received order" in q_lower or "received orders" in q_lower:
                        layout_name = "received"
                        show_received_layout(df)
                    elif "casting" in q_lower:
                        layout_name = "casting"
                        show_casting_layout(df, query)
                    elif "shipping" in q_lower or "shipped" in q_lower or "ship " in q_lower:
                        layout_name = "shipping"
                        show_shipping_layout(df)
                    else:
                        layout_name = "default"
                        df_fmt = format_dates(df)
                        st.dataframe(df_fmt)
                        render_total_box(df_fmt)

                    log_event("RUN_OK", query=query, sql=sql, layout=layout_name, rows=rows_count)
                else:
                    st.warning("⚠️ No records found for this filter.")
                    log_event("NO_ROWS", query=query, sql=sql, rows=0)

        except Exception as e:
            st.error(f"❌ Error while building SQL: {e}")
            log_event("PARSE_ERROR", query=query, error=str(e))


if __name__ == "__main__":
    main()
