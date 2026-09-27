"""Shared test fixtures.

The base fixtures describe a small, hand-checked, fully valid dataset. Rule
tests copy it and break exactly one thing, so a failure points at one rule
rather than at a pile of unrelated noise.

Dates are strings here on purpose: that is what `data_loader._read_csv`
produces, and validation runs before type normalisation.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services.data_loader import read_dataset

# Two products over three days for one merchant. Every documented invariant
# holds: inventory falls by exactly units_sold, orders <= units_sold,
# customers <= daily orders, and new + repeat == customers.
BASE_SALES: list[dict] = [
    {"date": "2026-01-01", "merchant_id": "M001", "product": "Widget A", "category": "Tools",
     "orders": 5, "units_sold": 6, "revenue": 600.00, "expenses": 300.00, "inventory": 44},
    {"date": "2026-01-01", "merchant_id": "M001", "product": "Widget B", "category": "Parts",
     "orders": 3, "units_sold": 3, "revenue": 150.00, "expenses": 75.00, "inventory": 27},
    {"date": "2026-01-02", "merchant_id": "M001", "product": "Widget A", "category": "Tools",
     "orders": 4, "units_sold": 5, "revenue": 500.00, "expenses": 250.00, "inventory": 39},
    {"date": "2026-01-02", "merchant_id": "M001", "product": "Widget B", "category": "Parts",
     "orders": 2, "units_sold": 2, "revenue": 100.00, "expenses": 50.00, "inventory": 25},
    {"date": "2026-01-03", "merchant_id": "M001", "product": "Widget A", "category": "Tools",
     "orders": 6, "units_sold": 7, "revenue": 700.00, "expenses": 350.00, "inventory": 32},
    {"date": "2026-01-03", "merchant_id": "M001", "product": "Widget B", "category": "Parts",
     "orders": 4, "units_sold": 4, "revenue": 200.00, "expenses": 100.00, "inventory": 21},
]

BASE_CUSTOMERS: list[dict] = [
    {"date": "2026-01-01", "merchant_id": "M001", "customers": 6, "new_customers": 6, "repeat_customers": 0},
    {"date": "2026-01-02", "merchant_id": "M001", "customers": 5, "new_customers": 2, "repeat_customers": 3},
    {"date": "2026-01-03", "merchant_id": "M001", "customers": 8, "new_customers": 3, "repeat_customers": 5},
]


@pytest.fixture
def sales_rows() -> list[dict]:
    return [dict(row) for row in BASE_SALES]


@pytest.fixture
def customer_rows() -> list[dict]:
    return [dict(row) for row in BASE_CUSTOMERS]


@pytest.fixture
def frames(sales_rows, customer_rows):
    """Build (sales, customers) DataFrames as the validator sees them."""

    def _build(sales: list[dict] | None = None, customers: list[dict] | None = None):
        return (
            pd.DataFrame(sales if sales is not None else sales_rows),
            pd.DataFrame(customers if customers is not None else customer_rows),
        )

    return _build


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def write_dataset(tmp_path, sales_rows, customer_rows):
    """Write rows to real CSVs and load them through the full pipeline.

    Returns the loaded `Dataset`, so loader and metric tests exercise the same
    read -> validate -> normalise path the API uses.
    """

    def _write(
        sales: list[dict] | None = None,
        customers: list[dict] | None = None,
        sales_columns: list[str] | None = None,
        customer_columns: list[str] | None = None,
        validate: bool = True,
    ):
        sales_path = tmp_path / "merchant_sales.csv"
        customers_path = tmp_path / "merchant_customers_daily.csv"
        _write_csv(sales_path, sales_columns or SALES_COLUMNS, sales if sales is not None else sales_rows)
        _write_csv(
            customers_path,
            customer_columns or CUSTOMERS_COLUMNS,
            customers if customers is not None else customer_rows,
        )
        return read_dataset(sales_path, customers_path, validate=validate)

    return _write


@pytest.fixture
def dataset(write_dataset):
    """The valid baseline dataset, loaded."""
    return write_dataset()


@pytest.fixture(autouse=True)
def _isolated_local_accounts(tmp_path, monkeypatch):
    """Point built-in accounts at a throwaway directory for every test.

    Without this, any test that reached a private route in built-in mode would
    create a real database and signing secret under data/local/ in the working
    tree. Each test gets its own empty store and a fresh secret.
    """
    from backend.app.config import settings
    from backend.app.services import local_auth

    monkeypatch.setattr(settings, "local_data_dir", str(tmp_path / "local-accounts"))
    monkeypatch.setattr(settings, "local_auth_secret", "")
    local_auth.reset_caches()
    yield
    local_auth.reset_caches()
