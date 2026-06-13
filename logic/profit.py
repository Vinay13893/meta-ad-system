"""
RTO-adjusted contribution margin calculations.

All functions are pure (no DB calls) so they can be unit-tested with fixtures.
The DB-fetching wrapper at the bottom calls these with real data.
"""
from __future__ import annotations

from datetime import date
from typing import Any


def calc_order_margin(
    order: dict,
    items: list[dict],
    costs: dict[str, dict],
) -> dict:
    """
    Computes RTO-adjusted contribution margin for a single order.

    order:  {order_id, gross_value, payment_method, status}
    items:  [{product_id, quantity, unit_price}]
    costs:  {product_id: {cogs, shipping_cost, packaging_cost,
                          cod_rto_rate, reverse_ship_cost}}

    Returns a dict with all components so the brief can show the breakdown.
    Missing product costs default to 0 and are flagged via has_full_costs=False.
    """
    gross = float(order.get("gross_value", 0))
    is_cod = order.get("payment_method", "prepaid") == "cod"

    total_cogs = 0.0
    total_packaging = 0.0
    max_shipping = 0.0
    max_reverse_ship = 0.0
    weighted_rto_rate = 0.0
    has_full_costs = True

    for item in items:
        pid = item.get("product_id", "")
        qty = int(item.get("quantity", 1))
        cost = costs.get(pid)

        if not cost:
            has_full_costs = False
            continue

        total_cogs += float(cost.get("cogs", 0)) * qty
        total_packaging += float(cost.get("packaging_cost", 0)) * qty
        max_shipping = max(max_shipping, float(cost.get("shipping_cost", 0)))
        max_reverse_ship = max(max_reverse_ship, float(cost.get("reverse_ship_cost", 0)))
        weighted_rto_rate = max(weighted_rto_rate, float(cost.get("cod_rto_rate", 0)))

    if is_cod:
        realized = gross * (1 - weighted_rto_rate)
        rto_cost = weighted_rto_rate * max_reverse_ship
    else:
        realized = gross
        rto_cost = 0.0

    cm = realized - total_cogs - max_shipping - total_packaging - rto_cost

    return {
        "order_id":       order["order_id"],
        "payment_method": order.get("payment_method"),
        "status":         order.get("status"),
        "gross_value":    gross,
        "realized_value": round(realized, 2),
        "cogs":           round(total_cogs, 2),
        "shipping":       round(max_shipping, 2),
        "packaging":      round(total_packaging, 2),
        "rto_cost":       round(rto_cost, 2),
        "contribution_margin": round(cm, 2),
        "has_full_costs": has_full_costs,
    }


def calc_daily_summary(
    order_margins: list[dict],
    ad_rows: list[dict],
) -> dict:
    """
    Aggregates order-level margins and ad spend into a daily P&L summary.

    order_margins: list of dicts returned by calc_order_margin()
    ad_rows:       list of ad_metrics_daily rows for the day
    """
    total_gross        = sum(o["gross_value"] for o in order_margins)
    total_realized     = sum(o["realized_value"] for o in order_margins)
    total_cm           = sum(o["contribution_margin"] for o in order_margins)
    total_spend        = sum(float(r.get("spend", 0)) for r in ad_rows)
    platform_revenue   = sum(float(r.get("revenue_rep", 0)) for r in ad_rows)

    # MER = realized revenue / ad spend (platform revenue gives a sense of attribution)
    mer = round(total_realized / total_spend, 2) if total_spend else None

    net_profit = round(total_cm - total_spend, 2)

    orders_without_costs = [o["order_id"] for o in order_margins if not o["has_full_costs"]]

    return {
        "order_count":       len(order_margins),
        "total_gross":       round(total_gross, 2),
        "platform_revenue":  round(platform_revenue, 2),
        "realized_revenue":  round(total_realized, 2),
        "total_cogs":        round(sum(o["cogs"] for o in order_margins), 2),
        "total_spend":       round(total_spend, 2),
        "contribution_margin": round(total_cm, 2),
        "net_profit":        net_profit,
        "mer":               mer,
        "costs_incomplete":  bool(orders_without_costs),
        "orders_without_costs": orders_without_costs,
    }


