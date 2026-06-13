# Meta Graph API version: v22.0
from __future__ import annotations

import sys
from datetime import date

import requests

from connectors.base import AdMetricRecord, AdPlatformConnector

BASE_URL = "https://graph.facebook.com/v22.0"

PURCHASE_ACTION_TYPES = {
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
}

FIELDS = ",".join([
    "ad_id", "ad_name",
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "spend", "impressions", "clicks", "inline_link_clicks",
    "ctr", "cpm", "reach", "frequency",
    "actions", "action_values",
])


def fetch_raw_insights(
    token: str, account_id: str, start: date, end: date
) -> list[dict]:
    """Fetches ad-level insights from Meta. Returns raw API rows."""
    if not account_id.startswith("act_"):
        account_id = f"act_{account_id}"

    url = f"{BASE_URL}/{account_id}/insights"
    params = {
        "access_token": token,
        "level": "ad",
        "fields": FIELDS,
        "time_range": f'{{"since":"{start}","until":"{end}"}}',
        "limit": 500,
    }

    rows: list[dict] = []
    while True:
        resp = requests.get(url, params=params, timeout=30)
        body = resp.json()

        if "error" in body:
            err = body["error"]
            print(f"Meta API error {err.get('code')}: {err.get('message')}", file=sys.stderr)
            break

        rows.extend(body.get("data", []))
        next_url = body.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        params = {}

    return rows


def _extract_action_value(actions: list[dict] | None, key: str) -> float:
    if not actions:
        return 0.0
    for a in actions:
        if a.get("action_type") in PURCHASE_ACTION_TYPES:
            return float(a.get("value", 0))
    return 0.0


def raw_to_record(raw: dict) -> AdMetricRecord:
    """Converts one raw Meta API insight row to an AdMetricRecord."""
    return AdMetricRecord(
        platform="meta",
        date=date.fromisoformat(raw.get("date_start", str(date.today()))),
        campaign_id=raw.get("campaign_id"),
        campaign_name=raw.get("campaign_name"),
        adset_id=raw.get("adset_id"),
        adset_name=raw.get("adset_name"),
        ad_id=raw.get("ad_id"),
        ad_name=raw.get("ad_name"),
        spend=float(raw.get("spend", 0)),
        impressions=int(raw.get("impressions", 0)),
        clicks=int(raw.get("clicks", 0)),
        link_clicks=int(raw["inline_link_clicks"]) if raw.get("inline_link_clicks") else None,
        reach=int(raw["reach"]) if raw.get("reach") else None,
        frequency=float(raw["frequency"]) if raw.get("frequency") else None,
        purchases=_extract_action_value(raw.get("actions"), "purchase"),
        revenue_rep=_extract_action_value(raw.get("action_values"), "purchase"),
    )


class MetaConnector(AdPlatformConnector):
    def fetch_ad_metrics(
        self, brand_id: str, creds: dict, start: date, end: date
    ) -> list[AdMetricRecord]:
        token = creds["access_token"]
        account_id = creds.get("account_id", "")
        raw_rows = fetch_raw_insights(token, account_id, start, end)
        return [raw_to_record(r) for r in raw_rows]
