"""
Unit tests for Shopify connector payment detection and order parsing.
Fixtures are anonymized from real orders observed on sage-herbal.myshopify.com.
"""
from __future__ import annotations

from connectors.shopify import _is_cod, _derive_status, _extract_utm, raw_to_order_record
from sync.shopify_sync import _is_influencer_order

# ── Real-order fixtures (anonymized) ─────────────────────────────────────────

# GoKwik COD order: payment_gateway_names=["cash_on_delivery"], financial=pending
RAW_COD = {
    "id": 1000000000001,
    "payment_gateway": None,
    "payment_gateway_names": ["cash_on_delivery"],
    "financial_status": "pending",
    "tags": "COD, GoKwik",
    "total_price": "495.00",
    "subtotal_price": "495.00",
    "created_at": "2026-06-13T10:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": None,
    "line_items": [
        {"product_id": 8293419319610, "variant_id": 52143744778554,
         "quantity": 1, "price": "495.00"},
    ],
}

# GoKwik prepaid UPI order: payment_gateway_names=["Gokwik UPI"], financial=paid
RAW_PREPAID = {
    "id": 1000000000002,
    "payment_gateway": None,
    "payment_gateway_names": ["Gokwik UPI"],
    "financial_status": "paid",
    "tags": "GoKwik, PREPAID-DISCOUNT, UPI",
    "total_price": "1050.20",
    "subtotal_price": "1050.20",
    "created_at": "2026-06-12T10:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": "fulfilled",
    "line_items": [
        {"product_id": 8293420859706, "variant_id": 52103961051450,
         "quantity": 2, "price": "639.00"},
    ],
}

# Internal influencer/gifting order: manual gateway, "influencer" tag
RAW_INFLUENCER = {
    "id": 1000000000003,
    "payment_gateway": None,
    "payment_gateway_names": ["manual"],
    "financial_status": "paid",
    "tags": "influencer",
    "total_price": "1134.00",
    "subtotal_price": "1134.00",
    "created_at": "2026-06-12T09:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": None,
    "line_items": [
        {"product_id": 8293420794170, "variant_id": 52143722398010,
         "quantity": 1, "price": "495.00"},
    ],
}


# ── _is_cod() ─────────────────────────────────────────────────────────────────

def test_cod_detected_from_gateway_names():
    assert _is_cod(["cash_on_delivery"]) is True

def test_cod_case_insensitive():
    assert _is_cod(["Cash_On_Delivery"]) is True

def test_prepaid_upi_not_cod():
    assert _is_cod(["Gokwik UPI"]) is False

def test_manual_not_cod():
    # "manual" = influencer order, not COD
    assert _is_cod(["manual"]) is False

def test_empty_gateway_names_not_cod():
    assert _is_cod([]) is False

def test_none_gateway_names_not_cod():
    assert _is_cod(None) is False


# ── raw_to_order_record() ─────────────────────────────────────────────────────

def test_cod_order_parsed_correctly():
    rec = raw_to_order_record(RAW_COD)
    assert rec.payment_method == "cod"
    assert rec.gross_value == 495.0
    assert rec.status == "confirmed"
    assert len(rec.items) == 1
    assert rec.items[0]["product_id"] == "8293419319610"

def test_prepaid_order_parsed_correctly():
    rec = raw_to_order_record(RAW_PREPAID)
    assert rec.payment_method == "prepaid"
    assert rec.gross_value == 1050.20
    assert rec.status == "delivered"
    assert rec.items[0]["quantity"] == 2

def test_influencer_order_payment_method_is_prepaid():
    # Influencer orders are manual/prepaid in payment terms —
    # the influencer filter (_is_influencer_order) is what excludes them,
    # not the payment method classifier.
    rec = raw_to_order_record(RAW_INFLUENCER)
    assert rec.payment_method == "prepaid"


# ── _is_influencer_order() ───────────────────────────────────────────────────

def test_influencer_tag_detected():
    assert _is_influencer_order(RAW_INFLUENCER) is True

def test_influencer_tag_case_insensitive():
    assert _is_influencer_order({"tags": "Influencer, other"}) is True

def test_real_cod_order_not_influencer():
    assert _is_influencer_order(RAW_COD) is False

def test_real_prepaid_order_not_influencer():
    assert _is_influencer_order(RAW_PREPAID) is False

def test_no_tags_not_influencer():
    assert _is_influencer_order({"tags": None}) is False


# ── _derive_status() RTO detection ───────────────────────────────────────────

def test_rto_tag_maps_to_rto_status():
    order = {"cancelled_at": None, "tags": "rto", "fulfillment_status": None, "financial_status": "pending"}
    assert _derive_status(order) == "rto"

def test_rto_tag_case_insensitive():
    order = {"cancelled_at": None, "tags": "RTO, GoKwik", "fulfillment_status": None, "financial_status": "pending"}
    assert _derive_status(order) == "rto"

def test_cancelled_takes_priority_over_rto_tag():
    # If cancelled_at is set, always return 'cancelled' regardless of tags
    order = {"cancelled_at": "2026-06-13T10:00:00Z", "tags": "rto", "fulfillment_status": None, "financial_status": "pending"}
    assert _derive_status(order) == "cancelled"

