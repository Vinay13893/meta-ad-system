from __future__ import annotations

import json
from datetime import date

from supabase import Client

from connectors.meta import fetch_raw_insights, raw_to_record


def run_meta_sync(brand_id: str, creds: dict, account_id: str, target_date: date, sb: Client) -> int:
    """
    Fetches Meta ad insights for target_date, writes raw rows to
    raw_meta_insights, and upserts normalized rows to ad_metrics_daily.
    Returns number of ads synced.
    """
    token = creds["access_token"]
    raw_rows = fetch_raw_insights(token, account_id, target_date, target_date)

    if not raw_rows:
        print(f"  Meta: no data for {target_date}")
        return 0

    # 1 — store raw (immutable)
    raw_upserts = [
        {
            "brand_id": brand_id,
            "date": str(target_date),
            "level": "ad",
            "object_id": row["ad_id"],
            "payload": row,
        }
        for row in raw_rows
        if row.get("ad_id")
    ]
    if raw_upserts:
        sb.table("raw_meta_insights").upsert(raw_upserts, on_conflict="brand_id,date,level,object_id").execute()

    # 2 — normalize and upsert
    records = [raw_to_record(r) for r in raw_rows]
    normalized = [
        {
            "brand_id": brand_id,
            "platform": "meta",
            "date": str(rec.date),
            "campaign_id": rec.campaign_id,
            "campaign_name": rec.campaign_name,
            "adset_id": rec.adset_id,
            "adset_name": rec.adset_name,
            "ad_id": rec.ad_id,
            "ad_name": rec.ad_name,
            "spend": rec.spend,
            "impressions": rec.impressions,
            "clicks": rec.clicks,
            "reach": rec.reach,
            "frequency": rec.frequency,
            "purchases": rec.purchases,
            "revenue_rep": rec.revenue_rep,
            "ctr": rec.link_clicks / rec.impressions if (rec.link_clicks is not None and rec.impressions) else None,
            "cpm": (rec.spend / rec.impressions * 1000) if rec.impressions else None,
            "cpa": (rec.spend / rec.purchases) if rec.purchases else None,
        }
        for rec in records
        if rec.ad_id
    ]
    if normalized:
        sb.table("ad_metrics_daily").upsert(normalized, on_conflict="brand_id,platform,date,ad_id").execute()

    print(f"  Meta: synced {len(records)} ads for {target_date}")
    return len(records)
