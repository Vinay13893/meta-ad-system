"""
Daily job entry point.
Runs every morning via GitHub Actions cron.

Flow:
  1. Sync Meta ad insights for yesterday
  2. Sync Shopify orders + products for yesterday
  3. Compute brief (profit + fatigue)
  4. Email the brief
  5. Write brief to daily_brief_log (done inside run_brief)
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv
from supabase import create_client

from sync.run_sync import run as run_sync, get_organization_id
from logic.brief import run_brief
from jobs.notify import send_daily_brief

load_dotenv()


def main() -> None:
    target_date = date.today() - timedelta(days=1)

    # Allow manual override: python -m jobs.daily_run 2026-06-12
    if len(sys.argv) > 1:
        target_date = date.fromisoformat(sys.argv[1])

    print(f"=== Daily run for {target_date} ===\n")

    # 1 + 2 — sync raw + normalized data
    run_sync(target_date)

    # 3 — compute brief
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)

    sb = create_client(supabase_url, supabase_key)
    brand = sb.table("brands").select("id").single().execute().data
    brand_id = brand["id"]
    org_id   = get_organization_id(brand_id, sb)

    print("\nGenerating brief...")
    brief_text = run_brief(brand_id, target_date, sb, org_id=org_id)
    print(brief_text)

    # 4 — send email
    print("\nSending email...")
    send_daily_brief(target_date, brief_text)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
