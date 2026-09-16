"""Insights endpoint (Stage 4).

Covers the response contract and the error shapes. The analysis rules
themselves are tested in `test_analysis.py`.
"""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import data_loader

client = TestClient(app)

LAST_30 = {"start": "2026-08-17", "end": "2026-09-15"}

FINDING_FIELDS = {
    "id", "category", "severity", "title", "description", "metric", "value",
    "unit", "scope", "reason", "period", "change", "comparison_value", "evidence",
}

VALID_CATEGORIES = {
    "Revenue", "Orders", "Customers", "Profit",
    "Product", "Category", "Inventory", "Trend",
}


def _real_dataset_available() -> bool:
    from backend.app.config import settings

    return settings.sales_path.exists() and settings.customers_path.exists()


needs_real = pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")


@pytest.fixture(autouse=True)
def fresh_cache():
    data_loader.clear_cache()
    yield
    data_loader.clear_cache()


def get_insights(**params):
    return client.get("/api/insights", params=params)


# --------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------
@needs_real
def test_returns_200():
    assert get_insights(merchant_id="M001", **LAST_30).status_code == 200


@needs_real
def test_response_structure():
    body = get_insights(merchant_id="M001", **LAST_30).json()

    assert set(body) == {
        "merchant_id", "requested_start", "requested_end", "has_data",
        "period", "comparison_period", "comparison_basis",
        "finding_count", "severity_counts", "notes", "findings",
    }
    assert body["merchant_id"] == "M001"
    assert body["has_data"] is True
    assert body["requested_start"] == "2026-08-17"
    assert body["requested_end"] == "2026-09-15"


@needs_real
def test_period_and_comparison_period_are_reported():
    body = get_insights(merchant_id="M001", **LAST_30).json()

    assert body["period"] == {"start": "2026-08-17", "end": "2026-09-15", "days": 30}
    assert body["comparison_period"]["days"] == 30
    assert body["comparison_period"]["end"] == "2026-08-16"
    assert body["comparison_basis"] == "previous_period"


@needs_real
def test_every_finding_has_the_full_contract():
    findings = get_insights(merchant_id="M001", **LAST_30).json()["findings"]
    assert findings

    for finding in findings:
        assert set(finding) == FINDING_FIELDS
        assert finding["category"] in VALID_CATEGORIES
        assert finding["severity"] in {"HIGH", "MEDIUM", "LOW"}
        assert finding["unit"] in {"currency", "count", "rate", "days"}
        assert finding["title"] and finding["description"] and finding["reason"]
        assert finding["scope"]
        assert set(finding["period"]) == {"start", "end", "days"}
        assert isinstance(finding["evidence"], dict)


@needs_real
def test_counts_match_the_findings_list():
    body = get_insights(merchant_id="M001", **LAST_30).json()

    assert body["finding_count"] == len(body["findings"])
    assert sum(body["severity_counts"].values()) == body["finding_count"]

    for severity, count in body["severity_counts"].items():
        assert count == sum(1 for f in body["findings"] if f["severity"] == severity)


@needs_real
def test_findings_are_ordered_most_severe_first():
    findings = get_insights(merchant_id="M001", **LAST_30).json()["findings"]
    rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ranks = [rank[f["severity"]] for f in findings]
    assert ranks == sorted(ranks)


@needs_real
def test_response_contains_no_nan_or_infinity():
    """NaN and Infinity are not valid JSON and would break the browser parser."""
    raw = get_insights(merchant_id="M003", **LAST_30).text
    assert "NaN" not in raw
    assert "Infinity" not in raw

    body = json.loads(raw)
    for finding in body["findings"]:
        for key in ("value", "change", "comparison_value"):
            value = finding[key]
            if isinstance(value, (int, float)):
                assert math.isfinite(value), f"{finding['id']}.{key}"


@needs_real
def test_date_filtering_changes_the_analysis():
    narrow = get_insights(merchant_id="M001", start="2026-09-01", end="2026-09-15").json()
    wide = get_insights(merchant_id="M001", **LAST_30).json()

    assert narrow["period"]["days"] == 15
    assert wide["period"]["days"] == 30
    assert narrow["findings"] != wide["findings"]


@needs_real
def test_merchant_filtering_changes_the_analysis():
    growing = get_insights(merchant_id="M001", **LAST_30).json()
    declining = get_insights(merchant_id="M003", **LAST_30).json()

    assert growing["findings"] != declining["findings"]
    assert any(f["id"] == "total-revenue-up" for f in growing["findings"])
    assert any(f["id"] == "total-revenue-down" for f in declining["findings"])


@needs_real
def test_repeated_requests_are_identical():
    first = get_insights(merchant_id="M003", **LAST_30).json()
    second = get_insights(merchant_id="M003", **LAST_30).json()
    assert first == second


@needs_real
def test_full_range_reports_the_within_period_fallback():
    body = get_insights(merchant_id="M003").json()

    assert body["comparison_basis"] == "within_period"
    assert any("second half" in note for note in body["notes"])


# --------------------------------------------------------------------------
# Empty and invalid input
# --------------------------------------------------------------------------
@needs_real
def test_range_outside_the_data_is_empty_not_an_error():
    response = get_insights(merchant_id="M001", start="2020-01-01", end="2020-02-01")
    assert response.status_code == 200

    body = response.json()
    assert body["has_data"] is False
    assert body["findings"] == []
    assert body["finding_count"] == 0
    assert body["period"] is None
    assert body["notes"]


@needs_real
def test_unknown_merchant_returns_404():
    response = get_insights(merchant_id="NOPE")
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@needs_real
def test_missing_merchant_returns_422():
    assert client.get("/api/insights").status_code == 422


@needs_real
def test_start_after_end_returns_400():
    response = get_insights(merchant_id="M001", start="2026-09-15", end="2026-08-17")
    assert response.status_code == 400
    assert "after end" in response.json()["detail"]


@needs_real
def test_malformed_date_returns_422():
    assert get_insights(merchant_id="M001", start="not-a-date").status_code == 422


@needs_real
def test_errors_never_leak_a_traceback():
    for params in (
        {"merchant_id": "NOPE"},
        {"merchant_id": "M001", "start": "2026-09-15", "end": "2026-08-17"},
        {"merchant_id": "M001", "start": "garbage"},
    ):
        text = get_insights(**params).text
        assert "Traceback" not in text
        assert 'File "' not in text


def test_missing_dataset_returns_503(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()

    response = get_insights(merchant_id="M001")
    assert response.status_code == 503
    assert "generate_dataset.py" in response.json()["detail"]


# --------------------------------------------------------------------------
# Stage 1-3 endpoints still behave
# --------------------------------------------------------------------------
@needs_real
def test_existing_endpoints_are_unaffected():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/merchants").status_code == 200
    assert client.get("/api/dataset/summary").status_code == 200
    assert client.get("/api/dataset/validation").status_code == 200
    assert client.get("/api/dashboard", params={"merchant_id": "M001"}).status_code == 200


@needs_real
def test_insights_and_dashboard_agree_on_the_period():
    """Both endpoints read the same services, so they must describe the same
    window for the same query."""
    insights = get_insights(merchant_id="M001", **LAST_30).json()
    dashboard = client.get("/api/dashboard", params={"merchant_id": "M001", **LAST_30}).json()

    assert insights["period"]["start"] == dashboard["summary"]["period_start"]
    assert insights["period"]["end"] == dashboard["summary"]["period_end"]
    assert insights["period"]["days"] == dashboard["summary"]["days"]
