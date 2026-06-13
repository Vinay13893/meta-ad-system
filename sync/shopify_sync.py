from __future__ import annotations

from datetime import date

from supabase import Client

from connectors.shopify import fetch_raw_orders, fetch_raw_products, raw_to_order_record


def run_shopify_sync(brand_id: str, creds: dict, domain: str, target_date: date, sb: Client) -> int:
    """
    Fetches Shopify orders for target_date, writes raw to raw_shopify_orders,
    and upserts normalized rows to orders + order_items.
    Returns number of orders synced.
    """
    token = creds["admin_token"]
    raw_orders = fetch_raw_orders(token, domain, target_date, target_date)

    if not raw_orders:
        print(f"  Shopify: no orders for {target_date}")
        return 0

    # 1 — store raw (immutable, keyed by order_id)
    raw_upserts = [
        {
            "brand_id": brand_id,
            "order_id": str(o["id"]),
            "payload": o,
        }
        for o in raw_orders
    ]
    sb.table("raw_shopify_orders").upsert(raw_upserts, on_conflict="brand_id,order_id").execute()

    # 2 — normalize orders
    records = [raw_to_order_record(o) for o in raw_orders]

    order_rows = [
        {
            "brand_id": brand_id,
            "order_id": rec.order_id,
            "created_at": rec.created_at,
            "gross_value": rec.gross_value,
            "payment_method": rec.payment_method,
            "status": rec.status,
        }
        for rec in records
    ]
    sb.table("orders").upsert(order_rows, on_conflict="brand_id,order_id").execute()

    # 3 — normalize order items
    item_rows = [
        {
            "brand_id": brand_id,
            "order_id": rec.order_id,
            "product_id": item["product_id"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
        }
        for rec in records
        for item in rec.items
    ]
    if item_rows:
        sb.table("order_items").upsert(item_rows, on_conflict="brand_id,order_id,product_id").execute()

    print(f"  Shopify: synced {len(records)} orders for {target_date}")
    return len(records)


def run_shopify_products_sync(brand_id: str, creds: dict, domain: str, sb: Client) -> int:
    """Syncs all products (full refresh — products don't have a date dimension)."""
    token = creds["admin_token"]
    raw_products = fetch_raw_products(token, domain)

    if not raw_products:
        print("  Shopify: no products found")
        return 0

    upserts = [
        {
            "brand_id": brand_id,
            "product_id": str(p["id"]),
            "payload": p,
        }
        for p in raw_products
    ]
    sb.table("raw_shopify_products").upsert(upserts, on_conflict="brand_id,product_id").execute()

    print(f"  Shopify: synced {len(raw_products)} products")
    return len(raw_products)
