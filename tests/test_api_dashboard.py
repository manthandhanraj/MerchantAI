"""Dashboard endpoint (Stage 3).

Most tests run against the small fixture dataset so the expected values are
exact and hand-checkable:

    day 1  revenue 750   orders  8  customers 6
    day 2  revenue 600   orders  6  customers 5
    day 3  revenue 900   orders 10  customers 8
    total  revenue 2250  orders 24  customers 19  expenses 1125
"""

from __future__ import annotations

import math
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


def get_dashboard(**params):
    return client.get("/api/dashboard", params=params)


# --------------------------------------------------------------------------
# Success
# --------------------------------------------------------------------------
def test_returns_200_for_valid_merchant(api_dataset):
    assert get_dashboard(merchant_id="M001").status_code == 200


def test_response_structure(api_dataset):
    body = get_dashboard(merchant_id="M001").json()
    assert set(body) == {
        "merchant_id",
        "requested_start",
        "requested_end",
        "has_data",
        "summary",
        "daily",
    }
    assert body["merchant_id"] == "M001"
    assert body["has_data"] is True


def test_summary_totals_match_the_fixture(api_dataset):
    summary = get_dashboard(merchant_id="M001").json()["summary"]
    assert summary["total_revenue"] == 2250.0
    assert summary["total_orders"] == 24
    assert summary["total_customers"] == 19
    assert summary["total_expenses"] == 1125.0
    assert summary["total_profit"] == 1125.0
    assert summary["average_order_value"] == pytest.approx(93.75)
    assert summary["profit_margin"] == pytest.approx(0.5)
    assert summary["days"] == 3
    assert summary["period_start"] == "2026-01-01"
    assert summary["period_end"] == "2026-01-03"


def test_daily_series_matches_the_fixture(api_dataset):
    daily = get_dashboard(merchant_id="M001").json()["daily"]
    assert len(daily) == 3
    assert [point["date"] for point in daily] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert [point["revenue"] for point in daily] == [750.0, 600.0, 900.0]
    assert [point["orders"] for point in daily] == [8, 6, 10]
    assert [point["customers"] for point in daily] == [6, 5, 8]
    assert [point["profit"] for point in daily] == [375.0, 300.0, 450.0]


def test_daily_point_has_every_charted_field(api_dataset):
    point = get_dashboard(merchant_id="M001").json()["daily"][0]
    assert set(point) == {
        "date",
        "revenue",
        "expenses",
        "profit",
        "average_order_value",
        "orders",
        "units_sold",
        "customers",
        "new_customers",
        "repeat_customers",
        "profit_margin",
        "repeat_customer_rate",
    }


def test_daily_length_matches_summary_days(api_dataset):
    body = get_dashboard(merchant_id="M001").json()
    assert len(body["daily"]) == body["summary"]["days"]


def test_daily_totals_reconcile_with_summary(api_dataset):
    """The chart and the KPI cards must not be able to disagree."""
    body = get_dashboard(merchant_id="M001").json()
    assert sum(p["revenue"] for p in body["daily"]) == pytest.approx(body["summary"]["total_revenue"])
    assert sum(p["orders"] for p in body["daily"]) == body["summary"]["total_orders"]
    assert sum(p["customers"] for p in body["daily"]) == body["summary"]["total_customers"]


# --------------------------------------------------------------------------
# Date filtering
# --------------------------------------------------------------------------
def test_date_range_narrows_the_result(api_dataset):
    body = get_dashboard(merchant_id="M001", start="2026-01-02", end="2026-01-02").json()
    assert body["summary"]["total_revenue"] == 600.0
    assert body["summary"]["days"] == 1
    assert len(body["daily"]) == 1
    assert body["daily"][0]["date"] == "2026-01-02"


def test_start_only_filters_from_that_date(api_dataset):
    body = get_dashboard(merchant_id="M001", start="2026-01-02").json()
    assert body["summary"]["total_revenue"] == 1500.0  # days 2 + 3
    assert len(body["daily"]) == 2


def test_end_only_filters_up_to_that_date(api_dataset):
    body = get_dashboard(merchant_id="M001", end="2026-01-02").json()
    assert body["summary"]["total_revenue"] == 1350.0  # days 1 + 2
    assert len(body["daily"]) == 2


def test_requested_dates_are_echoed_back(api_dataset):
    body = get_dashboard(merchant_id="M001", start="2026-01-02", end="2026-01-03").json()
    assert body["requested_start"] == "2026-01-02"
    assert body["requested_end"] == "2026-01-03"


