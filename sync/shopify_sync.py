from __future__ import annotations

from datetime import date

from supabase import Client

from connectors.shopify import fetch_raw_orders, fetch_raw_products, raw_to_order_record


def _is_influencer_order(raw: dict) -> bool:
    """
    Returns True for internal influencer/gifting orders that are marketing
    expense, not revenue. These are created manually by the team with the
    'influencer' tag and should not flow into profit calculations.
    """
    tags = [t.strip().lower() for t in (raw.get("tags") or "").split(",")]
    return "influencer" in tags


def run_shopify_sync(brand_id: str, creds: dict, domain: str, target_date: date, sb: Client) -> int:
    """
    Fetches Shopify orders for target_date, writes raw to raw_shopify_orders,
    and upserts normalized rows to orders + order_items.
    Influencer/gifting orders are stored raw but excluded from normalized tables.
    Returns number of revenue orders synced.
    """
    token = creds["admin_token"]
    raw_orders = fetch_raw_orders(token, domain, target_date, target_date)

    if not raw_orders:
        print(f"  Shopify: no orders for {target_date}")
        return 0

    # 1 — store raw (immutable, ALL orders including influencer)
    raw_upserts = [
        {
            "brand_id": brand_id,
            "order_id": str(o["id"]),
            "payload": o,
        }
        for o in raw_orders
    ]
    sb.table("raw_shopify_orders").upsert(raw_upserts, on_conflict="brand_id,order_id").execute()

    # 2 — normalize only revenue orders (exclude influencer/gifting)
    revenue_orders = [o for o in raw_orders if not _is_influencer_order(o)]
    skipped = len(raw_orders) - len(revenue_orders)
    if skipped:
        print(f"  Shopify: skipped {skipped} influencer order(s)")

    records = [raw_to_order_record(o) for o in revenue_orders]

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

    # Build variant → parent product_id map so items stored with variant_id
    # (when product_id is null on the line item) can still hit product_costs.
    raw_prods = (
        sb.table("raw_shopify_products")
        .select("product_id, payload")
        .eq("brand_id", brand_id)
        .execute()
    ).data
    variant_to_product: dict[str, str] = {}
    for rp in raw_prods:
        for v in rp["payload"].get("variants", []):
            variant_to_product[str(v["id"])] = rp["product_id"]

    # 3 — normalize order items (resolve variant IDs to parent product IDs)
    item_rows = [
        {
            "brand_id": brand_id,
            "order_id": rec.order_id,
            "product_id": variant_to_product.get(item["product_id"], item["product_id"]),
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
        }
        for rec in records
        for item in rec.items
    ]
    if item_rows:
        sb.table("order_items").upsert(item_rows, on_conflict="brand_id,order_id,product_id").execute()

    print(f"  Shopify: synced {len(records)} revenue orders for {target_date}")
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
