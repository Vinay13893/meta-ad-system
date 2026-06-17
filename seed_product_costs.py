"""
One-time script: seeds product_costs from raw_shopify_products.

Rules applied:
  cogs           = 30% of avg variant price  (includes packaging — packaging_cost set to 0)
  packaging_cost = 0
  shipping_cost  = 100   (INR, forward delivery)
  cod_rto_rate   = 0.0   (starts at 0; refresh_rto_rates() updates it as RTOs accumulate)
  reverse_ship_cost = 100 (INR, cost when a COD order is returned to origin)

Usage:
  python seed_product_costs.py <brand_id>

brand_id is required to avoid ambiguity when multiple brands exist in the DB.
Safe to re-run — uses upsert so existing rows are updated, not duplicated.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

if len(sys.argv) < 2:
    print("Usage: python seed_product_costs.py <brand_id>")
    print("brand_id is required — run: SELECT id, name FROM brands;")
    sys.exit(1)

brand_id = sys.argv[1]

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# Verify the brand exists and fetch its name + organization_id
brand_row = (
    sb.table("brands")
    .select("id, name, organization_id")
    .eq("id", brand_id)
    .single()
    .execute()
    .data
)
if not brand_row:
    print(f"No brand found with id={brand_id}")
    sys.exit(1)
brand_name = brand_row["name"]
org_id = brand_row.get("organization_id")
if org_id is None:
    print(f"WARNING: brand {brand_id!r} has no organization_id — product_costs rows will have organization_id=NULL")
print(f"Seeding product_costs for brand: {brand_name} ({brand_id})\n")

# Fetch raw products
raw_prods = sb.table("raw_shopify_products").select("product_id, payload").eq("brand_id", brand_id).execute().data
if not raw_prods:
    print("No products in raw_shopify_products. Run the products sync first.")
    sys.exit(1)

rows = []
print(f"{'Product':<42} {'Avg MRP':>8} {'COGS (30%)':>12}")
print("-" * 64)
for r in raw_prods:
    p = r["payload"]
    variants = p.get("variants", [])
    prices = [float(v["price"]) for v in variants if v.get("price")]
    avg_mrp = sum(prices) / len(prices) if prices else 0.0
    cogs = round(avg_mrp * 0.30, 2)
    title = (p.get("title") or r["product_id"])[:40]
    print(f"{title:<42} {avg_mrp:>8.2f} {cogs:>12.2f}")
    rows.append({
        "brand_id":          brand_id,
        "organization_id":   org_id,
        "product_id":        r["product_id"],
        "cogs":              cogs,
        "packaging_cost":    0.0,
        "shipping_cost":     100.0,
        "cod_rto_rate":      0.0,
        "reverse_ship_cost": 100.0,
    })

print(f"\nUpserting {len(rows)} product_costs rows …")
sb.table("product_costs").upsert(rows, on_conflict="brand_id,product_id").execute()
print("Done.")
