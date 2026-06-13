"""Tests for RTO-adjusted contribution margin logic."""
import pytest
from logic.profit import calc_order_margin, calc_daily_summary

COSTS = {
    "prod_a": {
        "cogs": 150.0,
        "shipping_cost": 60.0,
        "packaging_cost": 20.0,
        "cod_rto_rate": 0.30,
        "reverse_ship_cost": 80.0,
    }
}


def test_prepaid_order_full_realization():
    order = {"order_id": "o1", "gross_value": 999.0, "payment_method": "prepaid", "status": "confirmed"}
    items = [{"product_id": "prod_a", "quantity": 1, "unit_price": 999.0}]
    result = calc_order_margin(order, items, COSTS)

    assert result["realized_value"] == 999.0
    assert result["rto_cost"] == 0.0
    assert result["cogs"] == 150.0
    assert result["contribution_margin"] == pytest.approx(999 - 150 - 60 - 20, 0.01)
    assert result["has_full_costs"] is True


def test_cod_order_rto_deduction():
    order = {"order_id": "o2", "gross_value": 999.0, "payment_method": "cod", "status": "confirmed"}
    items = [{"product_id": "prod_a", "quantity": 1, "unit_price": 999.0}]
    result = calc_order_margin(order, items, COSTS)

    # realized = 999 * (1 - 0.30) = 699.30
    assert result["realized_value"] == pytest.approx(699.30, 0.01)
    # rto_cost = 0.30 * 80 = 24
    assert result["rto_cost"] == pytest.approx(24.0, 0.01)
    # cm = 699.30 - 150 - 60 - 20 - 24 = 445.30
    assert result["contribution_margin"] == pytest.approx(445.30, 0.01)


def test_missing_costs_flagged():
    order = {"order_id": "o3", "gross_value": 500.0, "payment_method": "prepaid", "status": "confirmed"}
    items = [{"product_id": "prod_unknown", "quantity": 1, "unit_price": 500.0}]
    result = calc_order_margin(order, items, {})

    assert result["has_full_costs"] is False
    assert result["realized_value"] == 500.0
    # CM = gross - 0 costs = 500 (no cost data)
    assert result["contribution_margin"] == 500.0


def test_daily_summary_mer():
    margins = [
        {"order_id": "o1", "gross_value": 1000, "realized_value": 1000,
         "cogs": 200, "shipping": 60, "packaging": 20, "rto_cost": 0,
         "contribution_margin": 720, "has_full_costs": True, "payment_method": "prepaid", "status": "confirmed"},
    ]
    ad_rows = [{"spend": 500, "revenue_rep": 900}]
    summary = calc_daily_summary(margins, ad_rows)

    assert summary["total_spend"] == 500
    assert summary["realized_revenue"] == 1000
    assert summary["mer"] == pytest.approx(2.0, 0.01)
    assert summary["net_profit"] == pytest.approx(720 - 500, 0.01)


def test_zero_spend_mer_is_none():
    margins = [{"order_id": "o1", "gross_value": 500, "realized_value": 500,
                "cogs": 0, "shipping": 0, "packaging": 0, "rto_cost": 0,
                "contribution_margin": 500, "has_full_costs": True,
                "payment_method": "prepaid", "status": "confirmed"}]
    summary = calc_daily_summary(margins, [])
    assert summary["mer"] is None
