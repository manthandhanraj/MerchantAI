"""Foundation smoke test: the documented schema actually validates real rows.

This is what makes the Stage 1 schema a contract rather than a description.
Stage 2's generated dataset must pass these same checks.
"""

import csv

import pytest

from backend.app.config import PROJECT_ROOT
from backend.app.models.schemas import (
    CUSTOMERS_COLUMNS,
    SALES_COLUMNS,
    CustomerDailyRecord,
    SalesRecord,
)

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"
SALES_SAMPLE = SAMPLE_DIR / "merchant_sales_sample.csv"
CUSTOMERS_SAMPLE = SAMPLE_DIR / "merchant_customers_daily_sample.csv"


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_sales_sample_matches_schema():
    rows = read_rows(SALES_SAMPLE)
    assert rows, "sales sample must not be empty"
    assert list(rows[0].keys()) == SALES_COLUMNS

    records = [SalesRecord(**row) for row in rows]

    # (date, merchant_id, product) is the declared grain, so it must be unique.
    keys = {(r.date, r.merchant_id, r.product) for r in records}
    assert len(keys) == len(records)


def test_customers_sample_matches_schema():
    rows = read_rows(CUSTOMERS_SAMPLE)
    assert rows, "customers sample must not be empty"
    assert list(rows[0].keys()) == CUSTOMERS_COLUMNS

    records = [CustomerDailyRecord(**row) for row in rows]

    keys = {(r.date, r.merchant_id) for r in records}
    assert len(keys) == len(records)


def test_samples_join_on_date_and_merchant():
    """The two files are joined on (date, merchant_id); every sales day needs
    a matching customer row or the customer insights would silently drop data."""
    sales_keys = {(r["date"], r["merchant_id"]) for r in read_rows(SALES_SAMPLE)}
    customer_keys = {(r["date"], r["merchant_id"]) for r in read_rows(CUSTOMERS_SAMPLE)}
    assert sales_keys == customer_keys


def test_customer_split_invariant_is_enforced():
    with pytest.raises(ValueError):
        CustomerDailyRecord(
            date="2026-09-01",
            merchant_id="M001",
            customers=50,
            new_customers=10,
            repeat_customers=10,  # 10 + 10 != 50
        )


def test_orders_cannot_exceed_units_sold():
    with pytest.raises(ValueError):
        SalesRecord(
            date="2026-09-01",
            merchant_id="M001",
            product="Phone Case",
            category="Accessories",
            orders=10,
            units_sold=5,
            revenue=1000.0,
            expenses=600.0,
            inventory=20,
        )
