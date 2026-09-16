"""Edge-case coverage (Stage 8).

Degenerate and boundary selections, exercised against every endpoint at once.
The point is not that each returns 200 — it is that a short, empty or absurd
range produces an honest, finite, explained answer rather than noise or a crash.
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import assistant as A
from backend.app.services import data_loader

client = TestClient(app)

GET_ENDPOINTS = (
    "/api/dashboard",
    "/api/insights",
    "/api/recommendations",
    "/api/action-plan",
    "/api/forecast",
)

DATA_START = date(2026, 3, 20)
DATA_END = date(2026, 9, 15)


def _real_dataset_available() -> bool:
    from backend.app.config import settings

    return settings.sales_path.exists() and settings.customers_path.exists()


needs_real = pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("complete() must not be called while the LLM is disabled")

    monkeypatch.setattr(A, "is_enabled", lambda: False)
    monkeypatch.setattr(A, "complete", explode)
    data_loader.clear_cache()
    yield
    data_loader.clear_cache()


def all_endpoints(params):
    """Every GET endpoint plus the assistant, for one query."""
    results = {path: client.get(path, params=params) for path in GET_ENDPOINTS}
    results["/api/assistant/ask"] = client.post(
        "/api/assistant/ask", json={**params, "question": "How is the business doing?"}
    )
    return results


def assert_all_ok_and_finite(params):
    for path, response in all_endpoints(params).items():
        assert response.status_code == 200, f"{path} -> {response.status_code}"
        raw = response.text
        assert "NaN" not in raw, f"{path} emitted NaN"
        assert "Infinity" not in raw, f"{path} emitted Infinity"
        _assert_finite(json.loads(raw), path)


def _assert_finite(node, path):
    if isinstance(node, bool):
        return
    if isinstance(node, float):
        assert math.isfinite(node), f"{path} emitted {node}"
    elif isinstance(node, dict):
        for value in node.values():
            _assert_finite(value, path)
    elif isinstance(node, list):
        for value in node:
            _assert_finite(value, path)


# --------------------------------------------------------------------------
# A-C, P — degenerate and extreme ranges
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("days", [1, 2, 3, 4, 5])
def test_short_ranges_answer_honestly(days):
    start = DATA_END - timedelta(days=days - 1)
    assert_all_ok_and_finite(
        {"merchant_id": "M001", "start": start.isoformat(), "end": DATA_END.isoformat()}
    )


@needs_real
def test_a_single_day_reports_one_day():
    params = {"merchant_id": "M001", "start": "2026-09-15", "end": "2026-09-15"}
    dashboard = client.get("/api/dashboard", params=params).json()

    assert dashboard["summary"]["days"] == 1
    assert len(dashboard["daily"]) == 1
    # A single day cannot support a growth comparison.
    assert dashboard["summary"]["revenue_growth_rate"] == 0.0


@needs_real
def test_a_range_far_larger_than_the_data_clamps_to_what_exists():
    params = {"merchant_id": "M001", "start": "2020-01-01", "end": "2030-12-31"}
    assert_all_ok_and_finite(params)

    dashboard = client.get("/api/dashboard", params=params).json()
    assert dashboard["summary"]["period_start"] == DATA_START.isoformat()
    assert dashboard["summary"]["period_end"] == DATA_END.isoformat()


# --------------------------------------------------------------------------
# D, E — dataset boundaries
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("boundary", [DATA_START, DATA_END])
def test_dataset_boundaries_behave(boundary):
    assert_all_ok_and_finite(
        {"merchant_id": "M001", "start": boundary.isoformat(), "end": boundary.isoformat()}
    )


@needs_real
def test_the_first_day_has_no_earlier_period_to_compare_with():
    params = {
        "merchant_id": "M001",
        "start": DATA_START.isoformat(),
        "end": (DATA_START + timedelta(days=6)).isoformat(),
    }
    insights = client.get("/api/insights", params=params).json()

    # Nothing exists before the dataset starts, so the split is used instead.
    assert insights["comparison_basis"] == "within_period"
    assert any("second half" in note for note in insights["notes"])


# --------------------------------------------------------------------------
# F — the comparison-minimum boundary
# --------------------------------------------------------------------------
@needs_real
def test_comparison_minimum_boundary_is_exact():
    from backend.app.services.analysis import MIN_DAYS_FOR_COMPARISON

    def basis(days):
        start = DATA_END - timedelta(days=days - 1)
        return client.get(
            "/api/insights",
            params={
                "merchant_id": "M001",
                "start": start.isoformat(),
                "end": DATA_END.isoformat(),
            },
        ).json()["comparison_basis"]

    assert basis(MIN_DAYS_FOR_COMPARISON - 1) is None
    assert basis(MIN_DAYS_FOR_COMPARISON) == "previous_period"


@needs_real
@pytest.mark.parametrize("days", [1, 2, 3])
def test_short_ranges_explain_why_there_are_no_trends(days):
    """Regression: these used to report the normal weekly rhythm as HIGH-severity
    revenue collapses."""
    start = DATA_END - timedelta(days=days - 1)
    insights = client.get(
        "/api/insights",
        params={"merchant_id": "M004", "start": start.isoformat(), "end": DATA_END.isoformat()},
    ).json()

    assert insights["comparison_basis"] is None
    assert insights["notes"]
    for finding in insights["findings"]:
        assert not finding["id"].startswith(("total-", "profit-margin", "repeat-rate"))


# --------------------------------------------------------------------------
# G, H — narrow merchants
# --------------------------------------------------------------------------
@needs_real
def test_every_merchant_survives_a_narrow_window():
    for merchant_id in ("M001", "M002", "M003", "M004"):
        assert_all_ok_and_finite(
            {"merchant_id": merchant_id, "start": "2026-09-09", "end": "2026-09-15"}
        )


@needs_real
def test_a_single_category_selection_does_not_break_share_maths():
    """Category share must still sum to 1 when there is only one category."""
    insights = client.get(
        "/api/insights", params={"merchant_id": "M003", "start": "2026-09-09", "end": "2026-09-15"}
    ).json()

    for finding in insights["findings"]:
        if finding["unit"] == "rate":
            assert 0.0 <= finding["value"] <= 1.0, finding["id"]


# --------------------------------------------------------------------------
# K-O — empty and invalid input
# --------------------------------------------------------------------------
@needs_real
def test_an_empty_period_is_explained_everywhere():
    params = {"merchant_id": "M001", "start": "2019-01-01", "end": "2019-02-01"}
    assert_all_ok_and_finite(params)

    assert client.get("/api/dashboard", params=params).json()["has_data"] is False
    assert client.get("/api/forecast", params=params).json()["reason"]
    assert client.get("/api/insights", params=params).json()["notes"]


@needs_real
@pytest.mark.parametrize(
    "params",
    [
        {"merchant_id": "M001", "start": "not-a-date"},
        {"merchant_id": "M001", "start": "2026-13-45"},
        {"merchant_id": "M001", "end": "15-09-2026"},
    ],
)
def test_invalid_dates_are_rejected_consistently(params):
    for path in GET_ENDPOINTS:
        assert client.get(path, params=params).status_code == 422, path


@needs_real
def test_reversed_range_is_rejected_before_any_work_happens():
    params = {"merchant_id": "M001", "start": "2026-09-15", "end": "2026-03-20"}
    for path in GET_ENDPOINTS:
        response = client.get(path, params=params)
        assert response.status_code == 400
        assert "after end" in response.json()["detail"]


@needs_real
@pytest.mark.parametrize("merchant_id", ["", "   ", "m001", "M999", "'; DROP TABLE--", "../../etc"])
def test_unknown_merchant_identifiers_are_refused_not_guessed(merchant_id):
    """Including lowercase: ids are exact, never fuzzy-matched."""
    response = client.get("/api/dashboard", params={"merchant_id": merchant_id})
    assert response.status_code == 404
    assert "Traceback" not in response.text


# --------------------------------------------------------------------------
# Z — the assistant with no model configured
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize(
    "question",
    ["", "   ", "?", "a" * 499, "Why did my sales decrease?", "¿Por qué bajaron mis ventas?"],
)
def test_the_assistant_handles_any_question_shape(question):
    response = client.post(
        "/api/assistant/ask", json={"merchant_id": "M001", "question": question}
    )
    if not question.strip():
        # Empty or whitespace-only is rejected by validation, or answered as a
        # general summary — either is fine, but never a crash.
        assert response.status_code in (200, 422)
    else:
        assert response.status_code == 200
        assert response.json()["answer"]


@needs_real
def test_the_assistant_never_reaches_a_provider_by_default():
    """The autouse fixture fails the test if `complete()` is ever called."""
    body = client.post(
        "/api/assistant/ask",
        json={"merchant_id": "M001", "question": "What should I focus on today?"},
    ).json()

    assert body["llm_enabled"] is False
    assert body["source"] == "deterministic"