def test_omitted_dates_echo_as_null(api_dataset):
    body = get_dashboard(merchant_id="M001").json()
    assert body["requested_start"] is None
    assert body["requested_end"] is None


# --------------------------------------------------------------------------
# Empty result
# --------------------------------------------------------------------------
def test_range_outside_the_data_is_empty_not_an_error(api_dataset):
    """An empty selection is a valid answer, so the UI shows an empty state
    rather than an error state."""
    response = get_dashboard(merchant_id="M001", start="2020-01-01", end="2020-02-01")
    assert response.status_code == 200

    body = response.json()
    assert body["has_data"] is False
    assert body["daily"] == []
    assert body["summary"]["total_revenue"] == 0.0
    assert body["summary"]["days"] == 0
    assert body["summary"]["period_start"] is None


def test_empty_summary_has_no_nan_or_infinity(api_dataset):
    """Zero orders must divide to 0.0, never NaN or Infinity."""
    summary = get_dashboard(merchant_id="M001", start="2020-01-01", end="2020-02-01").json()["summary"]
    assert summary["average_order_value"] == 0.0
    assert summary["profit_margin"] == 0.0
    assert summary["repeat_customer_rate"] == 0.0
    for key, value in summary.items():
        if isinstance(value, float):
            assert math.isfinite(value), f"{key} is not finite"


# --------------------------------------------------------------------------
# Invalid input
# --------------------------------------------------------------------------
def test_unknown_merchant_returns_404(api_dataset):
    response = get_dashboard(merchant_id="NOPE")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "NOPE" in detail
    assert "M001" in detail, "the error should list what is available"


def test_missing_merchant_returns_422(api_dataset):
    assert client.get("/api/dashboard").status_code == 422


def test_start_after_end_returns_400(api_dataset):
    response = get_dashboard(merchant_id="M001", start="2026-01-03", end="2026-01-01")
    assert response.status_code == 400
    assert "after end" in response.json()["detail"]


def test_malformed_date_returns_422(api_dataset):
    assert get_dashboard(merchant_id="M001", start="not-a-date").status_code == 422


def test_errors_never_leak_a_traceback(api_dataset):
    for params in (
        {"merchant_id": "NOPE"},
        {"merchant_id": "M001", "start": "2026-01-03", "end": "2026-01-01"},
        {"merchant_id": "M001", "start": "garbage"},
    ):
        body = get_dashboard(**params).json()
        assert "Traceback" not in str(body)
        assert "File \"" not in str(body)


# --------------------------------------------------------------------------
# Pipeline failures
# --------------------------------------------------------------------------
def test_missing_dataset_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()

    response = get_dashboard(merchant_id="M001")
    assert response.status_code == 503
    assert "generate_dataset.py" in response.json()["detail"]
    data_loader.clear_cache()


# --------------------------------------------------------------------------
# The real generated dataset
# --------------------------------------------------------------------------
def _real_dataset_available() -> bool:
    from backend.app.config import settings

    return settings.sales_path.exists() and settings.customers_path.exists()


@pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")
def test_growing_and_declining_merchants_differ_in_the_api():
    """M001 grows and M003 declines. The dashboard is only meaningful if that
    difference survives all the way to the endpoint."""
    data_loader.clear_cache()

    def trend(merchant_id: str) -> float:
        daily = get_dashboard(merchant_id=merchant_id).json()["daily"]
        first = sum(p["revenue"] for p in daily[:30]) / 30
        last = sum(p["revenue"] for p in daily[-30:]) / 30
        return last / first - 1

    assert trend("M001") > 0.1, "M001 should read as growing"
    assert trend("M003") < -0.1, "M003 should read as declining"


@pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")
def test_every_merchant_returns_finite_values():
    data_loader.clear_cache()
    merchants = client.get("/api/merchants").json()["merchants"]
    assert merchants

    for entry in merchants:
        body = get_dashboard(merchant_id=entry["merchant_id"]).json()
        assert body["has_data"] is True
        for key, value in body["summary"].items():
            if isinstance(value, float):
                assert math.isfinite(value), f"{entry['merchant_id']}.{key}"
        for point in body["daily"]:
            for key, value in point.items():
                if isinstance(value, float):
                    assert math.isfinite(value), f"{entry['merchant_id']}.{point['date']}.{key}"
