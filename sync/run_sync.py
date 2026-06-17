"""
Entry point for the daily sync.
Reads all active connections from the DB, runs Meta + Shopify syncs for yesterday.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
from supabase import create_client

from sync.meta_sync import run_meta_sync
from sync.shopify_sync import run_shopify_sync, run_shopify_products_sync, refresh_rto_rates

load_dotenv()


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)
    return create_client(url, key)


def get_organization_id(brand_id: str, sb) -> str | None:
    """Returns the organization_id for a brand, or None if not yet onboarded."""
    result = sb.table("brands").select("organization_id").eq("id", brand_id).single().execute()
    return result.data.get("organization_id") if result.data else None


def run(target_date: date | None = None) -> None:
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    print(f"=== Daily sync for {target_date} ===\n")
    sb = get_supabase()

    # Load all active connections
    conns = sb.table("connections").select("brand_id, platform, account_id, credentials").eq("status", "active").execute()

    meta_conns     = [c for c in conns.data if c["platform"] == "meta"]
    shopify_conns  = [c for c in conns.data if c["platform"] == "shopify"]

    for conn in meta_conns:
        brand_id   = conn["brand_id"]
        account_id = conn["account_id"]
        creds      = conn["credentials"]
        org_id     = get_organization_id(brand_id, sb)
        if org_id is None:
            print(f"  WARNING: brand {brand_id} has no organization_id — rows will be written with organization_id=NULL")
        print(f"[Meta] brand={brand_id} account={account_id}")
        run_meta_sync(brand_id, creds, account_id, target_date, sb, org_id=org_id)

    for conn in shopify_conns:
        brand_id = conn["brand_id"]
        domain   = conn["account_id"]
        creds    = conn["credentials"]
        org_id   = get_organization_id(brand_id, sb)
        if org_id is None:
            print(f"  WARNING: brand {brand_id} has no organization_id — rows will be written with organization_id=NULL")
        print(f"[Shopify] brand={brand_id} shop={domain}")
        # Products first so the variant→product_id map exists before order_items are written
        run_shopify_products_sync(brand_id, creds, domain, sb, org_id=org_id)
        run_shopify_sync(brand_id, creds, domain, target_date, sb, org_id=org_id)
        refresh_rto_rates(brand_id, sb)

    print("\n=== Sync complete ===")


if __name__ == "__main__":
    # Optionally pass a date: python -m sync.run_sync 2026-06-12
    if len(sys.argv) > 1:
        run(date.fromisoformat(sys.argv[1]))
    else:
        run()
