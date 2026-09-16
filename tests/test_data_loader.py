"""Loading, normalising and caching the dataset."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from backend.app.services import data_loader
from backend.app.services.data_loader import (
    DatasetNotFoundError,
    get_dataset,
    read_dataset,
)
from backend.app.services.validation import DatasetValidationError


def test_valid_dataset_loads(dataset):
    assert len(dataset.sales) == 6
    assert len(dataset.customers) == 3
    assert dataset.validation.ok


def test_types_are_normalised(dataset):
    assert pd.api.types.is_datetime64_any_dtype(dataset.sales["date"])
    assert pd.api.types.is_datetime64_any_dtype(dataset.customers["date"])
    for column in ("orders", "units_sold", "inventory"):
        assert dataset.sales[column].dtype == "int64"
    for column in ("revenue", "expenses"):
        assert dataset.sales[column].dtype == "float64"
    for column in ("customers", "new_customers", "repeat_customers"):
        assert dataset.customers[column].dtype == "int64"


def test_rows_are_sorted_canonically(dataset):
    keys = list(zip(dataset.sales["date"], dataset.sales["merchant_id"], dataset.sales["product"]))
    assert keys == sorted(keys)


def test_column_order_matches_schema(dataset):
    from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS

    assert list(dataset.sales.columns) == SALES_COLUMNS
    assert list(dataset.customers.columns) == CUSTOMERS_COLUMNS


def test_missing_file_raises_with_instructions(tmp_path):
    with pytest.raises(DatasetNotFoundError) as excinfo:
        read_dataset(tmp_path / "nope.csv", tmp_path / "also-nope.csv")
    assert "generate_dataset.py" in str(excinfo.value), "the error must say how to fix it"


def test_invalid_dataset_raises(write_dataset, sales_rows):
    sales_rows[0]["orders"] = 99  # orders > units_sold
    with pytest.raises(DatasetValidationError):
        write_dataset(sales_rows)


def test_validation_can_be_bypassed_but_still_reports(write_dataset, sales_rows):
    """`validate=False` is for inspecting a broken file, not for trusting it:
    the report still carries the errors."""
    sales_rows[0]["orders"] = 99
    dataset = write_dataset(sales_rows, validate=False)
    assert not dataset.validation.ok
    assert any(issue.rule == "R011" for issue in dataset.validation.errors)


def test_corrupt_value_survives_read_to_be_reported(write_dataset, sales_rows):
    """Types are normalised only after validation, so a non-numeric value is
    reported rather than silently coerced to NaN."""
    sales_rows[0]["orders"] = "abc"
    with pytest.raises(DatasetValidationError) as excinfo:
        write_dataset(sales_rows)
    assert "R007" in str(excinfo.value)


def test_dataset_helpers(dataset):
    assert dataset.merchant_ids == ["M001"]
    start, end = dataset.date_range
    assert start.isoformat() == "2026-01-01"
    assert end.isoformat() == "2026-01-03"
    assert not dataset.is_empty()


def test_empty_dataset_is_detected(dataset):
    from backend.app.services.metrics import filter_dataset

    assert len(filter_dataset(dataset, "M001").sales) == 6
    empty = filter_dataset(dataset, "NOPE")
    assert empty.is_empty()
    assert empty.customers.empty


# --------------------------------------------------------------------------
# Caching
# --------------------------------------------------------------------------
@pytest.fixture
def pointed_at_tmp(tmp_path, monkeypatch, sales_rows, customer_rows):
    """Point the loader's settings at a temporary dataset."""
    from tests.conftest import _write_csv
    from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS

    sales_path = tmp_path / "s.csv"
    customers_path = tmp_path / "c.csv"
    _write_csv(sales_path, SALES_COLUMNS, sales_rows)
    _write_csv(customers_path, CUSTOMERS_COLUMNS, customer_rows)

    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=sales_path, customers_path=customers_path),
    )
    data_loader.clear_cache()
    yield sales_path, customers_path
    data_loader.clear_cache()


def test_dataset_is_cached(pointed_at_tmp):
    assert get_dataset() is get_dataset(), "the dataset should load once per process"


def test_force_reload_rereads(pointed_at_tmp):
    first = get_dataset()
    assert get_dataset(force_reload=True) is not first


def test_clear_cache_forces_reload(pointed_at_tmp):
    first = get_dataset()
    data_loader.clear_cache()
    assert get_dataset() is not first


# --------------------------------------------------------------------------
# The real generated dataset
# --------------------------------------------------------------------------
def test_generated_dataset_loads_and_validates():
    """The committed dataset must pass the pipeline it ships with."""
    from backend.app.config import settings

    if not (settings.sales_path.exists() and settings.customers_path.exists()):
        pytest.skip("dataset not generated; run python data/generate_dataset.py")

    dataset = read_dataset(settings.sales_path, settings.customers_path)
    assert dataset.validation.ok, dataset.validation.summary()
    assert len(dataset.sales) > 1000
    assert len(dataset.merchant_ids) >= 2
