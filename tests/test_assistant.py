"""AI business assistant (Stage 6).

Everything here runs offline. The default configuration has `LLM_ENABLED=false`,
and the tests that exercise the model path substitute a fake `complete()` —
no test may reach a network.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.services import assistant as A
from backend.app.services.assistant import (
    STARTER_QUESTIONS,
    answer_from_context,
    ask,
    build_context,
    detect_intent,
    unsupported_numbers,
)
from backend.app.services.llm import LLMError
from tests.test_analysis import build_dataset

LAST_30 = (date(2026, 8, 17), date(2026, 9, 15))


def _real_dataset():
    from backend.app.config import settings
    from backend.app.services.data_loader import read_dataset

    if not (settings.sales_path.exists() and settings.customers_path.exists()):
        return None
    return read_dataset(settings.sales_path, settings.customers_path)


REAL = _real_dataset()
needs_real = pytest.mark.skipif(REAL is None, reason="dataset not generated")


@pytest.fixture
def small(tmp_path):
    """A short history: enough to analyse, too short to forecast."""
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": [20] * 8}],
    )


@pytest.fixture(autouse=True)
def llm_off(monkeypatch):
    """Guarantee no test reaches a provider unless it opts in explicitly."""

    def explode(*_args, **_kwargs):
        raise AssertionError("complete() must not be called while the LLM is disabled")

    monkeypatch.setattr(A, "is_enabled", lambda: False)
    monkeypatch.setattr(A, "complete", explode)


# --------------------------------------------------------------------------
# 10-15 — the context is assembled from the existing services
# --------------------------------------------------------------------------
@needs_real
def test_context_contains_summary_metrics():
    summary = build_context(REAL, "M003", *LAST_30)["summary"]
    for key in ("total_revenue", "total_orders", "total_customers", "total_profit",
                "average_order_value", "profit_margin", "repeat_customer_rate"):
        assert key in summary


@needs_real
def test_context_contains_daily_metrics():
    daily = build_context(REAL, "M003", *LAST_30)["daily_recent"]

    assert daily
    assert len(daily) <= A.CONTEXT_DAILY_DAYS
    assert set(daily[0]) == {"date", "revenue", "orders", "customers"}


@needs_real
def test_context_contains_analysis_findings():
    findings = build_context(REAL, "M003", *LAST_30)["findings"]

    assert findings
    assert {"id", "category", "severity", "title", "reason"} <= set(findings[0])


@needs_real
def test_context_contains_recommendations():
    recommendations = build_context(REAL, "M003", *LAST_30)["recommendations"]

    assert recommendations
    assert {"title", "action", "priority", "source_finding"} <= set(recommendations[0])


@needs_real
def test_context_contains_action_plan():
    plan = build_context(REAL, "M003", *LAST_30)["action_plan"]

    assert set(plan) == {"high", "medium", "low", "total_available"}
    assert plan["total_available"] > 0


@needs_real
def test_context_contains_forecast():
    projection = build_context(REAL, "M003", *LAST_30)["forecast"]

    assert projection["available"] is True
    assert projection["method"] == "linear_trend_with_weekday_seasonality"
    assert projection["points"]


@needs_real
def test_context_runs_the_analysis_only_once(monkeypatch):
    """Regression: `recommend()` and `build_action_plan()` each re-derive the
    analysis, so calling all three ran `analyse()` three times for one answer
    (184ms -> 77ms once chained through the composable entry points)."""
    calls = {"count": 0}
    original = A.analyse

    def counting(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(A, "analyse", counting)
    build_context(REAL, "M003", *LAST_30)

    assert calls["count"] == 1, f"analyse() ran {calls['count']} times for one context"


@needs_real
def test_context_contains_supporting_products_and_limitations():
    context = build_context(REAL, "M003", *LAST_30)

    assert context["top_products"]
    assert {"product", "revenue", "revenue_share"} <= set(context["top_products"][0])
    assert len(context["limitations"]) >= 5


@needs_real
def test_context_numbers_match_the_dashboard_services():
    """The assistant must not hold a second, divergent set of numbers."""
    from backend.app.services.metrics import filter_dataset, summary_metrics

    context = build_context(REAL, "M003", *LAST_30)
    expected = summary_metrics(filter_dataset(REAL, "M003", *LAST_30))
    assert context["summary"] == expected


def test_empty_period_produces_an_empty_context(small):
    context = build_context(small, "M001", date(2020, 1, 1), date(2020, 2, 1))

    assert context["has_data"] is False
    assert context["period"] is None
    assert context["limitations"]


# --------------------------------------------------------------------------
# 20 — an unavailable forecast is represented, not hidden
# --------------------------------------------------------------------------
def test_short_history_context_marks_the_forecast_unavailable(small):
    projection = build_context(small, "M001")["forecast"]

    assert projection["available"] is False
    assert projection["reason"]
    assert projection["points"] == []


def test_assistant_explains_an_unavailable_forecast(small):
    result = ask(small, "M001", "What's the forecast for the coming days?")

    assert "No forecast is available" in result.answer
    assert "history" in result.answer.lower()


# --------------------------------------------------------------------------
# Intent routing and answers
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Why did my sales decrease?", "decline"),
        ("Which product is performing best?", "best_product"),
        ("What should I focus on today?", "focus"),
        ("How can I improve next week's revenue?", "improve"),
        ("What's the forecast for the coming days?", "forecast"),
        ("Am I going to run out of stock?", "inventory"),
        ("How are my repeat customers?", "customers"),
        ("How is the business doing?", "summary"),
        ("", "summary"),
    ],
)
def test_intent_routing(question, expected):
    assert detect_intent(question) == expected


def test_improve_beats_forecast_for_next_week_questions():
    """"How can I improve next week's revenue?" asks for actions, not a projection."""
    assert detect_intent("How can I improve next week's revenue?") == "improve"


@needs_real
@pytest.mark.parametrize("question", STARTER_QUESTIONS)
def test_every_starter_question_is_answered(question):
    result = ask(REAL, "M003", question, *LAST_30)

    assert result.answer
    assert len(result.answer) > 60
    assert result.source == A.SOURCE_DETERMINISTIC
    assert result.grounded_in


@needs_real
def test_decline_answer_refuses_to_assert_a_cause():
    result = ask(REAL, "M003", "Why did my sales decrease?", *LAST_30)
    assert "not why" in result.answer or "establish a cause" in result.answer


@needs_real
def test_best_product_answer_names_the_leader():
    result = ask(REAL, "M003", "Which product is performing best?", *LAST_30)
    assert "Cold Coffee" in result.answer


@needs_real
def test_focus_answer_uses_the_action_plan():
    result = ask(REAL, "M003", "What should I focus on today?", *LAST_30)
    assert "action" in result.answer.lower()
    assert result.grounded_in == ["action_plan"]


def test_empty_period_answer_says_so(small):
    result = ask(small, "M001", "How is the business doing?", date(2020, 1, 1), date(2020, 2, 1))

    assert result.has_data is False
    assert "no sales data" in result.answer.lower()


# --------------------------------------------------------------------------
# 16 / 17 — disabled LLM never calls out, and answers offline
# --------------------------------------------------------------------------
@needs_real
def test_disabled_llm_never_calls_the_provider():
    """The autouse fixture makes `complete()` raise if it is ever reached."""
    result = ask(REAL, "M001", "How is the business doing?", *LAST_30)

    assert result.llm_enabled is False
    assert result.source == A.SOURCE_DETERMINISTIC
    assert result.answer


@needs_real
def test_disabled_llm_produces_no_warning():
    """Disabled is the normal state, not a degradation to apologise for."""
    assert ask(REAL, "M001", "How is the business doing?", *LAST_30).warnings == []


@needs_real
def test_offline_answers_are_deterministic():
    first = ask(REAL, "M003", "Why did my sales decrease?", *LAST_30)
    second = ask(REAL, "M003", "Why did my sales decrease?", *LAST_30)
    assert first.as_dict() == second.as_dict()


# --------------------------------------------------------------------------
# 18 — provider failure is contained
# --------------------------------------------------------------------------
@needs_real
def test_llm_failure_falls_back_to_the_offline_answer(monkeypatch):
    def fail(*_args, **_kwargs):
        raise LLMError("provider is down")

    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(A, "complete", fail)

    result = ask(REAL, "M001", "How is the business doing?", *LAST_30)

    assert result.source == A.SOURCE_DETERMINISTIC
    assert result.answer
    assert any("provider is down" in warning for warning in result.warnings)


@needs_real
def test_llm_failure_does_not_raise(monkeypatch):
    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(A, "complete", lambda *a, **k: (_ for _ in ()).throw(LLMError("boom")))

    assert ask(REAL, "M001", "hello", *LAST_30).answer  # no exception


# --------------------------------------------------------------------------
# 19 — the model cannot invent numbers
# --------------------------------------------------------------------------
@needs_real
def test_invented_numbers_are_rejected(monkeypatch):
    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(
        A, "complete", lambda *a, **k: "Your revenue was 9999999 from 45231 customers."
    )

    result = ask(REAL, "M001", "How is the business doing?", *LAST_30)

    assert result.source == A.SOURCE_DETERMINISTIC, "an unverifiable reply must not be shown"
    assert "9999999" not in result.answer
    assert any("could not be traced" in warning for warning in result.warnings)


@needs_real
def test_grounded_llm_answer_is_accepted(monkeypatch):
    context = build_context(REAL, "M001", *LAST_30)
    revenue = context["summary"]["total_revenue"]
    reply = f"Revenue for the period was {revenue:.2f}, which is solid."

    monkeypatch.setattr(A, "is_enabled", lambda: True)
    monkeypatch.setattr(A, "complete", lambda *a, **k: reply)

    result = ask(REAL, "M001", "How is the business doing?", *LAST_30)

    assert result.source == A.SOURCE_LLM
    assert result.answer == reply
    assert result.warnings == []


@needs_real
def test_number_verification_accepts_real_figures():
    context = build_context(REAL, "M003", *LAST_30)
    assert unsupported_numbers("Revenue fell 16.1% over the period.", context) == []


@needs_real
def test_number_verification_accepts_percentages_written_as_magnitudes():
    """Context stores -0.161; prose writes "fell 16.1%". Both must pass."""
    context = build_context(REAL, "M003", *LAST_30)
    assert unsupported_numbers("Repeat rate slipped 7.3 points to 60.1%.", context) == []


@needs_real
def test_number_verification_catches_fabrication():
    context = build_context(REAL, "M003", *LAST_30)
    flagged = unsupported_numbers("You earned 123456789 last week.", context)
    assert "123456789" in flagged


def test_calendar_references_are_not_flagged():
    context = {"has_data": True, "summary": {"total_revenue": 1000.0}}
    assert unsupported_numbers("Over the last 7 days and the 30 before that.", context) == []


@needs_real
@pytest.mark.parametrize("merchant_id", ["M001", "M002", "M003", "M004"])
def test_every_offline_answer_is_itself_grounded(merchant_id):
    """The deterministic path must satisfy the same rule it enforces on the model."""
    context = build_context(REAL, merchant_id, *LAST_30)
    for question in STARTER_QUESTIONS:
        answer, _ = answer_from_context(question, context)
        assert unsupported_numbers(answer, context) == [], f"{merchant_id}: {question}"


# --------------------------------------------------------------------------
# Prompt construction
# --------------------------------------------------------------------------
@needs_real
def test_system_prompt_forbids_invention_and_causation():
    prompt = A.SYSTEM_PROMPT.lower()
    assert "never estimate, extrapolate or invent" in prompt
    assert "never assert a cause" in prompt


@needs_real
def test_prompt_carries_the_context():
    context = build_context(REAL, "M001", *LAST_30)
    prompt = A.build_prompt("How is trade?", context)

    assert "How is trade?" in prompt
    assert "total_revenue" in prompt