def test_fulfilled_paid_is_delivered():
    order = {"cancelled_at": None, "tags": "", "fulfillment_status": "fulfilled", "financial_status": "paid"}
    assert _derive_status(order) == "delivered"

def test_unfulfilled_pending_is_confirmed():
    order = {"cancelled_at": None, "tags": "", "fulfillment_status": None, "financial_status": "pending"}
    assert _derive_status(order) == "confirmed"


# ── _extract_utm() ────────────────────────────────────────────────────────────

# Anonymized fixture: Meta-attributed COD order via GoKwik with UTMs in
# note_attributes (the landing_site field is null in GoKwik orders).
RAW_META_ATTRIBUTED = {
    "id": 1000000000010,
    "payment_gateway": None,
    "payment_gateway_names": ["cash_on_delivery"],
    "financial_status": "pending",
    "tags": "GoKwik",
    "total_price": "495.00",
    "subtotal_price": "495.00",
    "created_at": "2026-06-13T11:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": None,
    "landing_site": None,
    "note_attributes": [
        {"name": "utm_source",  "value": "fb"},
        {"name": "utm_medium",  "value": "cpc"},
        {"name": "utm_campaign","value": "Website_Traffic"},
        {"name": "utm_term",    "value": "120215998064080350"},  # adset_id
        {"name": "utm_content", "value": "Kesar Chandan Scrub"},
    ],
    "line_items": [
        {"product_id": 8293419319610, "variant_id": 52143744778554,
         "quantity": 1, "price": "495.00"},
    ],
}

# Order with UTMs in landing_site URL (standard Shopify checkout path)
RAW_LANDING_SITE_UTM = {
    "id": 1000000000011,
    "payment_gateway_names": ["Razorpay"],
    "financial_status": "paid",
    "tags": "",
    "total_price": "799.00",
    "subtotal_price": "799.00",
    "created_at": "2026-06-13T12:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": "fulfilled",
    "landing_site": "/?utm_source=fb&utm_medium=cpc&utm_term=120215998064080350&utm_content=Kesar+Chandan+Scrub",
    "note_attributes": [],
    "line_items": [
        {"product_id": 8293419319610, "variant_id": 52143744778554,
         "quantity": 1, "price": "799.00"},
    ],
}

# Order with no UTM data at all (direct/organic)
RAW_NO_UTM = {
    "id": 1000000000012,
    "payment_gateway_names": ["Gokwik UPI"],
    "financial_status": "paid",
    "tags": "GoKwik",
    "total_price": "495.00",
    "subtotal_price": "495.00",
    "created_at": "2026-06-13T13:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": "fulfilled",
    "landing_site": None,
    "note_attributes": [],
    "line_items": [
        {"product_id": 8293419319610, "variant_id": 52143744778554,
         "quantity": 1, "price": "495.00"},
    ],
}

# Order with UTMs from a non-Meta source (email campaign — utm_source != fb)
RAW_EMAIL_UTM = {
    "id": 1000000000013,
    "payment_gateway_names": ["Gokwik UPI"],
    "financial_status": "paid",
    "tags": "",
    "total_price": "639.00",
    "subtotal_price": "639.00",
    "created_at": "2026-06-13T14:00:00+05:30",
    "cancelled_at": None,
    "fulfillment_status": "fulfilled",
    "landing_site": "/?utm_source=klaviyo&utm_medium=email&utm_term=some_list&utm_content=june_sale",
    "note_attributes": [],
    "line_items": [
        {"product_id": 8293419319610, "variant_id": 52143744778554,
         "quantity": 1, "price": "639.00"},
    ],
}


def test_utm_from_note_attributes_fb_source():
    adset_id, ad_name = _extract_utm(RAW_META_ATTRIBUTED)
    assert adset_id == "120215998064080350"
    assert ad_name == "Kesar Chandan Scrub"

def test_utm_from_landing_site_url():
    adset_id, ad_name = _extract_utm(RAW_LANDING_SITE_UTM)
    assert adset_id == "120215998064080350"
    assert ad_name == "Kesar Chandan Scrub"

def test_no_utm_returns_none():
    adset_id, ad_name = _extract_utm(RAW_NO_UTM)
    assert adset_id is None
    assert ad_name is None

def test_non_fb_source_returns_none():
    # utm_source=klaviyo — not a Meta click, both fields must be None
    adset_id, ad_name = _extract_utm(RAW_EMAIL_UTM)
    assert adset_id is None
    assert ad_name is None

def test_order_record_carries_utm_fields():
    # Full round-trip: raw_to_order_record should populate both fields
    rec = raw_to_order_record(RAW_META_ATTRIBUTED)
    assert rec.meta_adset_id == "120215998064080350"
    assert rec.meta_ad_name == "Kesar Chandan Scrub"

def test_order_record_utm_none_when_no_data():
    rec = raw_to_order_record(RAW_NO_UTM)
    assert rec.meta_adset_id is None
    assert rec.meta_ad_name is None
