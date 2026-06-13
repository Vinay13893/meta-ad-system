# Inserts the Meta and Shopify credentials into the connections table.
# Run once after apply_migrations.py.
# Safe to re-run — uses upsert.

from __future__ import annotations

import json
import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL          = os.environ.get("DATABASE_URL")
META_ACCESS_TOKEN     = os.environ.get("META_ACCESS_TOKEN")
META_AD_ACCOUNT_ID    = os.environ.get("META_AD_ACCOUNT_ID")
SHOPIFY_SHOP_DOMAIN   = os.environ.get("SHOPIFY_SHOP_DOMAIN")
SHOPIFY_ADMIN_TOKEN   = os.environ.get("SHOPIFY_ADMIN_TOKEN")

missing = [k for k, v in {
    "DATABASE_URL": DATABASE_URL,
    "META_ACCESS_TOKEN": META_ACCESS_TOKEN,
    "META_AD_ACCOUNT_ID": META_AD_ACCOUNT_ID,
    "SHOPIFY_SHOP_DOMAIN": SHOPIFY_SHOP_DOMAIN,
    "SHOPIFY_ADMIN_TOKEN": SHOPIFY_ADMIN_TOKEN,
}.items() if not v]

if missing:
    print(f"Missing in .env: {', '.join(missing)}")
    sys.exit(1)

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

# Get the brand id
cur.execute("select id from brands where name = 'Sage Royal Ayurveda' limit 1")
row = cur.fetchone()
if not row:
    print("Brand not found — run apply_migrations.py first")
    sys.exit(1)
brand_id = row[0]

connections = [
    {
        "platform":   "meta",
        "account_id": META_AD_ACCOUNT_ID,
        "credentials": {"access_token": META_ACCESS_TOKEN},
    },
    {
        "platform":   "shopify",
        "account_id": SHOPIFY_SHOP_DOMAIN,
        "credentials": {"admin_token": SHOPIFY_ADMIN_TOKEN},
    },
]

for c in connections:
    cur.execute("""
        insert into connections (brand_id, platform, account_id, credentials)
        values (%s, %s, %s, %s)
        on conflict (brand_id, platform, account_id)
        do update set credentials = excluded.credentials,
                      status = 'active'
    """, (brand_id, c["platform"], c["account_id"], json.dumps(c["credentials"])))
    print(f"Upserted {c['platform']} connection for account {c['account_id']}")

cur.close()
conn.close()
print("\nConnections seeded. Database is ready.")