def calc_product_margins(
    order_margins: list[dict],
    order_items_by_order: dict[str, list[dict]],
) -> list[dict]:
    """
    Aggregates per-product RTO-adjusted contribution margin across a day's orders.

    Each product's share of an order's realized_value and contribution_margin is
    prorated by (item_value / order_gross_value), where item_value = unit_price * qty.
    This preserves the invariant: sum of product CMs == order CM.

    order_margins:          list of dicts from calc_order_margin()
    order_items_by_order:   {order_id: [{product_id, quantity, unit_price}]}

    Returns list sorted by contribution_margin ascending (worst first).
    """
    margin_by_order = {m["order_id"]: m for m in order_margins}
    accumulated: dict[str, dict] = {}

    for order_id, items in order_items_by_order.items():
        m = margin_by_order.get(order_id)
        if not m:
            continue
        gross = float(m["gross_value"])
        if gross == 0:
            continue

        for item in items:
            pid = str(item.get("product_id", ""))
            qty = int(item.get("quantity", 1))
            unit_price = float(item.get("unit_price", 0))
            proration = (unit_price * qty) / gross

            if pid not in accumulated:
                accumulated[pid] = {
                    "product_id": pid,
                    "units_sold": 0,
                    "realized_revenue": 0.0,
                    "contribution_margin": 0.0,
                    "costs_incomplete": False,
                }

            accumulated[pid]["units_sold"] += qty
            accumulated[pid]["realized_revenue"] += proration * float(m["realized_value"])
            accumulated[pid]["contribution_margin"] += proration * float(m["contribution_margin"])
            if not m["has_full_costs"]:
                accumulated[pid]["costs_incomplete"] = True

    result = [
        {
            "product_id":          data["product_id"],
            "units_sold":          data["units_sold"],
            "realized_revenue":    round(data["realized_revenue"], 2),
            "contribution_margin": round(data["contribution_margin"], 2),
            "costs_incomplete":    data["costs_incomplete"],
        }
        for data in accumulated.values()
    ]
    return sorted(result, key=lambda x: x["contribution_margin"])


# ── DB-backed wrapper ─────────────────────────────────────────────────────────

def fetch_daily_profit(brand_id: str, target_date: date, sb: Any) -> dict:
    """
    Queries Supabase and returns a daily profit summary dict.
    Calls calc_order_margin() + calc_daily_summary() internally.
    """
    date_str = str(target_date)

    # Orders placed on target_date
    order_rows = (
        sb.table("orders")
        .select("order_id, gross_value, payment_method, status, created_at")
        .eq("brand_id", brand_id)
        .gte("created_at", f"{date_str}T00:00:00Z")
        .lt("created_at", f"{date_str}T23:59:59Z")
        .execute()
    ).data

    if not order_rows:
        return {
            "order_count": 0, "total_gross": 0, "platform_revenue": 0,
            "realized_revenue": 0, "total_cogs": 0, "total_spend": 0,
            "contribution_margin": 0, "net_profit": 0, "mer": None,
            "costs_incomplete": False, "orders_without_costs": [],
            "product_margins": [],
        }

    order_ids = [o["order_id"] for o in order_rows]

    # Order items
    item_rows = (
        sb.table("order_items")
        .select("order_id, product_id, quantity, unit_price")
        .eq("brand_id", brand_id)
        .in_("order_id", order_ids)
        .execute()
    ).data

    items_by_order: dict[str, list] = {}
    for item in item_rows:
        items_by_order.setdefault(item["order_id"], []).append(item)

    # Product costs (might be empty if not yet filled in)
    product_ids = list({i["product_id"] for i in item_rows})
    cost_rows = (
        sb.table("product_costs")
        .select("*")
        .eq("brand_id", brand_id)
        .in_("product_id", product_ids)
        .execute()
    ).data if product_ids else []

    costs = {c["product_id"]: c for c in cost_rows}

    # Ad spend for the day
    ad_rows = (
        sb.table("ad_metrics_daily")
        .select("spend, revenue_rep")
        .eq("brand_id", brand_id)
        .eq("date", date_str)
        .execute()
    ).data

    margins = [
        calc_order_margin(o, items_by_order.get(o["order_id"], []), costs)
        for o in order_rows
    ]

    # Per-product margins
    product_margins = calc_product_margins(margins, items_by_order)

    # Enrich with human-readable product names from the raw catalog
    prod_name_rows = (
        sb.table("raw_shopify_products")
        .select("product_id, payload")
        .eq("brand_id", brand_id)
        .in_("product_id", product_ids)
        .execute()
    ).data if product_ids else []
    product_names = {
        p["product_id"]: p["payload"].get("title", p["product_id"])
        for p in prod_name_rows
    }
    for pm in product_margins:
        pm["product_name"] = product_names.get(pm["product_id"], pm["product_id"])

    summary = calc_daily_summary(margins, ad_rows)
    summary["product_margins"] = product_margins
    return summary
