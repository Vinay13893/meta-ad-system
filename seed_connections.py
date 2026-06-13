# Inserts the Meta and Shopify credentials into the connections table.
# Run once after applying migrations, or any time you rotate a token.
# Safe to re-run — uses upsert keyed on (brand_id, platform, account_id).
#
# Uses the same supabase-py + SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
# variables as the rest of the pipeline. No DATABASE_URL needed.

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL              = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
META_ACCESS_TOKEN         = os.environ.get("META_ACCESS_TOKEN")
META_AD_ACCOUNT_ID        = os.environ.get("META_AD_ACCOUNT_ID")
SHOPIFY_SHOP_DOMAIN       = os.environ.get("SHOPIFY_SHOP_DOMAIN")
SHOPIFY_ADMIN_TOKEN       = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip("'")

missing = [k for k, v in {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
    "META_ACCESS_TOKEN": META_ACCESS_TOKEN,
    "META_AD_ACCOUNT_ID": META_AD_ACCOUNT_ID,
    "SHOPIFY_SHOP_DOMAIN": SHOPIFY_SHOP_DOMAIN,
    "SHOPIFY_ADMIN_TOKEN": SHOPIFY_ADMIN_TOKEN,
}.items() if not v]

if missing:
    print(f"Missing in .env: {', '.join(missing)}")
    sys.exit(1)

sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

brand = sb.table("brands").select("id").single().execute().data
if not brand:
    print("Brand not found — apply migrations first (Supabase Dashboard → SQL Editor)")
    sys.exit(1)
brand_id = brand["id"]

connections = [
    {
        "brand_id":    brand_id,
        "platform":    "meta",
        "account_id":  META_AD_ACCOUNT_ID,
        "credentials": {"access_token": META_ACCESS_TOKEN},
        "status":      "active",
    },
    {
        "brand_id":    brand_id,
        "platform":    "shopify",
        "account_id":  SHOPIFY_SHOP_DOMAIN,
        "credentials": {"admin_token": SHOPIFY_ADMIN_TOKEN},
        "status":      "active",
    },
]

for c in connections:
    sb.table("connections").upsert(c, on_conflict="brand_id,platform,account_id").execute()
    print(f"Upserted {c['platform']} connection for account {c['account_id']}")

print("\nConnections seeded. Database is ready.")
