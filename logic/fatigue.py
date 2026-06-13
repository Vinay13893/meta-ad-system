"""
Creative and audience fatigue detection.

Compares trailing 7 days vs prior 7 days per ad.
All detection logic is in pure functions for testability.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

# Thresholds from CLAUDE.md §7.2
FREQ_INCREASE_PCT   = 0.25   # 25% increase in frequency triggers flag
FREQ_ABSOLUTE_FLOOR = 3.0    # or absolute frequency ≥ 3 triggers flag
CTR_DROP_PCT        = 0.20   # 20% drop in CTR
CPA_RISE_PCT        = 0.20   # 20% rise in CPA
MIN_SPEND_FLOOR     = 100.0  # ignore ads with trivial spend (INR)
CPM_RISE_PCT        = 0.10   # 10% rise in CPM for audience fatigue


def _avg(rows: list[dict], field: str) -> float | None:
    vals = [float(r[field]) for r in rows if r.get(field) is not None]
    return sum(vals) / len(vals) if vals else None


def _sum(rows: list[dict], field: str) -> float:
    return sum(float(r.get(field, 0)) for r in rows)


def detect_fatigue(
    metrics_by_ad: dict[str, list[dict]],
) -> list[dict]:
    """
    Pure function. Detects creative and audience fatigue per ad.

    metrics_by_ad: {ad_id: [list of ad_metrics_daily rows, newest first]}
                   Each row must have: ad_id, ad_name, date, spend, impressions,
                   clicks, reach, frequency, ctr, cpm, cpa, purchases

    Returns list of flag dicts, one per flagged ad.
    """
    flags = []

    for ad_id, rows in metrics_by_ad.items():
        if len(rows) < 2:
            continue

        # Sort newest-first
        rows_sorted = sorted(rows, key=lambda r: r["date"], reverse=True)

        trailing = rows_sorted[:7]   # most recent 7 days
        prior    = rows_sorted[7:14] # prior 7 days

        if not prior:
            continue

        spend_trailing = _sum(trailing, "spend")
        if spend_trailing < MIN_SPEND_FLOOR:
            continue

        ad_name = rows_sorted[0].get("ad_name", ad_id)

        freq_t = _avg(trailing, "frequency")
        freq_p = _avg(prior,    "frequency")
        ctr_t  = _avg(trailing, "ctr")
        ctr_p  = _avg(prior,    "ctr")
        cpa_t  = _avg(trailing, "cpa")
        cpa_p  = _avg(prior,    "cpa")
        cpm_t  = _avg(trailing, "cpm")
        cpm_p  = _avg(prior,    "cpm")
        reach_t = _avg(trailing, "reach")
        reach_p = _avg(prior,    "reach")

        # ── Creative fatigue: freq ↑, CTR ↓, CPA ↑ ───────────────────────
        freq_rose  = freq_t and freq_p and (
            (freq_t - freq_p) / freq_p >= FREQ_INCREASE_PCT
            or freq_t >= FREQ_ABSOLUTE_FLOOR
        )
        ctr_fell   = ctr_t  and ctr_p  and ctr_p  > 0 and (ctr_p  - ctr_t)  / ctr_p  >= CTR_DROP_PCT
        cpa_rose   = cpa_t  and cpa_p  and cpa_p  > 0 and (cpa_t  - cpa_p)  / cpa_p  >= CPA_RISE_PCT

        if freq_rose and ctr_fell and cpa_rose:
            flags.append({
                "ad_id":   ad_id,
                "ad_name": ad_name,
                "flag":    "creative_fatigue",
                "metrics": {
                    "frequency_trailing": round(freq_t, 2),
                    "frequency_prior":    round(freq_p, 2),
                    "ctr_trailing_pct":   round(ctr_t, 2),
                    "ctr_prior_pct":      round(ctr_p, 2),
                    "cpa_trailing":       round(cpa_t, 2),
                    "cpa_prior":          round(cpa_p, 2),
                    "spend_7d":           round(spend_trailing, 2),
                },
                "suggestion": (
                    f"Frequency {round(freq_p,1)}→{round(freq_t,1)}, "
                    f"CTR {round(ctr_p,2)}%→{round(ctr_t,2)}% (−{round((ctr_p-ctr_t)/ctr_p*100,0):.0f}%), "
                    f"CPA +{round((cpa_t-cpa_p)/cpa_p*100,0):.0f}%: pattern consistent with "
                    f"creative fatigue — consider testing fresh creatives against this ad."
                ),
            })
            continue  # skip audience fatigue check if creative already flagged

        # ── Audience fatigue: freq ↑, reach flat/declining, CPM ↑ ─────────
        freq_rose_any  = freq_t and freq_p and freq_t > freq_p
        reach_flat     = reach_t and reach_p and reach_t <= reach_p * 1.05
        cpm_rose       = cpm_t and cpm_p and cpm_p > 0 and (cpm_t - cpm_p) / cpm_p >= CPM_RISE_PCT

        if freq_rose_any and reach_flat and cpm_rose:
            flags.append({
                "ad_id":   ad_id,
                "ad_name": ad_name,
                "flag":    "audience_fatigue",
                "metrics": {
                    "frequency_trailing": round(freq_t, 2),
                    "frequency_prior":    round(freq_p, 2),
                    "reach_trailing":     round(reach_t, 0),
                    "reach_prior":        round(reach_p, 0),
                    "cpm_trailing":       round(cpm_t, 2),
                    "cpm_prior":          round(cpm_p, 2),
                    "spend_7d":           round(spend_trailing, 2),
                },
                "suggestion": (
                    f"Frequency rising ({round(freq_p,1)}→{round(freq_t,1)}), "
                    f"reach flat ({round(reach_p,0):.0f}→{round(reach_t,0):.0f}), "
                    f"CPM +{round((cpm_t-cpm_p)/cpm_p*100,0):.0f}%: pattern consistent with "
                    f"audience saturation — consider expanding audience or refreshing targeting."
                ),
            })

    return flags


# ── DB-backed wrapper ─────────────────────────────────────────────────────────

def fetch_fatigue_flags(brand_id: str, target_date: date, sb: Any) -> list[dict]:
    """
    Queries 14 days of ad_metrics_daily and runs fatigue detection.
    """
    window_start = target_date - timedelta(days=14)

    rows = (
        sb.table("ad_metrics_daily")
        .select("ad_id, ad_name, date, spend, impressions, clicks, reach, frequency, ctr, cpm, cpa, purchases")
        .eq("brand_id", brand_id)
        .gte("date", str(window_start))
        .lte("date", str(target_date))
        .execute()
    ).data

    metrics_by_ad: dict[str, list] = {}
    for row in rows:
        metrics_by_ad.setdefault(row["ad_id"], []).append(row)

    return detect_fatigue(metrics_by_ad)
