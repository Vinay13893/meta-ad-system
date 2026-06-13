"""Tests for creative and audience fatigue detection."""
from logic.fatigue import detect_fatigue


def _make_rows(ad_id, ad_name, days):
    """
    days: list of dicts with overrides, index 0 = most recent.
    Fills sane defaults for unspecified fields.
    """
    rows = []
    for i, overrides in enumerate(days):
        row = {
            "ad_id": ad_id,
            "ad_name": ad_name,
            "date": f"2026-06-{12 - i:02d}",
            "spend": 300.0,
            "impressions": 10000,
            "clicks": 200,
            "reach": 9000,
            "frequency": 2.0,
            "ctr": 2.0,
            "cpm": 30.0,
            "cpa": 150.0,
            "purchases": 2.0,
        }
        row.update(overrides)
        rows.append(row)
    return rows


def test_creative_fatigue_detected():
    # trailing 7: high freq, low CTR, high CPA
    trailing = [{"frequency": 4.5, "ctr": 1.0, "cpa": 250.0, "spend": 300} for _ in range(7)]
    # prior 7: healthy metrics
    prior    = [{"frequency": 2.0, "ctr": 2.5, "cpa": 150.0, "spend": 300} for _ in range(7)]

    rows = _make_rows("ad_1", "Test Ad", trailing + prior)
    flags = detect_fatigue({"ad_1": rows})

    assert len(flags) == 1
    assert flags[0]["flag"] == "creative_fatigue"
    assert flags[0]["ad_id"] == "ad_1"


def test_no_flag_healthy_ad():
    rows = _make_rows("ad_2", "Healthy Ad", [
        {"frequency": 1.5, "ctr": 3.0, "cpa": 120.0} for _ in range(14)
    ])
    flags = detect_fatigue({"ad_2": rows})
    assert flags == []


def test_low_spend_ignored():
    # Even with bad metrics, ignore if spend is trivial
    trailing = [{"frequency": 5.0, "ctr": 0.5, "cpa": 500.0, "spend": 10} for _ in range(7)]
    prior    = [{"frequency": 2.0, "ctr": 2.5, "cpa": 150.0, "spend": 10} for _ in range(7)]
    rows = _make_rows("ad_3", "Low Spend Ad", trailing + prior)
    flags = detect_fatigue({"ad_3": rows})
    assert flags == []


def test_audience_fatigue_detected():
    # freq rising, reach flat, CPM rising — but CTR/CPA not bad enough for creative fatigue
    trailing = [{"frequency": 3.2, "ctr": 2.1, "cpa": 155.0, "reach": 8800, "cpm": 38.0, "spend": 300} for _ in range(7)]
    prior    = [{"frequency": 2.1, "ctr": 2.3, "cpa": 145.0, "reach": 9000, "cpm": 30.0, "spend": 300} for _ in range(7)]
    rows = _make_rows("ad_4", "Audience Fatigue Ad", trailing + prior)
    flags = detect_fatigue({"ad_4": rows})

    assert len(flags) == 1
    assert flags[0]["flag"] == "audience_fatigue"


def test_insufficient_data_no_flag():
    # Only 3 days of data — not enough for comparison
    rows = _make_rows("ad_5", "New Ad", [{"spend": 300} for _ in range(3)])
    flags = detect_fatigue({"ad_5": rows})
    assert flags == []
