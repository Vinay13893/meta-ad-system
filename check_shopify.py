# Shopify Admin REST API version: 2025-01
# Orders reference: https://shopify.dev/docs/api/admin-rest/2025-01/resources/order
#
# Requires env vars: SHOPIFY_SHOP_DOMAIN, SHOPIFY_ADMIN_TOKEN
# Run: python check_shopify.py
#
# NOTE ON COD DETECTION
# Shopify does not have a first-class "COD" flag. We infer it from the
# payment_gateway field. Common COD gateway names for Indian stores:
# 'Cash on Delivery', 'cod', 'manual', 'cash_on_delivery'.
# Verify that COD_KEYWORDS below matches your store's actual gateway name
# (visible in the Shopify admin under each order's Payment section).

from __future__ import annotations

import os
import sys
from datetime import date, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "2025-01"

COD_KEYWORDS = {"cod", "cash", "manual"}  # lowercased substrings to match


def get_yesterday_range() -> tuple[str, str]:
    yesterday = date.today() - timedelta(days=1)
    # Shopify timestamps are in UTC; using midnight-to-midnight UTC.
    # If your store timezone differs from UTC, adjust or filter by local date
    # after fetching.
    start = f"{yesterday}T00:00:00Z"
    end   = f"{yesterday}T23:59:59Z"
    return start, end


def is_cod(gateway: str | None) -> bool:
    if not gateway:
        return False
    g = gateway.lower()
    return any(kw in g for kw in COD_KEYWORDS)


def fetch_orders(domain: str, token: str, start: str, end: str) -> list[dict]:
    """Fetches all orders created in the given UTC window, all statuses."""
    url = f"https://{domain}/admin/api/{API_VERSION}/orders.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    params = {
        "created_at_min": start,
        "created_at_max": end,
        "status": "any",
        "limit": 250,
        "fields": "id,name,total_price,payment_gateway,financial_status,fulfillment_status,cancelled_at,created_at",
    }

    orders: list[dict] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)

        if resp.status_code == 401:
            print("Shopify API error: 401 Unauthorized — check SHOPIFY_ADMIN_TOKEN.")
            sys.exit(1)
        if not resp.ok:
            print(f"Shopify API error: {resp.status_code} — {resp.text[:300]}")
            sys.exit(1)

        batch = resp.json().get("orders", [])
        orders.extend(batch)

        # Shopify paginates via the Link header (cursor-based since API 2019-10).
        link_header = resp.headers.get("Link", "")
        next_url = _parse_next_link(link_header)
        if not next_url:
            break
        url = next_url
        params = {}  # cursor is embedded in the next URL

    return orders


def _parse_next_link(link_header: str) -> str | None:
    """Extracts the 'next' URL from a Shopify Link header, if present."""
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def derive_status(order: dict) -> str:
    """
    Maps Shopify fields to the internal status vocabulary from the spec:
    confirmed | cancelled | delivered | rto (not yet determinable at this stage).
    RTO status is only knowable after fulfilment + return; we mark it as
    'returned' from financial_status == 'refunded' combined with fulfilment.
    """
    if order.get("cancelled_at"):
        return "cancelled"
    fulfil = order.get("fulfillment_status") or "unfulfilled"
    financial = order.get("financial_status", "")
    if fulfil == "fulfilled" and financial in ("paid", "partially_refunded"):
        return "delivered"
    if financial == "refunded" and fulfil in ("restocked", "fulfilled"):
        return "returned"  # closest proxy to RTO; flag for manual review
    return "confirmed"


def fmt_price(val) -> str:
    try:
        return f"₹{float(val):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def print_table(orders: list[dict]) -> None:
    if not orders:
        print("No orders found for yesterday.")
        return

    columns = [
        ("Order",          lambda o: o.get("name", str(o.get("id", "")))),
        ("Created (UTC)",  lambda o: (o.get("created_at") or "")[:16].replace("T", " ")),
        ("Total",          lambda o: fmt_price(o.get("total_price", 0))),
        ("Payment",        lambda o: "COD" if is_cod(o.get("payment_gateway")) else "Prepaid"),
        ("Gateway",        lambda o: (o.get("payment_gateway") or "—")[:20]),
        ("Status",         lambda o: derive_status(o)),
    ]

    headers = [c[0] for c in columns]
    rendered = [[fn(order) for (_, fn) in columns] for order in orders]

    widths = [
        max(len(h), max((len(r[i]) for r in rendered), default=0))
        for i, h in enumerate(headers)
    ]

    sep = "  "
    header_line = sep.join(h.ljust(widths[i]) for i, h in enumerate(headers))
    print(header_line)
    print("-" * len(header_line))
    for row in rendered:
        print(sep.join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def print_summary(orders: list[dict]) -> None:
    total_value = sum(float(o.get("total_price", 0)) for o in orders)
    cod_orders   = [o for o in orders if is_cod(o.get("payment_gateway"))]
    cod_value    = sum(float(o.get("total_price", 0)) for o in cod_orders)
    prepaid_value = total_value - cod_value

    print(f"\nTotal orders : {len(orders)}")
    print(f"Total value  : {fmt_price(total_value)}")
    print(f"  COD        : {len(cod_orders)} orders  {fmt_price(cod_value)}")
    print(f"  Prepaid    : {len(orders) - len(cod_orders)} orders  {fmt_price(prepaid_value)}")


def main() -> None:
    domain = os.environ.get("SHOPIFY_SHOP_DOMAIN")
    token  = os.environ.get("SHOPIFY_ADMIN_TOKEN")

    if not domain or not token:
        print("Missing SHOPIFY_SHOP_DOMAIN or SHOPIFY_ADMIN_TOKEN in .env")
        sys.exit(1)

    start, end = get_yesterday_range()
    print(f"Shopify orders — {start[:10]} (UTC)\n")

    orders = fetch_orders(domain, token, start, end)
    print_table(orders)
    print_summary(orders)


if __name__ == "__main__":
    main()
