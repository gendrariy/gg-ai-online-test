from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

import pandas as pd
import streamlit as st


# ---------- CASTING / SHIPPING COMMON HELPERS (copied from main_app.py) ----------

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
    def mask_silver(m):
        return str(m).strip().upper().startswith("SLV")

    def mask_brass(m):
        return str(m).strip().upper().startswith("BRASS")

    def mask_platinum(m):
        return str(m).strip().upper().startswith("PLAT")

    def mask_gold(m):
        c = str(m).strip().upper()
        return not (mask_silver(c) or mask_brass(c) or mask_platinum(c))

    silver_mask = grouped["metal"].apply(mask_silver)
    brass_mask = grouped["metal"].apply(mask_brass)
    plat_mask = grouped["metal"].apply(mask_platinum)
    gold_mask = grouped["metal"].apply(mask_gold)
    return silver_mask, brass_mask, plat_mask, gold_mask


# ---------- CASTING LAYOUT (module) ----------

def render_casting_layout(
    df: pd.DataFrame,
    query: str,
    *,
    format_dates: Callable[[pd.DataFrame], pd.DataFrame],
    render_total_box: Callable[[pd.DataFrame], None],
) -> None:
    if df is None or df.empty:
        st.warning("⚠️ No records found for this filter.")
        return

    df_local = df.copy()

    q_lower = query.lower()
    neg_casting = bool(
        re.search(
            r"(not\s+casting|no\s+casting|not\s+ready\s+casting|casting\s+not\s+ready)",
            q_lower,
        )
    )
    if neg_casting:
        title_prefix = "Not casting"
        title_class = "casting-title-not"
    else:
        title_prefix = "Casting"
        title_class = "casting-title"

    period_text = None
    if "Casting_Date" in df_local.columns:
        cdates = pd.to_datetime(df_local["Casting_Date"], errors="coerce")
        if not cdates.isna().all():
            start = cdates.min()
            end = cdates.max()
            if pd.notna(start) and pd.notna(end):
                if start.date() == end.date():
                    period_text = start.strftime("%m/%d/%Y")
                else:
                    period_text = f"{start.strftime('%m/%d/%Y')} – {end.strftime('%m/%d/%Y')}"

    required = {"metal", "quan", "CastWt"}
    if not required.issubset(set(df_local.columns)):
        st.warning("⚠️ Casting layout: missing required columns (need metal, quan, CastWt).")
        df_fmt = format_dates(df_local)
        st.dataframe(df_fmt)
        render_total_box(df_fmt)
        return

    # --- by metal ---
    grouped = (
        df_local.groupby("metal", as_index=False)
        .agg(
            Qty=("quan", "sum"),
            Weight=("CastWt", "sum"),
        )
    )
    grouped["PurityFactor"] = grouped["metal"].apply(purity_factor)
    grouped["PureMetal"] = grouped["Weight"] * grouped["PurityFactor"]
    grouped["__order"] = grouped["metal"].apply(sort_metal_for_casting)
    grouped = grouped.sort_values("__order").drop(columns="__order")

    grouped["Weight"] = grouped["Weight"].round(3)
    grouped["PureMetal"] = grouped["PureMetal"].round(3)

    silver_mask, brass_mask, plat_mask, gold_mask = _metal_group_masks(grouped)

    # sums
    def _sum(mask):
        return (
            float(grouped.loc[mask, "Qty"].sum()),
            float(grouped.loc[mask, "Weight"].sum()),
            float(grouped.loc[mask, "PureMetal"].sum()),
        )

    gold_qty, gold_weight, gold_pure = _sum(gold_mask)
    silver_qty, silver_weight, silver_pure = _sum(silver_mask)
    brass_qty, brass_weight, brass_pure = _sum(brass_mask)
    plat_qty, plat_weight, plat_pure = _sum(plat_mask)

    total_qty = float(grouped["Qty"].sum())
    total_weight = float(grouped["Weight"].sum())
    total_pure = float(grouped["PureMetal"].sum())

    # --- summary rows: only non-zero groups; TOTAL only if it adds info ---
    rows = []
    def _add_row(name: str, qty: float, weight: float, pure: float):
        if qty != 0 or weight != 0 or pure != 0:
            rows.append(
                {
                    "Metal group": name,
                    "Total qty": qty,
                    "Total weight": round(weight, 3),
                    "Total pure metal": round(pure, 3),
                }
            )

    _add_row("Gold", gold_qty, gold_weight, gold_pure)
    _add_row("Silver", silver_qty, silver_weight, silver_pure)
    _add_row("Brass", brass_qty, brass_weight, brass_pure)
    _add_row("Platinum", plat_qty, plat_weight, plat_pure)

    group_count = len(rows)
    gold_present = bool(gold_mask.any())

    # show summary only for: gold (even if only gold) OR mixed groups
    show_summary = gold_present or (group_count > 1)

    # add TOTAL only if it is not redundant
    if group_count > 1:
        rows.append(
            {
                "Metal group": "TOTAL (all metals)",
                "Total qty": total_qty,
                "Total weight": round(total_weight, 3),
                "Total pure metal": round(total_pure, 3),
            }
        )

    summary = pd.DataFrame(rows) if rows else pd.DataFrame(
        {
            "Metal group": ["TOTAL (all metals)"],
            "Total qty": [total_qty],
            "Total weight": [round(total_weight, 3)],
            "Total pure metal": [round(total_pure, 3)],
        }
    )

    # By metal table: always show when summary is hidden; otherwise show if it adds detail.
    show_by_metal = (not show_summary) or gold_present or (grouped["metal"].nunique() > 1)

    # ------------------ RENDER ------------------

    if show_summary:
        st.markdown(
            f'<h3 class="{title_class}">1️⃣ {title_prefix} summary by metal group</h3>',
            unsafe_allow_html=True,
        )
        st.dataframe(summary.set_index("Metal group"), use_container_width=True)

    if show_by_metal:
        num = "2" if show_summary else "1"
        st.markdown(
            f'<h3 class="{title_class}">{num}️⃣ {title_prefix} by metal</h3>',
            unsafe_allow_html=True,
        )
        if period_text:
            st.markdown(f"**Period (Casting_Date):** {period_text}")

        table = grouped[["metal", "Qty", "Weight", "PureMetal"]].copy()
        table.insert(0, "No.", range(1, len(table) + 1))
        st.dataframe(table.set_index("No."), use_container_width=True)

    detail_no = "3" if show_summary else "2"
    st.subheader(f"{detail_no}️⃣ Detailed casting records")
    df_fmt = format_dates(df_local)
    st.dataframe(df_fmt, use_container_width=True)
    render_total_box(df_fmt)
