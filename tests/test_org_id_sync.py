"""
Tests confirming that organization_id is propagated into every row written
by the sync functions and the daily brief, and that org_id=None writes NULL
without crashing.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from sync.run_sync import get_organization_id
from sync.shopify_sync import run_shopify_sync, run_shopify_products_sync
from sync.meta_sync import run_meta_sync
from logic.brief import run_brief

BRAND_ID = "aaaaaaaa-0000-0000-0000-000000000001"
ORG_ID   = "bbbbbbbb-0000-0000-0000-000000000002"
TARGET   = date(2026, 6, 15)
CREDS_SHOPIFY = {"admin_token": "test-token"}
CREDS_META    = {"access_token": "test-meta-token"}
DOMAIN   = "test.myshopify.com"
ACCOUNT  = "act_12345"

# ── Minimal raw fixtures ───────────────────────────────────────────────────────

RAW_ORDER = {
    "id": 9000000001,
    "payment_gateway": None,
    "payment_gateway_names": ["Razorpay"],
    "financial_status": "paid",
    "tags": "",
    "total_price": "999.00",
    "subtotal_price": "999.00",
    "created_at": "2026-06-15T10:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": "fulfilled",
    "landing_site": None,
    "note_attributes": [],
    "line_items": [
        {"product_id": 111111, "variant_id": 222222, "quantity": 1, "price": "999.00"},
    ],
}

RAW_PRODUCT = {
    "id": 111111,
    "title": "Test Product",
    "variants": [{"id": 222222, "price": "999.00"}],
}

RAW_META_ROW = {
    "ad_id": "ad_abc123",
    "ad_name": "Test Ad",
    "adset_id": "adset_001",
    "adset_name": "Test Adset",
    "campaign_id": "camp_001",
    "campaign_name": "Test Campaign",
    "date_start": "2026-06-15",
    "spend": "500.00",
    "impressions": "10000",
    "clicks": "120",
    "reach": "8000",
    "frequency": "1.25",
    "ctr": "1.2",
    "actions": [{"action_type": "purchase", "value": "5"}],
    "action_values": [{"action_type": "purchase", "value": "4500.00"}],
}


# ── Helper: build a per-table-capturing Supabase mock ─────────────────────────

def _make_sb():
    """
    Returns (sb, captured) where captured[table_name] is the list of rows
    passed to the most recent .upsert() call on that table.
    """
    captured: dict[str, list] = {}
    tables: dict[str, MagicMock] = {}

    def _table(name: str) -> MagicMock:
        if name not in tables:
            m = MagicMock()
            # Default: chained select().eq().execute().data = [] (variant map lookup)
            m.select.return_value.eq.return_value.execute.return_value.data = []

            def _upsert(rows, **kwargs):
                captured[name] = rows
                return MagicMock()

            m.upsert.side_effect = _upsert
            tables[name] = m
        return tables[name]

    sb = MagicMock()
    sb.table.side_effect = _table
    return sb, captured


# ── get_organization_id ────────────────────────────────────────────────────────

def test_get_org_id_returns_value():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "organization_id": ORG_ID
    }
    assert get_organization_id(BRAND_ID, sb) == ORG_ID


def test_get_org_id_returns_none_when_no_data():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = None
    assert get_organization_id(BRAND_ID, sb) is None


def test_get_org_id_returns_none_when_column_is_null():
    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "organization_id": None
    }
    assert get_organization_id(BRAND_ID, sb) is None


# ── run_shopify_sync ───────────────────────────────────────────────────────────

def test_shopify_sync_includes_org_id():
    sb, captured = _make_sb()
    with patch("sync.shopify_sync.fetch_raw_orders", return_value=[RAW_ORDER]):
        run_shopify_sync(BRAND_ID, CREDS_SHOPIFY, DOMAIN, TARGET, sb, org_id=ORG_ID)

    assert captured["orders"][0]["organization_id"] == ORG_ID
    assert captured["raw_shopify_orders"][0]["organization_id"] == ORG_ID
    assert captured["order_items"][0]["organization_id"] == ORG_ID


def test_shopify_sync_org_id_none_writes_null():
    sb, captured = _make_sb()
    with patch("sync.shopify_sync.fetch_raw_orders", return_value=[RAW_ORDER]):
        run_shopify_sync(BRAND_ID, CREDS_SHOPIFY, DOMAIN, TARGET, sb, org_id=None)

    assert captured["orders"][0]["organization_id"] is None
    assert captured["raw_shopify_orders"][0]["organization_id"] is None
    assert captured["order_items"][0]["organization_id"] is None


def test_shopify_sync_default_org_id_is_none():
    # Calling without org_id kwarg must not raise and must write organization_id=None
    sb, captured = _make_sb()
    with patch("sync.shopify_sync.fetch_raw_orders", return_value=[RAW_ORDER]):
        run_shopify_sync(BRAND_ID, CREDS_SHOPIFY, DOMAIN, TARGET, sb)

    assert captured["orders"][0]["organization_id"] is None


# ── run_shopify_products_sync ──────────────────────────────────────────────────

def test_shopify_products_sync_includes_org_id():
    sb, captured = _make_sb()
    with patch("sync.shopify_sync.fetch_raw_products", return_value=[RAW_PRODUCT]):
        run_shopify_products_sync(BRAND_ID, CREDS_SHOPIFY, DOMAIN, sb, org_id=ORG_ID)

    assert captured["raw_shopify_products"][0]["organization_id"] == ORG_ID


def test_shopify_products_sync_org_id_none_writes_null():
    sb, captured = _make_sb()
    with patch("sync.shopify_sync.fetch_raw_products", return_value=[RAW_PRODUCT]):
        run_shopify_products_sync(BRAND_ID, CREDS_SHOPIFY, DOMAIN, sb, org_id=None)

    assert captured["raw_shopify_products"][0]["organization_id"] is None


# ── run_meta_sync ──────────────────────────────────────────────────────────────

def test_meta_sync_includes_org_id():
    sb, captured = _make_sb()
    with patch("sync.meta_sync.fetch_raw_insights", return_value=[RAW_META_ROW]):
        run_meta_sync(BRAND_ID, CREDS_META, ACCOUNT, TARGET, sb, org_id=ORG_ID)

    assert captured["ad_metrics_daily"][0]["organization_id"] == ORG_ID
    assert captured["raw_meta_insights"][0]["organization_id"] == ORG_ID


def test_meta_sync_org_id_none_writes_null():
    sb, captured = _make_sb()
    with patch("sync.meta_sync.fetch_raw_insights", return_value=[RAW_META_ROW]):
        run_meta_sync(BRAND_ID, CREDS_META, ACCOUNT, TARGET, sb, org_id=None)

    assert captured["ad_metrics_daily"][0]["organization_id"] is None
    assert captured["raw_meta_insights"][0]["organization_id"] is None


def test_meta_sync_default_org_id_is_none():
    sb, captured = _make_sb()
    with patch("sync.meta_sync.fetch_raw_insights", return_value=[RAW_META_ROW]):
        run_meta_sync(BRAND_ID, CREDS_META, ACCOUNT, TARGET, sb)

    assert captured["ad_metrics_daily"][0]["organization_id"] is None


# ── Warning emitted in run_sync for None org_id ────────────────────────────────

def test_run_sync_warns_when_org_id_none(capsys):
    """
    run() should print a WARNING line when a brand has no organization_id.
    """
    from sync.run_sync import run

    # Minimal sb: one shopify connection, brand has no org_id
    sb = MagicMock()

    def _table(name: str) -> MagicMock:
        m = MagicMock()
        if name == "connections":
            m.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "brand_id": BRAND_ID,
                    "platform": "shopify",
                    "account_id": DOMAIN,
                    "credentials": CREDS_SHOPIFY,
                }
            ]
        elif name == "brands":
            # single() chain for get_organization_id — returns no org_id
            m.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
                "organization_id": None
            }
        else:
            m.select.return_value.eq.return_value.execute.return_value.data = []
            m.select.return_value.eq.return_value.neq.return_value.execute.return_value.data = []
        return m

    sb.table.side_effect = _table

    with patch("sync.run_sync.get_supabase", return_value=sb), \
         patch("sync.shopify_sync.fetch_raw_orders", return_value=[]), \
         patch("sync.shopify_sync.fetch_raw_products", return_value=[]):
        run(target_date=TARGET)

    out = capsys.readouterr().out
    assert "WARNING" in out
    assert BRAND_ID in out
    assert "organization_id" in out


# ── run_brief / daily_brief_log ────────────────────────────────────────────────

# Minimal profit dict satisfying compose_brief's field access
_PROFIT = {
    "order_count": 3,
    "total_gross": 3000.0,
    "platform_revenue": 2700.0,
    "realized_revenue": 2500.0,
    "total_spend": 500.0,
    "mer": 5.0,
    "total_cogs": 900.0,
    "contribution_margin": 1100.0,
    "net_profit": 600.0,
    "costs_incomplete": False,
    "product_margins": [],
}


def _make_brief_sb():
    """
    Returns (sb, captured_payload) pair.
    captured_payload[0] will be the dict passed to daily_brief_log.upsert
    after run_brief is called.
    """
    captured: list[dict] = []
    sb = MagicMock()

    def _table(name: str) -> MagicMock:
        m = MagicMock()
        if name == "daily_brief_log":
            def _upsert(payload, **kwargs):
                captured.append(payload)
                return MagicMock()
            m.upsert.side_effect = _upsert
        else:
            # ad_metrics_daily select chain
            m.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return m

    sb.table.side_effect = _table
    return sb, captured


def test_run_brief_includes_org_id():
    sb, captured = _make_brief_sb()
    with patch("logic.brief.fetch_daily_profit", return_value=_PROFIT), \
         patch("logic.brief.fetch_fatigue_flags", return_value=[]):
        run_brief(BRAND_ID, TARGET, sb, org_id=ORG_ID)

    assert len(captured) == 1
    assert captured[0]["organization_id"] == ORG_ID
    assert captured[0]["brand_id"] == BRAND_ID


def test_run_brief_org_id_none_writes_null():
    sb, captured = _make_brief_sb()
    with patch("logic.brief.fetch_daily_profit", return_value=_PROFIT), \
         patch("logic.brief.fetch_fatigue_flags", return_value=[]):
        run_brief(BRAND_ID, TARGET, sb, org_id=None)

    assert len(captured) == 1
    assert captured[0]["organization_id"] is None


def test_run_brief_default_org_id_is_none():
    sb, captured = _make_brief_sb()
    with patch("logic.brief.fetch_daily_profit", return_value=_PROFIT), \
         patch("logic.brief.fetch_fatigue_flags", return_value=[]):
        run_brief(BRAND_ID, TARGET, sb)

    assert len(captured) == 1
    assert captured[0]["organization_id"] is None
