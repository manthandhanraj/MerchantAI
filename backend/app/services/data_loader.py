"""Dataset loading, validation and caching.

This is the single entry point to MerchantAI's data. Every later stage reads
through `get_dataset()` — nothing else opens a CSV. That is what keeps one
definition of "the data" across the dashboard, the insights, the forecast and
the assistant.

Order of operations matters:

    read (types left raw) -> validate -> normalise types -> cache

Validating before normalising is deliberate. If we coerced types on read,
`pd.to_numeric` would quietly turn a corrupted `"abc"` into `NaN` and the
validator would never see it. Reading raw means bad values survive long enough
to be reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from backend.app.config import settings
from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services.validation import ValidationReport, validate_dataset

# Columns that stay textual through both read and normalisation.
_TEXT_COLUMNS = ["date", "merchant_id", "product", "category"]

_SALES_INT = ["orders", "units_sold", "inventory"]
_SALES_FLOAT = ["revenue", "expenses"]
_CUSTOMER_INT = ["customers", "new_customers", "repeat_customers"]


class DatasetNotFoundError(FileNotFoundError):
    """Raised when a dataset CSV is missing, with instructions to generate it."""


@dataclass(frozen=True)
class Dataset:
    """The validated, type-normalised dataset.

    `sales` is one row per (date, merchant_id, product).
    `customers` is one row per (date, merchant_id).
    Both carry real `datetime64` dates.
    """

    sales: pd.DataFrame
    customers: pd.DataFrame
    validation: ValidationReport

    @property
    def merchant_ids(self) -> list[str]:
        return sorted(self.sales["merchant_id"].unique().tolist())

    @property
    def date_range(self) -> tuple[date, date]:
        return self.sales["date"].min().date(), self.sales["date"].max().date()

    def is_empty(self) -> bool:
        return self.sales.empty


def _read_csv(path: Path, label: str) -> pd.DataFrame:
    """Read a CSV leaving numeric types to pandas' own inference, so corrupted
    values stay visible to the validator instead of being coerced away."""
    if not path.exists():
        raise DatasetNotFoundError(
            f"{label} dataset not found at {path}.\n"
            "Generate it from the project root with:\n"
            "    python data/generate_dataset.py"
        )
    return pd.read_csv(path, dtype={c: "string" for c in _TEXT_COLUMNS})


def _normalise_sales(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    for column in _SALES_INT:
        out[column] = out[column].astype("int64")
    for column in _SALES_FLOAT:
        out[column] = out[column].astype("float64")
    for column in ("merchant_id", "product", "category"):
        out[column] = out[column].astype("string")
    return out[SALES_COLUMNS].sort_values(["date", "merchant_id", "product"]).reset_index(drop=True)


def _normalise_customers(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d")
    for column in _CUSTOMER_INT:
        out[column] = out[column].astype("int64")
    out["merchant_id"] = out["merchant_id"].astype("string")
    return out[CUSTOMERS_COLUMNS].sort_values(["date", "merchant_id"]).reset_index(drop=True)


def dataset_from_frames(
    raw_sales: pd.DataFrame,
    raw_customers: pd.DataFrame,
    validate: bool = True,
) -> Dataset:
    """Validate and normalise two raw frames into a `Dataset`.

    This is the single place a `Dataset` is constructed, whichever source the
    rows came from: the committed synthetic CSVs, or a merchant's own uploaded
    files. Everything downstream — metrics, analysis, recommendations, the
    action plan, the forecast and the assistant — therefore behaves identically
    for demo and private data, because it cannot tell them apart.

    Both frames must already carry the canonical columns, dates as YYYY-MM-DD
    strings and values as text or numbers. Nothing is repaired here.
    """
    report = validate_dataset(raw_sales, raw_customers)
    if validate:
        report.raise_if_invalid()

    return Dataset(
        sales=_normalise_sales(raw_sales),
        customers=_normalise_customers(raw_customers),
        validation=report,
    )


def read_dataset(
    sales_path: Path,
    customers_path: Path,
    validate: bool = True,
) -> Dataset:
    """Read, validate and normalise a dataset from explicit paths. Uncached.

    Raises `DatasetNotFoundError` if a file is missing and
    `DatasetValidationError` if validation finds errors. Nothing is repaired.
    """
    return dataset_from_frames(
        _read_csv(sales_path, "sales"),
        _read_csv(customers_path, "customers"),
        validate=validate,
    )


# Module-level cache. The dataset is small, read-only and identical for every
# request, so loading it once per process is the whole reason no database is needed.
_cache: Dataset | None = None


def get_dataset(force_reload: bool = False) -> Dataset:
    """Return the cached dataset, loading it on first use.

    Paths come from configuration, so they can be pointed elsewhere in tests
    or deployment without touching this module.
    """
    global _cache
    if _cache is None or force_reload:
        _cache = read_dataset(settings.sales_path, settings.customers_path)
    return _cache


def clear_cache() -> None:
    """Drop the cached dataset. Used by tests that swap the underlying files."""
    global _cache
    _cache = None
