"""Stage 2 API endpoints.

The dataset is swapped for the small fixture so assertions are exact and the
tests do not depend on the committed CSVs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services import data_loader
from tests.conftest import _write_csv

client = TestClient(app)


@pytest.fixture
def api_dataset(tmp_path, monkeypatch, sales_rows, customer_rows):
    """Point the API's loader at the fixture dataset."""
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
    yield
    data_loader.clear_cache()


@pytest.fixture
def no_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()
    yield
    data_loader.clear_cache()


# --------------------------------------------------------------------------
# /api/merchants
# --------------------------------------------------------------------------
def test_merchants_endpoint(api_dataset):
    response = client.get("/api/merchants")
    assert response.status_code == 200

    body = response.json()
    assert body["count"] == 1
    entry = body["merchants"][0]
    assert entry["merchant_id"] == "M001"
    assert entry["total_revenue"] == 2250.0
    assert entry["total_orders"] == 24
    assert entry["products"] == 2


# --------------------------------------------------------------------------
# /api/dataset/summary
# --------------------------------------------------------------------------
def test_dataset_summary_endpoint(api_dataset):
    response = client.get("/api/dataset/summary")
    assert response.status_code == 200

    body = response.json()
    assert body["synthetic"] is True, "the API must state the data is synthetic"
    assert body["sales_rows"] == 6
    assert body["customer_rows"] == 3
    assert body["merchants"] == ["M001"]
    assert body["products"] == 2
    assert body["days"] == 3
    assert body["date_start"] == "2026-01-01"
    assert body["date_end"] == "2026-01-03"
    assert body["validation_status"].startswith("PASS")
    assert body["totals"]["total_revenue"] == 2250.0


# --------------------------------------------------------------------------
# /api/dataset/validation
# --------------------------------------------------------------------------
def test_validation_endpoint(api_dataset):
    response = client.get("/api/dataset/validation")
    assert response.status_code == 200

    body = response.json()
    assert body["ok"] is True
    assert body["errors"] == []
    assert body["stats"]["sales_rows"] == 6


# --------------------------------------------------------------------------
# Failure modes
# --------------------------------------------------------------------------
def test_missing_dataset_returns_503_with_instructions(no_dataset):
    response = client.get("/api/merchants")
    assert response.status_code == 503
    assert "generate_dataset.py" in response.json()["detail"]


def test_invalid_dataset_returns_503(tmp_path, monkeypatch, sales_rows, customer_rows):
    sales_rows[0]["orders"] = 99  # orders > units_sold
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

    response = client.get("/api/dataset/summary")
    assert response.status_code == 503
    assert "R011" in response.json()["detail"]
    data_loader.clear_cache()


def test_health_still_reports_dataset_presence(api_dataset):
    """Stage 1's health endpoint must keep working unchanged."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
