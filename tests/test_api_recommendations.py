"""Recommendations and action-plan endpoints (Stage 5).

Covers the response contracts and error shapes. The mapping rules themselves
are tested in `test_recommendations.py`.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services import data_loader

client = TestClient(app)

LAST_30 = {"start": "2026-08-17", "end": "2026-09-15"}

RECOMMENDATION_FIELDS = {
    "id", "title", "action", "reason", "priority", "severity", "category",
    "scope", "metric", "value", "unit", "change", "period", "source_finding",
    "evidence",
}

ACTION_ITEM_FIELDS = {
    "rank", "priority", "title", "action", "reason", "category", "scope",
    "source_finding",
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


def get_recommendations(**params):
    return client.get("/api/recommendations", params=params)


def get_plan(**params):
    return client.get("/api/action-plan", params=params)


# --------------------------------------------------------------------------
# L — /api/recommendations
# --------------------------------------------------------------------------
@needs_real
def test_recommendations_returns_200():
    assert get_recommendations(merchant_id="M001", **LAST_30).status_code == 200


@needs_real
def test_recommendations_response_structure():
    body = get_recommendations(merchant_id="M001", **LAST_30).json()

    assert set(body) == {
        "merchant_id", "requested_start", "requested_end", "has_data",
        "period", "comparison_period", "comparison_basis",
        "recommendation_count", "priority_counts", "notes",
        "recommendations", "unactioned",
    }
    assert body["merchant_id"] == "M001"
    assert body["has_data"] is True
    assert body["recommendation_count"] == len(body["recommendations"])


@needs_real
def test_every_recommendation_has_the_full_contract():
    body = get_recommendations(merchant_id="M003", **LAST_30).json()
    assert body["recommendations"]

    for recommendation in body["recommendations"]:
        assert set(recommendation) == RECOMMENDATION_FIELDS
        assert recommendation["priority"] in {"High", "Medium", "Low"}
        assert recommendation["severity"] in {"HIGH", "MEDIUM", "LOW"}
        assert recommendation["title"] and recommendation["action"]
        assert recommendation["source_finding"], "every action must name its finding"
        assert set(recommendation["period"]) == {"start", "end", "days"}
        assert isinstance(recommendation["evidence"], dict)


@needs_real
def test_recommendations_trace_back_to_real_findings():
    """The ids in `source_finding` must exist in the insights response for the
    same query — the two endpoints must not disagree."""
    recommendations = get_recommendations(merchant_id="M003", **LAST_30).json()
    insights = client.get("/api/insights", params={"merchant_id": "M003", **LAST_30}).json()

    finding_ids = {f["id"] for f in insights["findings"]}
    assert finding_ids

    for recommendation in recommendations["recommendations"]:
        assert recommendation["source_finding"] in finding_ids


@needs_real
def test_unactioned_findings_are_listed_with_reasons():
    body = get_recommendations(merchant_id="M003", **LAST_30).json()
    assert body["unactioned"]

    for entry in body["unactioned"]:
        assert set(entry) == {"finding_id", "category", "severity", "title", "reason"}
        assert entry["reason"]


@needs_real
def test_priority_counts_match_the_list():
    body = get_recommendations(merchant_id="M001", **LAST_30).json()

    assert sum(body["priority_counts"].values()) == body["recommendation_count"]
    for priority, count in body["priority_counts"].items():
        assert count == sum(1 for r in body["recommendations"] if r["priority"] == priority)


@needs_real
def test_recommendations_are_ordered_by_priority():
    body = get_recommendations(merchant_id="M001", **LAST_30).json()
    rank = {"High": 0, "Medium": 1, "Low": 2}
    ranks = [rank[r["priority"]] for r in body["recommendations"]]
    assert ranks == sorted(ranks)


@needs_real
def test_recommendations_response_has_no_nan_or_infinity():
    raw = get_recommendations(merchant_id="M003", **LAST_30).text
    assert "NaN" not in raw
    assert "Infinity" not in raw

    for recommendation in get_recommendations(merchant_id="M003", **LAST_30).json()["recommendations"]:
        for key in ("value", "change"):
            value = recommendation[key]
            if isinstance(value, (int, float)):
                assert math.isfinite(value), f"{recommendation['id']}.{key}"


@needs_real
def test_repeated_recommendation_requests_are_identical():
    first = get_recommendations(merchant_id="M003", **LAST_30).json()
    second = get_recommendations(merchant_id="M003", **LAST_30).json()
    assert first == second


# --------------------------------------------------------------------------
# /api/action-plan
# --------------------------------------------------------------------------
@needs_real
def test_action_plan_returns_200():
    assert get_plan(merchant_id="M001", **LAST_30).status_code == 200


@needs_real
def test_action_plan_response_structure():
    body = get_plan(merchant_id="M001", **LAST_30).json()

    assert set(body) == {
        "merchant_id", "requested_start", "requested_end", "has_data",
        "period", "comparison_period", "comparison_basis",
        "total_available", "included", "truncated", "notes",
        "high", "medium", "low",
    }
    assert body["has_data"] is True


@needs_real
def test_action_plan_buckets_carry_the_right_priority():
    body = get_plan(merchant_id="M001", **LAST_30).json()

    for bucket, expected in (("high", "High"), ("medium", "Medium"), ("low", "Low")):
        for item in body[bucket]:
            assert set(item) == ACTION_ITEM_FIELDS
            assert item["priority"] == expected
            assert item["source_finding"]


@needs_real
def test_action_plan_ranks_are_contiguous_and_ordered():
    body = get_plan(merchant_id="M001", **LAST_30).json()
    items = body["high"] + body["medium"] + body["low"]

    assert body["included"] == len(items)
    assert [item["rank"] for item in items] == list(range(1, len(items) + 1))


@needs_real
def test_action_plan_is_short_enough_to_act_on():
    from backend.app.services.action_plan import MAX_PER_PRIORITY

    body = get_plan(merchant_id="M001", **LAST_30).json()
    assert body["included"] <= sum(MAX_PER_PRIORITY.values())
    assert len(body["high"]) <= MAX_PER_PRIORITY["High"]


@needs_real
def test_action_plan_reports_what_it_left_out():
    body = get_plan(merchant_id="M003", **LAST_30).json()

    assert body["total_available"] >= body["included"]
    if body["truncated"]:
        assert any("most significant" in note for note in body["notes"])


@needs_real
def test_action_plan_items_appear_in_the_recommendations():
    plan = get_plan(merchant_id="M003", **LAST_30).json()
    recommendations = get_recommendations(merchant_id="M003", **LAST_30).json()

    sources = {r["source_finding"] for r in recommendations["recommendations"]}
    for item in plan["high"] + plan["medium"] + plan["low"]:
        assert item["source_finding"] in sources


@needs_real
def test_repeated_plan_requests_are_identical():
    assert get_plan(merchant_id="M003", **LAST_30).json() == get_plan(
        merchant_id="M003", **LAST_30
    ).json()


# --------------------------------------------------------------------------
# M / N / O — invalid and empty input
# --------------------------------------------------------------------------
@needs_real
@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_unknown_merchant_returns_404(endpoint):
    response = client.get(endpoint, params={"merchant_id": "NOPE"})
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


@needs_real
@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_missing_merchant_returns_422(endpoint):
    assert client.get(endpoint).status_code == 422


@needs_real
@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_start_after_end_returns_400(endpoint):
    response = client.get(
        endpoint, params={"merchant_id": "M001", "start": "2026-09-15", "end": "2026-08-17"}
    )
    assert response.status_code == 400
    assert "after end" in response.json()["detail"]


@needs_real
@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_malformed_date_returns_422(endpoint):
    response = client.get(endpoint, params={"merchant_id": "M001", "start": "not-a-date"})
    assert response.status_code == 422


@needs_real
def test_empty_period_returns_empty_recommendations():
    body = get_recommendations(
        merchant_id="M001", start="2020-01-01", end="2020-02-01"
    ).json()

    assert body["has_data"] is False
    assert body["recommendations"] == []
    assert body["unactioned"] == []
    assert body["recommendation_count"] == 0
    assert body["period"] is None


@needs_real
def test_empty_period_returns_empty_plan():
    body = get_plan(merchant_id="M001", start="2020-01-01", end="2020-02-01").json()

    assert body["has_data"] is False
    assert body["high"] == body["medium"] == body["low"] == []
    assert body["included"] == 0
    assert body["truncated"] is False


@needs_real
@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_errors_never_leak_a_traceback(endpoint):
    for params in (
        {"merchant_id": "NOPE"},
        {"merchant_id": "M001", "start": "2026-09-15", "end": "2026-08-17"},
        {"merchant_id": "M001", "start": "garbage"},
    ):
        text = client.get(endpoint, params=params).text
        assert "Traceback" not in text
        assert 'File "' not in text


@pytest.mark.parametrize("endpoint", ["/api/recommendations", "/api/action-plan"])
def test_missing_dataset_returns_503(endpoint, tmp_path, monkeypatch):
    monkeypatch.setattr(
        data_loader,
        "settings",
        SimpleNamespace(sales_path=tmp_path / "gone.csv", customers_path=tmp_path / "gone2.csv"),
    )
    data_loader.clear_cache()

    response = client.get(endpoint, params={"merchant_id": "M001"})
    assert response.status_code == 503
    assert "generate_dataset.py" in response.json()["detail"]


# --------------------------------------------------------------------------
# P — Stage 1-4 endpoints unaffected
# --------------------------------------------------------------------------
@needs_real
def test_existing_endpoints_still_respond():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/merchants").status_code == 200
    assert client.get("/api/dataset/summary").status_code == 200
    assert client.get("/api/dataset/validation").status_code == 200
    assert client.get("/api/dashboard", params={"merchant_id": "M001"}).status_code == 200
    assert client.get("/api/insights", params={"merchant_id": "M001"}).status_code == 200


@needs_real
def test_all_stage_endpoints_agree_on_the_period():
    params = {"merchant_id": "M001", **LAST_30}
    dashboard = client.get("/api/dashboard", params=params).json()
    insights = client.get("/api/insights", params=params).json()
    plan = get_plan(**params).json()

    assert insights["period"] == plan["period"]
    assert plan["period"]["start"] == dashboard["summary"]["period_start"]
    assert plan["period"]["end"] == dashboard["summary"]["period_end"]
