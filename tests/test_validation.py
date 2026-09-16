"""Dataset-level validation rules.

Each test breaks exactly one thing in the valid baseline and asserts the
matching rule fires. The two invariants the Stage 1 audit flagged as
unenforceable at row level — R020 and R021 — are covered explicitly.
"""

from __future__ import annotations

import pytest

from backend.app.services.validation import (
    DatasetValidationError,
    validate_dataset,
)


def rules(report) -> set[str]:
    return {issue.rule for issue in report.issues}


def test_valid_dataset_passes(frames):
    sales, customers = frames()
    report = validate_dataset(sales, customers)
    assert report.ok, report.summary()
    assert report.errors == []
    assert report.warnings == []


def test_valid_dataset_reports_stats(frames):
    sales, customers = frames()
    report = validate_dataset(sales, customers)
    assert report.stats["sales_rows"] == 6
    assert report.stats["customer_rows"] == 3
    assert report.stats["merchants"] == 1
    assert report.stats["products"] == 2
    assert report.stats["restock_events"] == 0


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------
def test_missing_required_column_fails(frames):
    sales, customers = frames()
    report = validate_dataset(sales.drop(columns=["revenue"]), customers)
    assert not report.ok
    assert "R001" in rules(report)
    assert "revenue" in report.errors[0].message


def test_missing_customer_column_fails(frames):
    sales, customers = frames()
    report = validate_dataset(sales, customers.drop(columns=["new_customers"]))
    assert not report.ok
    assert "R002" in rules(report)


def test_missing_value_fails(frames, sales_rows):
    sales_rows[2]["revenue"] = None
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R003" in rules(report)


def test_non_numeric_value_fails(frames, sales_rows):
    sales_rows[1]["orders"] = "not-a-number"
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R007" in rules(report)


def test_unparseable_date_fails(frames, sales_rows):
    sales_rows[0]["date"] = "01-01-2026"  # wrong format
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R005" in rules(report)


def test_duplicate_sales_key_fails(frames, sales_rows):
    sales_rows.append(dict(sales_rows[0]))
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R009" in rules(report)


