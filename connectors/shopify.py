# Shopify Admin REST API version: 2025-01
from __future__ import annotations

import sys
from datetime import date

import requests

from connectors.base import EcommerceConnector, OrderRecord

API_VERSION = "2025-01"

# Exact gateway name returned by GoKwik for cash-on-delivery orders.
# payment_gateway is always null in this store; payment_gateway_names is the real field.
COD_GATEWAY_NAMES = {"cash_on_delivery"}


def _is_cod(gateway_names: list | None) -> bool:
    if not gateway_names:
        return False
    return any(n.lower() in COD_GATEWAY_NAMES for n in gateway_names)


def _derive_status(order: dict) -> str:
    if order.get("cancelled_at"):
        return "cancelled"
    fulfil = order.get("fulfillment_status") or "unfulfilled"
    financial = order.get("financial_status", "")
    if fulfil == "fulfilled" and financial in ("paid", "partially_refunded"):
        return "delivered"
    if financial == "refunded" and fulfil in ("restocked", "fulfilled"):
        return "returned"
    return "confirmed"


def _parse_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return None


def fetch_raw_orders(
    token: str, domain: str, start: date, end: date
) -> list[dict]:
    """Fetches all orders in UTC window from Shopify. Returns raw order dicts."""
    url = f"https://{domain}/admin/api/{API_VERSION}/orders.json"
    headers = {"X-Shopify-Access-Token": token}
    params = {
        "created_at_min": f"{start}T00:00:00Z",
        "created_at_max": f"{end}T23:59:59Z",
        "status": "any",
        "limit": 250,
    }

    orders: list[dict] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if not resp.ok:
            print(f"Shopify API error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            break
        orders.extend(resp.json().get("orders", []))
        next_url = _parse_link(resp.headers.get("Link", ""))
        if not next_url:
            break
        url = next_url
        params = {}

    return orders


def fetch_raw_products(token: str, domain: str) -> list[dict]:
    """Fetches all products from Shopify. Returns raw product dicts."""
    url = f"https://{domain}/admin/api/{API_VERSION}/products.json"
    headers = {"X-Shopify-Access-Token": token}
    params = {"limit": 250}

    products: list[dict] = []
    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if not resp.ok:
            print(f"Shopify API error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            break
        products.extend(resp.json().get("products", []))
        next_url = _parse_link(resp.headers.get("Link", ""))
        if not next_url:
            break
        url = next_url
        params = {}

    return products


def raw_to_order_record(raw: dict) -> OrderRecord:
    """Converts one raw Shopify order dict to an OrderRecord."""
    gateway_names = raw.get("payment_gateway_names") or []
    items = [
        {
            "product_id": str(li.get("product_id") or li.get("variant_id") or "unknown"),
            "quantity": int(li.get("quantity", 1)),
            "unit_price": float(li.get("price", 0)),
        }
        for li in raw.get("line_items", [])
    ]
    return OrderRecord(
        order_id=str(raw["id"]),
        created_at=raw["created_at"],
        gross_value=float(raw.get("subtotal_price") or raw.get("total_price", 0)),
        payment_method="cod" if _is_cod(gateway_names) else "prepaid",
        status=_derive_status(raw),
        items=items,
    )


class ShopifyConnector(EcommerceConnector):
    def fetch_orders(
        self, brand_id: str, creds: dict, start: date, end: date
    ) -> list[OrderRecord]:
        token = creds["admin_token"]
        domain = creds.get("domain", "")
        raw_orders = fetch_raw_orders(token, domain, start, end)
        return [raw_to_order_record(o) for o in raw_orders]

    def fetch_products(self, brand_id: str, creds: dict) -> list[dict]:
        token = creds["admin_token"]
        domain = creds.get("domain", "")
        return fetch_raw_products(token, domain)
