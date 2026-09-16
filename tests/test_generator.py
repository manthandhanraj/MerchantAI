"""Synthetic dataset generation.

The generator is only useful if it is reproducible and if what it produces
passes the same pipeline the app runs. Both are asserted here, along with the
business patterns Stages 4-6 are being built to find.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services.data_loader import read_dataset
from backend.app.services.validation import validate_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_generator():
    """`data/` is not a package, so load the script by path.

    The module has to be registered in `sys.modules` before it executes:
    `@dataclass` resolves type hints via `sys.modules[cls.__module__]`, which
    is still missing during `exec_module`.
    """
    spec = importlib.util.spec_from_file_location(
        "generate_dataset", PROJECT_ROOT / "data" / "generate_dataset.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generator = _load_generator()


@pytest.fixture(scope="module")
def generated():
    """A small deterministic dataset, shared across tests in this module."""
    return generator.build_dataset(days=40, seed=42, end_date=date(2026, 6, 30))


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_same_seed_produces_identical_output():
    first = generator.build_dataset(days=30, seed=42, end_date=date(2026, 6, 30))
    second = generator.build_dataset(days=30, seed=42, end_date=date(2026, 6, 30))
    assert first == second


def test_different_seed_produces_different_output():
    first = generator.build_dataset(days=30, seed=42, end_date=date(2026, 6, 30))
    second = generator.build_dataset(days=30, seed=7, end_date=date(2026, 6, 30))
    assert first != second


def test_end_date_is_fixed_not_today():
    """A moving window would change the output every day and break
    reproducibility, so the default end date is a constant."""
    assert isinstance(generator.DEFAULT_END_DATE, date)
    assert generator.DEFAULT_END_DATE != date.today()


# --------------------------------------------------------------------------
# Shape and schema
# --------------------------------------------------------------------------
def test_output_matches_schema_columns(generated):
    sales, customers = generated
    assert list(sales[0].keys()) == SALES_COLUMNS
    assert list(customers[0].keys()) == CUSTOMERS_COLUMNS


def test_rows_pass_row_level_validation(generated):
    sales, customers = generated
    generator.validate_rows(sales, customers)  # raises on any bad row

    # Prove the check is doing work: a corrupted row must be rejected. Without
    # this, the test would still pass if validate_rows became a no-op.
    corrupted = [dict(row) for row in sales]
    corrupted[0]["orders"] = int(corrupted[0]["units_sold"]) + 10
    with pytest.raises(ValueError):
        generator.validate_rows(corrupted, customers)


def test_generated_data_passes_dataset_validation(generated):
    sales, customers = generated
    report = validate_dataset(pd.DataFrame(sales), pd.DataFrame(customers))
    assert report.ok, report.summary()


def test_day_count_is_respected(generated):
    sales, _ = generated
    assert len({row["date"] for row in sales}) == 40


def test_all_merchants_are_present(generated):
    sales, _ = generated
    assert {row["merchant_id"] for row in sales} == {m.merchant_id for m in generator.MERCHANTS}


def test_rows_are_canonically_sorted(generated):
    sales, customers = generated
    sales_keys = [(r["date"], r["merchant_id"], r["product"]) for r in sales]
    assert sales_keys == sorted(sales_keys)
    customer_keys = [(r["date"], r["merchant_id"]) for r in customers]
    assert customer_keys == sorted(customer_keys)


def test_too_few_days_is_rejected():
    with pytest.raises(ValueError):
        generator.build_dataset(days=1)


# --------------------------------------------------------------------------
# Data realism
# --------------------------------------------------------------------------
def test_data_is_not_perfectly_linear(generated):
    """Guard against the dataset degenerating into a smooth synthetic ramp."""
    sales, _ = generated
    frame = pd.DataFrame(sales)
    frame["revenue"] = frame["revenue"].astype(float)
    daily = frame.groupby("date")["revenue"].sum()
    day_over_day = daily.diff().dropna()
    assert (day_over_day > 0).any() and (day_over_day < 0).any(), "revenue should rise and fall"
    assert daily.std() > 0


def test_weekend_uplift_exists(generated):
    """Every merchant profile defines a weekend lift; it should be measurable."""
    sales, _ = generated
    frame = pd.DataFrame(sales)
    frame["revenue"] = frame["revenue"].astype(float)
    frame["date"] = pd.to_datetime(frame["date"])
    daily = frame.groupby("date")["revenue"].sum().to_frame()
    weekend = daily[daily.index.dayofweek >= 5]["revenue"].mean()
    weekday = daily[daily.index.dayofweek < 5]["revenue"].mean()
    assert weekend > weekday


def test_declining_and_growing_merchants_behave_as_designed():
    """The demo narrative depends on M003 declining and M001 growing. If this
    breaks, Stages 4-6 lose the patterns they are built to surface."""
    sales, _ = generator.build_dataset(days=180, seed=42, end_date=date(2026, 9, 15))
    frame = pd.DataFrame(sales)
    frame["revenue"] = frame["revenue"].astype(float)
    frame["date"] = pd.to_datetime(frame["date"])

    def trend(merchant_id: str) -> float:
        daily = frame[frame["merchant_id"] == merchant_id].groupby("date")["revenue"].sum()
        return daily.tail(30).mean() / daily.head(30).mean() - 1

    assert trend("M003") < -0.1, "M003 is the declining-merchant demo case"
    assert trend("M001") > 0.1, "M001 is the growing-merchant demo case"


def test_restocks_occur(generated):
    sales, customers = generated
    report = validate_dataset(pd.DataFrame(sales), pd.DataFrame(customers))
    assert report.stats["restock_events"] > 0, "inventory should actually move"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def test_cli_writes_loadable_files(tmp_path):
    exit_code = generator.main(["--days", "20", "--seed", "3", "--out-dir", str(tmp_path)])
    assert exit_code == 0

    sales_path = tmp_path / "merchant_sales.csv"
    customers_path = tmp_path / "merchant_customers_daily.csv"
    assert sales_path.exists() and customers_path.exists()

    dataset = read_dataset(sales_path, customers_path)
    assert dataset.validation.ok
    assert len(dataset.sales) > 0


def test_cli_output_is_byte_identical_across_runs(tmp_path):
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    generator.main(["--days", "15", "--seed", "11", "--out-dir", str(first_dir)])
    generator.main(["--days", "15", "--seed", "11", "--out-dir", str(second_dir)])

    for name in ("merchant_sales.csv", "merchant_customers_daily.csv"):
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