def test_duplicate_customer_key_fails(frames, customer_rows):
    customer_rows.append(dict(customer_rows[0]))
    sales, customers = frames(customers=customer_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R010" in rules(report)


# --------------------------------------------------------------------------
# Ranges and row logic
# --------------------------------------------------------------------------
def test_negative_value_fails(frames, sales_rows):
    sales_rows[0]["revenue"] = -100.0
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R014" in rules(report)


def test_negative_customer_count_fails(frames, customer_rows):
    customer_rows[0]["repeat_customers"] = -1
    customer_rows[0]["new_customers"] = 7
    sales, customers = frames(customers=customer_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R015" in rules(report)


def test_orders_exceeding_units_fails(frames, sales_rows):
    sales_rows[0]["orders"] = 99
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R011" in rules(report)


def test_units_without_orders_fails(frames, sales_rows):
    sales_rows[0]["orders"] = 0
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R012" in rules(report)


def test_customer_split_mismatch_fails(frames, customer_rows):
    customer_rows[1]["repeat_customers"] = 99
    sales, customers = frames(customers=customer_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R013" in rules(report)


# --------------------------------------------------------------------------
# Revenue / profit consistency
# --------------------------------------------------------------------------
def test_units_sold_without_revenue_fails(frames, sales_rows):
    sales_rows[0]["revenue"] = 0.0
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R030" in rules(report)


def test_revenue_without_units_fails(frames, sales_rows):
    sales_rows[0]["units_sold"] = 0
    sales_rows[0]["orders"] = 0
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R031" in rules(report)


def test_unit_price_outlier_fails(frames, sales_rows):
    # Widget A sells at 100/unit on every other row; 10x that is corruption.
    sales_rows[4]["revenue"] = 7000.00
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R032" in rules(report)


def test_expenses_above_revenue_warns_but_does_not_block(frames, sales_rows):
    sales_rows[0]["expenses"] = 9999.00
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert "R033" in rules(report)
    assert report.warnings, "selling below cost should warn"
    assert report.ok, "a below-cost sale is possible in reality and must not block"


# --------------------------------------------------------------------------
# Cross-row invariants (Stage 1 audit gaps)
# --------------------------------------------------------------------------
def test_customers_exceeding_daily_orders_fails(frames, customer_rows):
    # Day 1 has 8 orders in total; 20 distinct customers is impossible.
    customer_rows[0]["customers"] = 20
    customer_rows[0]["new_customers"] = 20
    customer_rows[0]["repeat_customers"] = 0
    sales, customers = frames(customers=customer_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R020" in rules(report)


def test_customers_equal_to_daily_orders_passes(frames, customer_rows):
    customer_rows[0]["customers"] = 8  # exactly the day's order count
    customer_rows[0]["new_customers"] = 8
    customer_rows[0]["repeat_customers"] = 0
    sales, customers = frames(customers=customer_rows)
    assert validate_dataset(sales, customers).ok


def test_inventory_dropping_faster_than_sales_fails(frames, sales_rows):
    # Widget A: 44 closing on day 1, 5 units sold on day 2 -> 39 expected.
    # Recording 10 means stock vanished without being sold.
    sales_rows[2]["inventory"] = 10
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R021" in rules(report)


def test_inventory_rising_is_treated_as_restock(frames, sales_rows):
    sales_rows[2]["inventory"] = 239  # day 2: 39 + a 200-unit delivery
    sales_rows[4]["inventory"] = 232  # day 3 must continue from the new level (239 - 7)
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)
    assert report.ok, "a restock may raise closing stock"
    assert report.stats["restock_events"] == 1, "restocks must stay visible, not silently absorbed"


def test_first_row_of_product_has_no_continuity_check(frames, sales_rows):
    """A product's opening row has no predecessor, so it cannot violate
    continuity however large the opening stock is."""
    sales_rows[0]["inventory"] = 100000
    sales_rows[2]["inventory"] = 99995  # 100000 - 5 units
    sales_rows[4]["inventory"] = 99988  # 99995 - 7 units
    sales, customers = frames(sales_rows)
    assert validate_dataset(sales, customers).ok


# --------------------------------------------------------------------------
# Join completeness
# --------------------------------------------------------------------------
def test_sales_day_without_customer_row_fails(frames, customer_rows):
    sales, customers = frames(customers=customer_rows[:2])  # drop day 3
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R022" in rules(report)


def test_customer_day_without_sales_fails(frames, customer_rows):
    customer_rows.append(
        {"date": "2026-01-09", "merchant_id": "M001", "customers": 2,
         "new_customers": 2, "repeat_customers": 0}
    )
    sales, customers = frames(customers=customer_rows)
    report = validate_dataset(sales, customers)
    assert not report.ok
    assert "R023" in rules(report)


# --------------------------------------------------------------------------
# Reporting behaviour
# --------------------------------------------------------------------------
def test_report_raises_with_actionable_detail(frames, sales_rows):
    sales_rows[0]["orders"] = 99
    sales, customers = frames(sales_rows)
    report = validate_dataset(sales, customers)

    with pytest.raises(DatasetValidationError) as excinfo:
        report.raise_if_invalid()

    message = str(excinfo.value)
    assert "R011" in message
    assert "Widget A" in message, "the failure must name the offending rows"


def test_validation_never_mutates_input(frames, sales_rows):
    sales, customers = frames(sales_rows)
    before_sales = sales.copy(deep=True)
    before_customers = customers.copy(deep=True)

    validate_dataset(sales, customers)

    # Corrupt data must never be silently repaired on the way through.
    assert sales.equals(before_sales)
    assert customers.equals(before_customers)


def test_multiple_independent_failures_are_all_reported(frames, sales_rows, customer_rows):
    sales_rows[0]["orders"] = 99  # R011
    customer_rows[1]["repeat_customers"] = 99  # R013
    sales, customers = frames(sales_rows, customer_rows)
    report = validate_dataset(sales, customers)
    assert {"R011", "R013"} <= rules(report)
