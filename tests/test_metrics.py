"""Metric computations.

Expected values are hand-computed from the baseline fixture in conftest.py:

    day 1  revenue 750   orders  8  units  9  expenses 375  customers 6
    day 2  revenue 600   orders  6  units  7  expenses 300  customers 5
    day 3  revenue 900   orders 10  units 11  expenses 450  customers 8
    total  revenue 2250  orders 24  units 27  expenses 1125 customers 19
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.app.services import metrics as M
from backend.app.utils.calculations import growth_rate, safe_divide


# --------------------------------------------------------------------------
# safe_divide
# --------------------------------------------------------------------------
def test_safe_divide_scalars():
    assert safe_divide(10.0, 4.0) == 2.5
    assert safe_divide(10.0, 0.0) == 0.0
    assert safe_divide(0.0, 0.0) == 0.0


def test_safe_divide_series_by_scalar_broadcasts():
    """Regression: a Series divided by a scalar must broadcast. Wrapping the
    scalar in a Series index-aligns instead, zeroing every row but the first
    and silently breaking share-of-total columns."""
    result = safe_divide(pd.Series([10.0, 20.0, 70.0]), 100.0)
    assert list(result) == [0.1, 0.2, 0.7]


def test_safe_divide_series_by_zero_uses_default():
    assert list(safe_divide(pd.Series([1.0, 2.0]), 0.0)) == [0.0, 0.0]


def test_safe_divide_elementwise_zero():
    result = safe_divide(pd.Series([10.0, 20.0]), pd.Series([2.0, 0.0]))
    assert list(result) == [5.0, 0.0]


def test_safe_divide_never_returns_inf_or_nan():
    result = safe_divide(pd.Series([1.0, 2.0, 3.0]), pd.Series([0.0, 0.0, 1.0]))
    assert np.isfinite(result).all()


def test_growth_rate():
    assert growth_rate(150.0, 100.0) == 0.5
    assert growth_rate(50.0, 100.0) == -0.5
    assert growth_rate(100.0, 0.0) == 0.0, "no prior period means no measurable growth"


# --------------------------------------------------------------------------
# Daily metrics
# --------------------------------------------------------------------------
def test_daily_metrics_shape_and_order(dataset):
    daily = M.daily_metrics(dataset)
    assert len(daily) == 3
    assert list(daily["date"]) == sorted(daily["date"])


def test_daily_metrics_values(dataset):
    daily = M.daily_metrics(dataset)
    assert list(daily["revenue"]) == [750.0, 600.0, 900.0]
    assert list(daily["orders"]) == [8, 6, 10]
    assert list(daily["units_sold"]) == [9, 7, 11]
    assert list(daily["profit"]) == [375.0, 300.0, 450.0]
    assert list(daily["customers"]) == [6, 5, 8]


def test_daily_derived_metrics(dataset):
    daily = M.daily_metrics(dataset)
    assert daily["average_order_value"].iloc[0] == pytest.approx(750 / 8)
    assert daily["profit_margin"].iloc[0] == pytest.approx(0.5)
    assert daily["repeat_customer_rate"].iloc[0] == pytest.approx(0.0)
    assert daily["repeat_customer_rate"].iloc[2] == pytest.approx(5 / 8)
    assert daily["revenue_per_customer"].iloc[0] == pytest.approx(125.0)


def test_period_growth(dataset):
    # Only 3 days, so the window shrinks to 1: day 3 (900) vs day 2 (600).
    daily = M.daily_metrics(dataset)
    assert M.period_growth(daily, "revenue") == pytest.approx(0.5)


def test_period_growth_without_prior_period_is_zero():
    assert M.period_growth(pd.DataFrame(columns=["revenue"])) == 0.0


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
def test_summary_totals(dataset):
    summary = M.summary_metrics(dataset)
    assert summary["total_revenue"] == 2250.0
    assert summary["total_orders"] == 24
    assert summary["total_units_sold"] == 27
    assert summary["total_expenses"] == 1125.0
    assert summary["total_profit"] == 1125.0
    assert summary["profit_margin"] == pytest.approx(0.5)
    assert summary["average_order_value"] == pytest.approx(93.75)
    assert summary["days"] == 3
    assert summary["period_start"] == "2026-01-01"
    assert summary["period_end"] == "2026-01-03"


def test_summary_customer_metrics(dataset):
    summary = M.summary_metrics(dataset)
    assert summary["total_customers"] == 19
    assert summary["new_customers"] == 11
    assert summary["repeat_customers"] == 8
    assert summary["repeat_customer_rate"] == pytest.approx(8 / 19, abs=1e-4)


def test_summary_is_json_safe(dataset):
    """Every value must be a plain Python type so FastAPI can serialise it."""
    for key, value in M.summary_metrics(dataset).items():
        assert not isinstance(value, (np.integer, np.floating)), f"{key} is a numpy scalar"
        if isinstance(value, float):
            assert np.isfinite(value), f"{key} is not finite"


# --------------------------------------------------------------------------
# Product and category performance
# --------------------------------------------------------------------------
def test_product_performance(dataset):
    products = M.product_performance(dataset).set_index("product")
    assert products.loc["Widget A", "revenue"] == 1800.0
    assert products.loc["Widget A", "units_sold"] == 18
    assert products.loc["Widget A", "avg_unit_price"] == pytest.approx(100.0)
    assert products.loc["Widget B", "avg_unit_price"] == pytest.approx(50.0)
    assert products.loc["Widget A", "active_days"] == 3


def test_product_revenue_share_sums_to_one(dataset):
    products = M.product_performance(dataset)
    assert products["revenue_share"].sum() == pytest.approx(1.0)
    assert products.set_index("product").loc["Widget A", "revenue_share"] == pytest.approx(0.8)


def test_products_sorted_by_revenue(dataset):
    revenue = list(M.product_performance(dataset)["revenue"])
    assert revenue == sorted(revenue, reverse=True)


def test_category_performance(dataset):
    categories = M.category_performance(dataset).set_index("category")
    assert categories.loc["Tools", "revenue"] == 1800.0
    assert categories.loc["Parts", "revenue"] == 450.0
    assert categories.loc["Tools", "products"] == 1


def test_category_revenue_share_sums_to_one(dataset):
    assert M.category_performance(dataset)["revenue_share"].sum() == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def test_inventory_position_uses_latest_snapshot(dataset):
    position = M.inventory_position(dataset).set_index("product")
    assert position.loc["Widget A", "inventory"] == 32  # day 3 closing stock
    assert position.loc["Widget B", "inventory"] == 21
    assert position.loc["Widget A", "as_of_date"] == pd.Timestamp("2026-01-03")


def test_inventory_cover_and_status(dataset):
    position = M.inventory_position(dataset).set_index("product")
    # 18 units over a 7-day window = 2.571/day; 32 in stock = ~12.4 days cover.
    assert position.loc["Widget A", "avg_daily_units"] == pytest.approx(18 / 7)
    assert position.loc["Widget A", "days_of_inventory_cover"] == pytest.approx(32 / (18 / 7))
    assert position.loc["Widget A", "stock_status"] == "healthy"


def test_stock_status_thresholds():
    assert M._stock_status(0, 5.0) == "out_of_stock"
    assert M._stock_status(10, float("nan")) == "no_recent_sales"
    assert M._stock_status(10, 1.0) == "critical"
    assert M._stock_status(10, 5.0) == "low"
    assert M._stock_status(10, 30.0) == "healthy"


def test_inventory_movement_detects_restock(write_dataset, sales_rows):
    sales_rows[2]["inventory"] = 239  # day 2 delivery of 200
    sales_rows[4]["inventory"] = 232  # day 3 continues from the new level
    dataset = write_dataset(sales_rows)

    movement = M.inventory_movement(dataset)
    widget_a = movement[movement["product"] == "Widget A"].reset_index(drop=True)
    assert list(widget_a["restock_units"]) == [0, 200, 0]


def test_inventory_movement_has_no_restock_in_baseline(dataset):
    assert M.inventory_movement(dataset)["restock_units"].sum() == 0


# --------------------------------------------------------------------------
# Merchant directory
# --------------------------------------------------------------------------
def test_merchant_directory(dataset):
    entries = M.merchant_directory(dataset)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["merchant_id"] == "M001"
    assert entry["total_revenue"] == 2250.0
    assert entry["total_orders"] == 24
    assert entry["products"] == 2
    assert entry["first_date"] == "2026-01-01"


# --------------------------------------------------------------------------
# Filtering and empty behaviour
# --------------------------------------------------------------------------
def test_filter_by_date_range(dataset):
    from datetime import date

    narrowed = M.filter_dataset(dataset, start=date(2026, 1, 2), end=date(2026, 1, 2))
    assert M.summary_metrics(narrowed)["total_revenue"] == 600.0
    assert len(M.daily_metrics(narrowed)) == 1


def test_filter_by_merchant(dataset):
    assert M.summary_metrics(M.filter_dataset(dataset, "M001"))["total_revenue"] == 2250.0


def test_empty_selection_returns_zeros_not_errors(dataset):
    """A merchant with no data is an empty state, not a crash or a NaN."""
    empty = M.filter_dataset(dataset, "DOES-NOT-EXIST")

    summary = M.summary_metrics(empty)
    assert summary["total_revenue"] == 0.0
    assert summary["average_order_value"] == 0.0
    assert summary["days"] == 0

    assert M.daily_metrics(empty).empty
    assert M.product_performance(empty).empty
    assert M.category_performance(empty).empty
    assert M.inventory_position(empty).empty
    assert M.inventory_movement(empty).empty
    assert M.merchant_directory(empty) == []


def test_empty_frames_keep_their_columns(dataset):
    """Stage 3 renders these directly, so an empty result still needs columns."""
    empty = M.filter_dataset(dataset, "DOES-NOT-EXIST")
    assert "revenue" in M.daily_metrics(empty).columns
    assert "revenue_share" in M.product_performance(empty).columns
    assert "stock_status" in M.inventory_position(empty).columns
