# Meta Graph API version: v22.0
# Insights reference: https://developers.facebook.com/docs/marketing-api/insights
#
# Requires env vars: META_ACCESS_TOKEN, META_AD_ACCOUNT_ID
# Run: python check_meta.py

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# Meta returns purchases under different action_type values depending on
# how the account is set up (pixel vs catalogue vs Meta Shop).
PURCHASE_ACTION_TYPES = {
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
}


def get_yesterday() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def fetch_insights(account_id: str, token: str, date_str: str) -> list[dict]:
    """
    Pulls ad-level insights for a single day.
    Handles cursor-based pagination automatically.
    NOTE: Very large accounts may need the async Jobs API instead; the endpoint
    will return error code 100 / subcode 1504 in that case.
    """
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    url = f"{BASE_URL}/{account_id}/insights"
    params = {
        "access_token": token,
        "level": "ad",
        "fields": ",".join([
            "ad_id",
            "ad_name",
            "spend",
            "impressions",
            "clicks",
            "ctr",
            "cpm",
            "reach",
            "frequency",
            "actions",
        ]),
        "time_range": f'{{"since":"{date_str}","until":"{date_str}"}}',
        "limit": 500,
    }

    rows: list[dict] = []
    while True:
        resp = requests.get(url, params=params, timeout=30)
        body = resp.json()

        if "error" in body:
            err = body["error"]
            print(f"Meta API error {err.get('code')}: {err.get('message')}")
            sys.exit(1)

        rows.extend(body.get("data", []))

        next_url = body.get("paging", {}).get("next")
        if not next_url:
            break
        # The 'next' cursor URL already contains all params including the token.
        url = next_url
        params = {}

    return rows


def extract_purchases(actions: list[dict] | None) -> float:
    if not actions:
        return 0.0
    total = 0.0
    for action in actions:
        if action.get("action_type") in PURCHASE_ACTION_TYPES:
            total += float(action.get("value", 0))
    return total


def fmt(val, decimals=2):
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return "0.00"


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No ad data returned for this date.")
        return

    columns = [
        ("Ad Name",    lambda r: r.get("ad_name", "")[:45]),
        ("Spend",      lambda r: fmt(r.get("spend", 0))),
        ("Impressions",lambda r: r.get("impressions", "0")),
        ("Clicks",     lambda r: r.get("clicks", "0")),
        ("CTR %",      lambda r: fmt(r.get("ctr", 0))),
        ("CPM",        lambda r: fmt(r.get("cpm", 0))),
        ("Reach",      lambda r: r.get("reach", "0")),
        ("Frequency",  lambda r: fmt(r.get("frequency", 0))),
        ("Purchases",  lambda r: fmt(extract_purchases(r.get("actions")), 0)),
    ]

    headers = [c[0] for c in columns]
    rendered = [[fn(row) for (_, fn) in columns] for row in rows]

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


def main() -> None:
    token = os.environ.get("META_ACCESS_TOKEN")
    account_id = os.environ.get("META_AD_ACCOUNT_ID")

    if not token or not account_id:
        print("Missing META_ACCESS_TOKEN or META_AD_ACCOUNT_ID in .env")
        sys.exit(1)

    date_str = get_yesterday()
    print(f"Meta Ads — ad-level insights for {date_str}\n")

    rows = fetch_insights(account_id, token, date_str)
    print_table(rows)
    print(f"\n{len(rows)} ad(s) returned.")


if __name__ == "__main__":
    main()
