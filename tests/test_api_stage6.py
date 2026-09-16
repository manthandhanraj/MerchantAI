"""Forecast and assistant endpoints (Stage 6).

Covers the response contracts, the error shapes, and that a failing Stage 6
feature cannot take the Stage 1-5 endpoints with it.
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

LAST_30 = {"start": "2026-08-17", "end": "2026-09-15"}


def _real_dataset_available() -> bool:
    from backend.app.config import settings

    return settings.sales_path.exists() and settings.customers_path.exists()


needs_real = pytest.mark.skipif(not _real_dataset_available(), reason="dataset not generated")


@pytest.fixture(autouse=True)
def fresh_cache():
    data_loader.clear_cache()
    yield
    data_loader.clear_cache()


@pytest.fixture(autouse=True)
def llm_off(monkeypatch):
    """No API test may reach a provider."""

    def explode(*_args, **_kwargs):
        raise AssertionError("complete() must not be called while the LLM is disabled")

    monkeypatch.setattr(A, "is_enabled", lambda: False)
    monkeypatch.setattr(A, "complete", explode)


def get_forecast(**params):
    return client.get("/api/forecast", params=params)


def post_ask(**body):
    return client.post("/api/assistant/ask", json=body)


# --------------------------------------------------------------------------
# 21 — forecast success
# --------------------------------------------------------------------------
@needs_real
def test_forecast_returns_200():
    assert get_forecast(merchant_id="M001").status_code == 200


@needs_real
def test_forecast_response_structure():
    body = get_forecast(merchant_id="M001").json()

    assert set(body) == {
        "merchant_id", "metric", "available", "reason", "method", "history",
        "forecast_period", "points", "horizon_days", "requested_horizon_days",
        "trend_direction", "trend_per_day", "fit_r_squared", "backtest",
        "confidence_interval", "history_daily_mean", "forecast_total", "limitations",
    }
    assert body["available"] is True
    assert body["method"] == "linear_trend_with_weekday_seasonality"


@needs_real
def test_forecast_points_are_well_formed():
    body = get_forecast(merchant_id="M001").json()

    assert len(body["points"]) == body["horizon_days"]
    for point in body["points"]:
        assert set(point) == {"date", "value", "weekday"}
        assert math.isfinite(point["value"])
        assert point["value"] >= 0


@needs_real
def test_forecast_declares_its_limits():
    body = get_forecast(merchant_id="M001").json()

    assert body["confidence_interval"] is None
    assert body["limitations"]
    assert any("short-term" in note for note in body["limitations"])
    assert body["backtest"]["mean_absolute_error"] >= 0


@needs_real
def test_forecast_horizon_is_capped_not_rejected():
    body = get_forecast(merchant_id="M001", horizon_days=14).json()
    assert body["horizon_days"] == 14
    assert body["requested_horizon_days"] == 14


@needs_real
def test_forecast_horizon_above_the_maximum_is_a_validation_error():
    """The cap is advertised on the query parameter, so an out-of-range request
    is rejected rather than silently reinterpreted."""
    assert get_forecast(merchant_id="M001", horizon_days=90).status_code == 422


@needs_real
def test_forecast_response_has_no_nan_or_infinity():
    raw = get_forecast(merchant_id="M003").text
    assert "NaN" not in raw
    assert "Infinity" not in raw


@needs_real
def test_forecast_is_deterministic_over_http():
    assert get_forecast(merchant_id="M003").json() == get_forecast(merchant_id="M003").json()


# --------------------------------------------------------------------------
# 22 / 23 / 24 — forecast error and insufficiency handling
# --------------------------------------------------------------------------
@needs_real
def test_forecast_unknown_merchant_returns_404():
    response = get_forecast(merchant_id="NOPE")
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@needs_real
def test_forecast_missing_merchant_returns_422():
    assert client.get("/api/forecast").status_code == 422


@needs_real
def test_forecast_inverted_date_range_returns_400():
    response = get_forecast(merchant_id="M001", start="2026-09-15", end="2026-08-17")
    assert response.status_code == 400
    assert "after end" in response.json()["detail"]


@needs_real
def test_forecast_malformed_date_returns_422():
    assert get_forecast(merchant_id="M001", start="not-a-date").status_code == 422


@needs_real
def test_forecast_insufficient_data_is_200_with_a_reason():
    """Too little history is an answer the UI can render, not an error."""
    response = get_forecast(merchant_id="M001", start="2026-09-10", end="2026-09-15")
    assert response.status_code == 200

    body = response.json()
    assert body["available"] is False
    assert body["reason"]
    assert body["points"] == []
    assert body["limitations"]


@needs_real
def test_forecast_empty_period_is_200_with_a_reason():
    body = get_forecast(merchant_id="M001", start="2020-01-01", end="2020-02-01").json()
    assert body["available"] is False
    assert "No sales history" in body["reason"]


@needs_real
def test_forecast_unknown_metric_is_200_with_a_reason():
    body = get_forecast(merchant_id="M001", metric="unicorns").json()
    assert body["available"] is False
    assert "cannot be forecast" in body["reason"]


@needs_real
def test_forecast_errors_never_leak_a_traceback():
    for params in (
        {"merchant_id": "NOPE"},
        {"merchant_id": "M001", "start": "2026-09-15", "end": "2026-08-17"},
        {"merchant_id": "M001", "start": "garbage"},
    ):
        text = get_forecast(**params).text
        assert "Traceback" not in text
        assert 'File "' not in text


# --------------------------------------------------------------------------
# 25 / 27 — assistant success with the LLM disabled
# --------------------------------------------------------------------------
@needs_real
def test_assistant_returns_200():
    assert post_ask(merchant_id="M003", question="Why did my sales decrease?").status_code == 200


@needs_real
def test_assistant_response_structure():
    body = post_ask(merchant_id="M003", question="Why did my sales decrease?", **LAST_30).json()

    assert set(body) == {
        "merchant_id", "question", "answer", "source", "llm_enabled", "has_data",
        "grounded_in", "warnings", "suggested_questions", "limitations", "context",
    }
    assert body["answer"]
    assert body["source"] == "deterministic"
    assert body["llm_enabled"] is False
    assert body["suggested_questions"]
    assert body["limitations"]
    assert body["context"] is None


@needs_real
def test_assistant_works_offline_with_no_key():
    """This is the default configuration and it must produce a real answer."""
    body = post_ask(merchant_id="M001", question="How is the business doing?", **LAST_30).json()

    assert body["llm_enabled"] is False
    assert body["warnings"] == []
    assert len(body["answer"]) > 60


@needs_real
def test_assistant_can_return_its_context():
    body = post_ask(
        merchant_id="M001", question="How is trade?", include_context=True, **LAST_30
    ).json()

    assert body["context"] is not None
    for section in ("summary", "findings", "recommendations", "action_plan", "forecast"):
        assert section in body["context"]


@needs_real
def test_assistant_status_reports_configuration_without_the_key():
    body = client.get("/api/assistant/status").json()

    assert body["enabled"] is False
    assert body["key_present"] is False
    assert body["provider"]
    assert body["suggested_questions"]
    assert "api_key" not in str(body).lower()


@needs_real
def test_assistant_is_deterministic_over_http():
    question = {"merchant_id": "M003", "question": "What should I focus on today?", **LAST_30}
    assert post_ask(**question).json() == post_ask(**question).json()


@needs_real
def test_assistant_reports_an_unavailable_forecast():
    body = post_ask(
        merchant_id="M001",
        question="What's the forecast for the coming days?",
        start="2026-09-10",
        end="2026-09-15",
    ).json()

    assert body["has_data"] is True
    assert "No forecast is available" in body["answer"]


# --------------------------------------------------------------------------
# 26 — assistant validation
# --------------------------------------------------------------------------
@needs_real
def test_assistant_unknown_merchant_returns_404():
    response = post_ask(merchant_id="NOPE", question="hello")
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@needs_real
def test_assistant_missing_question_returns_422():
    assert client.post("/api/assistant/ask", json={"merchant_id": "M001"}).status_code == 422


@needs_real
def test_assistant_empty_question_returns_422():
    assert post_ask(merchant_id="M001", question="").status_code == 422


@needs_real
def test_assistant_overlong_question_returns_422():
    assert post_ask(merchant_id="M001", question="x" * 5000).status_code == 422


@needs_real
def test_assistant_inverted_date_range_returns_400():
    response = post_ask(
        merchant_id="M001", question="hello", start="2026-09-15", end="2026-08-17"
    )
    assert response.status_code == 400
    assert "after end" in response.json()["detail"]


@needs_real
def test_assistant_malformed_date_returns_422():
    assert post_ask(merchant_id="M001", question="hi", start="not-a-date").status_code == 422


@needs_real
def test_assistant_errors_never_leak_a_traceback():
    for body in (
        {"merchant_id": "NOPE", "question": "hi"},
        {"merchant_id": "M001", "question": "hi", "start": "2026-09-15", "end": "2026-08-17"},
        {"merchant_id": "M001", "question": "hi", "start": "garbage"},
    ):
        text = post_ask(**body).text
        assert "Traceback" not in text
        assert 'File "' not in text


# --------------------------------------------------------------------------
# 28 — Stage 6 failures cannot damage Stages 1-5
# --------------------------------------------------------------------------
@needs_real
def test_assistant_failure_does_not_affect_other_endpoints(monkeypatch):
    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(
        A, "complete", lambda *a, **k: (_ for _ in ()).throw(LLMError("provider down"))
    )

    answer = post_ask(merchant_id="M001", question="How is trade?", **LAST_30)
    assert answer.status_code == 200
    assert answer.json()["source"] == "deterministic"

    assert client.get("/api/dashboard", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/insights", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/action-plan", params={"merchant_id": "M001"}).status_code == 200


@needs_real
def test_forecast_unavailability_does_not_affect_the_dashboard():
    thin = {"merchant_id": "M001", "start": "2026-09-10", "end": "2026-09-15"}

    assert get_forecast(**thin).json()["available"] is False
    assert client.get("/api/dashboard", params=thin).json()["has_data"] is True


@needs_real
def test_all_stage_1_to_5_endpoints_still_respond():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/merchants").status_code == 200
    assert client.get("/api/dataset/summary").status_code == 200
    assert client.get("/api/dataset/validation").status_code == 200
    assert client.get("/api/dashboard", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/insights", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/recommendations", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/action-plan", params={"merchant_id": "M001"}).status_code == 200


@needs_real
def test_stage_6_agrees_with_the_dashboard_on_the_period():
    params = {"merchant_id": "M001", **LAST_30}
    dashboard = client.get("/api/dashboard", params=params).json()
    forecast_body = get_forecast(**params).json()

    assert forecast_body["history"]["start"] == dashboard["summary"]["period_start"]
    assert forecast_body["history"]["end"] == dashboard["summary"]["period_end"]
    assert forecast_body["history"]["days"] == dashboard["summary"]["days"]


@pytest.mark.parametrize("path", ["/api/forecast", "/api/assistant/ask"])
def test_missing_dataset_returns_503(path, tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()

    if path == "/api/forecast":
        response = client.get(path, params={"merchant_id": "M001"})
    else:
        response = client.post(path, json={"merchant_id": "M001", "question": "hi"})

    assert response.status_code == 503
    assert "generate_dataset.py" in response.json()["detail"]
