"""Tests for RTO-adjusted contribution margin logic."""
import pytest
from logic.profit import calc_order_margin, calc_daily_summary, calc_product_margins

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


# ── calc_product_margins() ────────────────────────────────────────────────────

def test_product_margins_single_order_single_product():
    margins = [{"order_id": "o1", "gross_value": 500.0, "realized_value": 500.0,
                "contribution_margin": 200.0, "has_full_costs": True}]
    items = {"o1": [{"product_id": "prod_a", "quantity": 1, "unit_price": 500.0}]}
    result = calc_product_margins(margins, items)

    assert len(result) == 1
    assert result[0]["product_id"] == "prod_a"
    assert result[0]["units_sold"] == 1
    assert result[0]["realized_revenue"] == pytest.approx(500.0)
    assert result[0]["contribution_margin"] == pytest.approx(200.0)
    assert result[0]["costs_incomplete"] is False


def test_product_margins_proration_sums_to_order_cm():
    # Two products in one COD order.
    # prod_a: 600/1000 = 60% → realized=540, cm=300
    # prod_b: 400/1000 = 40% → realized=360, cm=200
    # Invariant: sum of product CMs == order CM (500)
    margins = [{"order_id": "o1", "gross_value": 1000.0, "realized_value": 900.0,
                "contribution_margin": 500.0, "has_full_costs": True}]
    items = {"o1": [
        {"product_id": "prod_a", "quantity": 1, "unit_price": 600.0},
        {"product_id": "prod_b", "quantity": 1, "unit_price": 400.0},
    ]}
    result = calc_product_margins(margins, items)
    by_id = {r["product_id"]: r for r in result}

    assert by_id["prod_a"]["realized_revenue"] == pytest.approx(540.0)
    assert by_id["prod_a"]["contribution_margin"] == pytest.approx(300.0)
    assert by_id["prod_b"]["realized_revenue"] == pytest.approx(360.0)
    assert by_id["prod_b"]["contribution_margin"] == pytest.approx(200.0)
    total_cm = sum(r["contribution_margin"] for r in result)
    assert total_cm == pytest.approx(500.0)


def test_product_margins_aggregates_across_orders():
    # Same product in two separate orders; units and margins must be summed.
    margins = [
        {"order_id": "o1", "gross_value": 500.0, "realized_value": 500.0,
         "contribution_margin": 200.0, "has_full_costs": True},
        {"order_id": "o2", "gross_value": 500.0, "realized_value": 450.0,
         "contribution_margin": 180.0, "has_full_costs": True},
    ]
    items = {
        "o1": [{"product_id": "prod_a", "quantity": 1, "unit_price": 500.0}],
        "o2": [{"product_id": "prod_a", "quantity": 2, "unit_price": 250.0}],
    }
    result = calc_product_margins(margins, items)

    assert len(result) == 1
    assert result[0]["units_sold"] == 3               # 1 + 2
    assert result[0]["realized_revenue"] == pytest.approx(950.0)   # 500 + 450
    assert result[0]["contribution_margin"] == pytest.approx(380.0) # 200 + 180


def test_product_margins_costs_incomplete_flag_propagates():
    # Product appears in two orders; one has full costs, one does not.
    # costs_incomplete must be True even if only one order lacks costs.
    margins = [
        {"order_id": "o1", "gross_value": 500.0, "realized_value": 500.0,
         "contribution_margin": 200.0, "has_full_costs": True},
        {"order_id": "o2", "gross_value": 500.0, "realized_value": 500.0,
         "contribution_margin": 500.0, "has_full_costs": False},
    ]
    items = {
        "o1": [{"product_id": "prod_a", "quantity": 1, "unit_price": 500.0}],
        "o2": [{"product_id": "prod_a", "quantity": 1, "unit_price": 500.0}],
    }
    result = calc_product_margins(margins, items)

    assert len(result) == 1
    assert result[0]["costs_incomplete"] is True
