"""
Morning brief: composes the daily message and writes it to daily_brief_log.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from logic.profit import fetch_daily_profit
from logic.fatigue import fetch_fatigue_flags


def _inr(val) -> str:
    try:
        return f"₹{float(val):,.0f}"
    except (TypeError, ValueError):
        return "₹?"


def _pct(val) -> str:
    try:
        return f"{float(val):.1f}%"
    except (TypeError, ValueError):
        return "?%"


def compose_brief(
    target_date: date,
    profit: dict,
    flags: list[dict],
    ad_rows: list[dict],
) -> str:
    """
    Pure function. Returns the brief as a plain-text string.
    Intentionally terse — will adapt to WhatsApp/Telegram formatting later.
    """
    lines = []
    lines.append(f"📊 Daily Brief — {target_date.strftime('%d %b %Y')}")
    lines.append("─" * 38)

    # Revenue block
    lines.append(f"Orders          : {profit['order_count']}")
    lines.append(f"Gross revenue   : {_inr(profit['total_gross'])}")
    lines.append(f"Platform revenue: {_inr(profit['platform_revenue'])}  (Meta-reported)")
    lines.append(f"Realized revenue: {_inr(profit['realized_revenue'])}  (after RTO adj.)")
    lines.append(f"Ad spend        : {_inr(profit['total_spend'])}")

    mer = profit.get("mer")
    lines.append(f"MER             : {round(mer, 2):.2f}x" if mer else "MER             : —  (no spend)")

    # Contribution margin block
    lines.append("")
    lines.append(f"COGS            : {_inr(profit['total_cogs'])}")
    cm = profit['contribution_margin']
    net = profit['net_profit']
    lines.append(f"Contribution CM : {_inr(cm)}")
    lines.append(f"Net profit      : {_inr(net)}  (CM − ad spend)")

    if profit.get("costs_incomplete"):
        lines.append("")
        lines.append("⚠️  Cost data missing for some products.")
        lines.append("   Add rows to product_costs table for accurate margins.")

    # Ad-level spend table
    if ad_rows:
        lines.append("")
        lines.append("Ad spend breakdown:")
        for r in sorted(ad_rows, key=lambda x: float(x.get("spend", 0)), reverse=True):
            name = (r.get("ad_name") or "—")[:32]
            lines.append(
                f"  {name:<32}  {_inr(r.get('spend', 0))}  "
                f"CTR {_pct(r.get('ctr') or 0)}  "
                f"Freq {float(r.get('frequency') or 0):.1f}"
            )

    # Product profitability (only when 5+ distinct products ordered that day)
    pm = profit.get("product_margins", [])
    if len(pm) >= 5:
        lines.append("")
        lines.append("Product margins (worst → best):")
        bottom = pm[:3]
        bottom_ids = {p["product_id"] for p in bottom}
        top = [p for p in reversed(pm) if p["product_id"] not in bottom_ids][:3]
        top_asc = list(reversed(top))   # ascending CM so worst-to-best reads top-to-bottom

        for p in bottom:
            name = (p.get("product_name") or p["product_id"])[:28]
            units = f"{p['units_sold']} unit{'s' if p['units_sold'] != 1 else ''}"
            note = "  *" if p["costs_incomplete"] else ""
            lines.append(f"  {name:<28}  {units:<8}  CM {_inr(p['contribution_margin'])}{note}")

        if top_asc:
            lines.append("  ···")
            for p in top_asc:
                name = (p.get("product_name") or p["product_id"])[:28]
                units = f"{p['units_sold']} unit{'s' if p['units_sold'] != 1 else ''}"
                note = "  *" if p["costs_incomplete"] else ""
                lines.append(f"  {name:<28}  {units:<8}  CM {_inr(p['contribution_margin'])}{note}")

        if any(p["costs_incomplete"] for p in pm):
            lines.append("  * costs incomplete for this product")

    # Fatigue flags
    if flags:
        lines.append("")
        lines.append(f"⚠️  {len(flags)} flag(s) detected:")
        for f in flags:
            lines.append(f"  [{f['flag'].replace('_',' ').upper()}] {f['ad_name']}")
            lines.append(f"  → {f['suggestion']}")
    else:
        lines.append("")
        lines.append("✓  No fatigue flags.")

    lines.append("─" * 38)
    return "\n".join(lines)


def run_brief(brand_id: str, target_date: date, sb: Any) -> str:
    """
    Fetches all data, composes brief, saves to daily_brief_log, returns text.
    """
    profit = fetch_daily_profit(brand_id, target_date, sb)
    flags  = fetch_fatigue_flags(brand_id, target_date, sb)

    ad_rows = (
        sb.table("ad_metrics_daily")
        .select("ad_name, spend, ctr, frequency, impressions, clicks, reach")
        .eq("brand_id", brand_id)
        .eq("date", str(target_date))
        .execute()
    ).data

    text = compose_brief(target_date, profit, flags, ad_rows)

    # Persist to daily_brief_log
    payload = {
        "brand_id": brand_id,
        "date":     str(target_date),
        "summary":  json.dumps({
            "profit": profit,
            "flags":  flags,
            "brief_text": text,
        }),
    }
    sb.table("daily_brief_log").upsert(payload, on_conflict="brand_id,date").execute()

    return text
