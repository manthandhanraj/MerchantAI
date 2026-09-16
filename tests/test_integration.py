"""End-to-end integration (Stage 7).

Every feature is exercised individually by its own suite. These tests check the
seams: that one merchant and one date range drive the whole application
consistently, that each layer's output really is the next layer's input, and
that a failure in one feature cannot damage the others.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import assistant as A
from backend.app.services import data_loader
from backend.app.services.llm import LLMError

client = TestClient(app)

QUERY = {"merchant_id": "M003", "start": "2026-08-17", "end": "2026-09-15"}
MERCHANTS = ["M001", "M002", "M003", "M004"]

GET_ENDPOINTS = (
    "/api/dashboard",
    "/api/insights",
    "/api/recommendations",
    "/api/action-plan",
    "/api/forecast",
)


def _real_dataset_available() -> bool:
    from backend.app.config import settings

    return settings.sales_path.exists() and settings.customers_path.exists()


needs_real = pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """Fresh cache, and no test may reach a model provider."""

    def explode(*_args, **_kwargs):
        raise AssertionError("complete() must not be called while the LLM is disabled")

    monkeypatch.setattr(A, "is_enabled", lambda: False)
    monkeypatch.setattr(A, "complete", explode)
    data_loader.clear_cache()
    yield
    data_loader.clear_cache()


def ask(**overrides):
    body = {"merchant_id": QUERY["merchant_id"], "question": "How is the business doing?"}
    body.update({k: v for k, v in QUERY.items() if k != "merchant_id"})
    body.update(overrides)
    return client.post("/api/assistant/ask", json=body)


# --------------------------------------------------------------------------
# The whole surface responds
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("path", GET_ENDPOINTS)
@pytest.mark.parametrize("merchant_id", MERCHANTS)
def test_every_endpoint_answers_for_every_merchant(path, merchant_id):
    response = client.get(path, params={**QUERY, "merchant_id": merchant_id})
    assert response.status_code == 200


@needs_real
def test_the_whole_pipeline_runs_for_one_merchant():
    """Dataset -> metrics -> dashboard -> insights -> recommendations ->
    action plan -> forecast -> assistant, in one pass."""
    assert client.get("/api/health").json()["sales_data_present"] is True
    assert client.get("/api/merchants").json()["count"] >= 1

    for path in GET_ENDPOINTS:
        assert client.get(path, params=QUERY).status_code == 200

    answer = ask()
    assert answer.status_code == 200
    assert answer.json()["answer"]


# --------------------------------------------------------------------------
# One query, one consistent answer everywhere
# --------------------------------------------------------------------------
@needs_real
def test_every_endpoint_reports_the_same_period():
    dashboard = client.get("/api/dashboard", params=QUERY).json()
    insights = client.get("/api/insights", params=QUERY).json()
    plan = client.get("/api/action-plan", params=QUERY).json()
    recommendations = client.get("/api/recommendations", params=QUERY).json()
    forecast = client.get("/api/forecast", params=QUERY).json()

    period = {
        "start": dashboard["summary"]["period_start"],
        "end": dashboard["summary"]["period_end"],
        "days": dashboard["summary"]["days"],
    }
    assert insights["period"] == period
    assert plan["period"] == period
    assert recommendations["period"] == period
    assert forecast["history"] == period


@needs_real
def test_recommendations_trace_back_to_insight_findings():
    """Stage 5 must be derived from Stage 4, not from a second analysis."""
    insights = client.get("/api/insights", params=QUERY).json()
    recommendations = client.get("/api/recommendations", params=QUERY).json()

    finding_ids = {f["id"] for f in insights["findings"]}
    assert recommendations["recommendations"]
    for recommendation in recommendations["recommendations"]:
        assert recommendation["source_finding"] in finding_ids


@needs_real
def test_action_plan_items_trace_back_to_recommendations():
    recommendations = client.get("/api/recommendations", params=QUERY).json()
    plan = client.get("/api/action-plan", params=QUERY).json()

    sources = {r["source_finding"] for r in recommendations["recommendations"]}
    items = plan["high"] + plan["medium"] + plan["low"]
    assert items
    for item in items:
        assert item["source_finding"] in sources


@needs_real
def test_assistant_context_matches_the_other_endpoints():
    """The assistant must not hold its own copy of the numbers."""
    body = ask(include_context=True).json()
    context = body["context"]

    dashboard = client.get("/api/dashboard", params=QUERY).json()
    insights = client.get("/api/insights", params=QUERY).json()
    forecast = client.get("/api/forecast", params=QUERY).json()

    assert context["summary"] == dashboard["summary"]
    assert context["forecast"]["forecast_total"] == forecast["forecast_total"]
    assert {f["id"] for f in context["findings"]} <= {f["id"] for f in insights["findings"]}


@needs_real
def test_dashboard_daily_series_reconciles_with_its_summary():
    dashboard = client.get("/api/dashboard", params=QUERY).json()

    assert sum(p["revenue"] for p in dashboard["daily"]) == pytest.approx(
        dashboard["summary"]["total_revenue"]
    )
    assert sum(p["orders"] for p in dashboard["daily"]) == dashboard["summary"]["total_orders"]


@needs_real
def test_forecast_continues_the_dashboard_series():
    """The projection must start the day after the last charted day."""
    from datetime import date, timedelta

    dashboard = client.get("/api/dashboard", params=QUERY).json()
    forecast = client.get("/api/forecast", params=QUERY).json()

    last_charted = date.fromisoformat(dashboard["daily"][-1]["date"])
    first_projected = date.fromisoformat(forecast["forecast_period"]["start"])
    assert first_projected == last_charted + timedelta(days=1)


# --------------------------------------------------------------------------
# Changing the query changes everything together
# --------------------------------------------------------------------------
@needs_real
def test_switching_merchant_changes_every_feature():
    def snapshot(merchant_id):
        params = {**QUERY, "merchant_id": merchant_id}
        return (
            client.get("/api/dashboard", params=params).json()["summary"]["total_revenue"],
            [f["id"] for f in client.get("/api/insights", params=params).json()["findings"]],
            [i["source_finding"] for i in client.get("/api/action-plan", params=params).json()["high"]],
        )

    first = snapshot("M001")
    second = snapshot("M003")

    assert first[0] != second[0], "revenue should differ between merchants"
    assert first[1] != second[1], "findings should differ between merchants"
    assert first != second


@needs_real
def test_forecast_reflects_each_merchants_designed_behaviour():
    """Asserted over full history, which is the window the Stage 2 trends were
    designed across. A 30-day slice can legitimately run the other way — M001's
    last 30 days sit after its festival peak.
    """

    def trend(merchant_id):
        return client.get("/api/forecast", params={"merchant_id": merchant_id}).json()[
            "trend_direction"
        ]

    assert trend("M001") == "rising"
    assert trend("M003") == "falling"


@needs_real
def test_changing_the_date_range_changes_every_feature():
    narrow = {"merchant_id": "M001", "start": "2026-09-01", "end": "2026-09-15"}
    wide = {"merchant_id": "M001", "start": "2026-03-20", "end": "2026-09-15"}

    for path in ("/api/dashboard", "/api/insights", "/api/action-plan"):
        assert client.get(path, params=narrow).json() != client.get(path, params=wide).json()

    assert (
        client.get("/api/dashboard", params=narrow).json()["summary"]["days"]
        < client.get("/api/dashboard", params=wide).json()["summary"]["days"]
    )


# --------------------------------------------------------------------------
# Consistent validation across the whole surface
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_unknown_merchant_is_404_everywhere(path):
    assert client.get(path, params={"merchant_id": "NOPE"}).status_code == 404


@needs_real
@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_inverted_range_is_400_everywhere(path):
    response = client.get(
        path, params={"merchant_id": "M001", "start": "2026-09-15", "end": "2026-08-17"}
    )
    assert response.status_code == 400


@needs_real
@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_missing_merchant_is_422_everywhere(path):
    assert client.get(path).status_code == 422


@needs_real
def test_assistant_shares_the_same_validation():
    assert ask(merchant_id="NOPE").status_code == 404
    assert ask(start="2026-09-15", end="2026-08-17").status_code == 400
    assert client.post("/api/assistant/ask", json={"merchant_id": "M001"}).status_code == 422


@needs_real
@pytest.mark.parametrize("path", GET_ENDPOINTS)
def test_no_endpoint_leaks_a_traceback(path):
    text = client.get(path, params={"merchant_id": "NOPE"}).text
    assert "Traceback" not in text
    assert 'File "' not in text


# --------------------------------------------------------------------------
# Empty and insufficient data
# --------------------------------------------------------------------------
@needs_real
def test_an_empty_period_is_an_empty_answer_everywhere_not_an_error():
    empty = {"merchant_id": "M001", "start": "2020-01-01", "end": "2020-02-01"}

    for path in GET_ENDPOINTS:
        assert client.get(path, params=empty).status_code == 200

    assert client.get("/api/dashboard", params=empty).json()["has_data"] is False
    assert client.get("/api/insights", params=empty).json()["findings"] == []
    assert client.get("/api/action-plan", params=empty).json()["included"] == 0
    assert client.get("/api/forecast", params=empty).json()["available"] is False
    assert ask(**{k: v for k, v in empty.items() if k != "merchant_id"}).json()["has_data"] is False


@needs_real
def test_a_short_period_keeps_everything_else_working():
    """Too little history for a forecast must not stop the rest reporting."""
    short = {"merchant_id": "M001", "start": "2026-09-10", "end": "2026-09-15"}

    assert client.get("/api/forecast", params=short).json()["available"] is False
    assert client.get("/api/dashboard", params=short).json()["has_data"] is True
    assert client.get("/api/insights", params=short).status_code == 200
    assert client.get("/api/action-plan", params=short).status_code == 200


# --------------------------------------------------------------------------
# Failure isolation
# --------------------------------------------------------------------------
@needs_real
def test_a_failing_assistant_leaves_every_other_endpoint_working(monkeypatch):
    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(
        A, "complete", lambda *a, **k: (_ for _ in ()).throw(LLMError("provider down"))
    )

    answer = ask()
    assert answer.status_code == 200
    assert answer.json()["source"] == "deterministic"

    for path in GET_ENDPOINTS:
        assert client.get(path, params=QUERY).status_code == 200


@needs_real
def test_a_missing_dataset_fails_every_endpoint_the_same_way(tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()

    for path in GET_ENDPOINTS:
        response = client.get(path, params={"merchant_id": "M001"})
        assert response.status_code == 503
        assert "generate_dataset.py" in response.json()["detail"]

    assert ask().status_code == 503


# --------------------------------------------------------------------------
# Output safety across the whole surface
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("merchant_id", MERCHANTS)
def test_no_endpoint_emits_nan_or_infinity(merchant_id):
    for path in GET_ENDPOINTS:
        raw = client.get(path, params={**QUERY, "merchant_id": merchant_id}).text
        assert "NaN" not in raw, f"{path} for {merchant_id}"
        assert "Infinity" not in raw, f"{path} for {merchant_id}"


@needs_real
def test_dashboard_numbers_are_all_finite():
    body = client.get("/api/dashboard", params=QUERY).json()
    for key, value in body["summary"].items():
        if isinstance(value, float):
            assert math.isfinite(value), key


@needs_real
def test_the_assistant_stays_offline_by_default():
    body = ask().json()
    assert body["llm_enabled"] is False
    assert body["source"] == "deterministic"
    assert body["warnings"] == []


@needs_real
def test_no_endpoint_exposes_the_api_key():
    status = client.get("/api/assistant/status").json()
    assert "key_present" in status
    assert "llm_api_key" not in str(status).lower()
    assert "api_key" not in str(status).lower()
