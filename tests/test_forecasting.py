"""Forecasting engine (Stage 6).

Controlled datasets are used where the shape must be exact; the real generated
dataset confirms the projection reaches the right conclusions about the demo
merchants.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.services import forecasting as F
from backend.app.services.forecasting import (
    MAX_HORIZON_DAYS,
    MIN_HISTORY_DAYS,
    forecast,
)
from backend.app.services.metrics import daily_metrics, filter_dataset
from tests.test_analysis import build_dataset

START = date(2026, 1, 1)


def dataset_of(tmp_path, units, price=100.0, **kwargs):
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": price, "units": units, **kwargs}],
    )


# --------------------------------------------------------------------------
# 1 / 2 — a forecast is produced, and it is deterministic
# --------------------------------------------------------------------------
@pytest.fixture
def steady(tmp_path):
    """60 days of gently rising trade."""
    return dataset_of(tmp_path, [20 + index // 6 for index in range(60)])


def test_forecast_is_produced(steady):
    result = forecast(steady, "M001")

    assert result.available is True
    assert result.method == "linear_trend_with_weekday_seasonality"
    assert len(result.points) == result.horizon_days
    assert all(point.value >= 0 for point in result.points)


def test_same_input_produces_identical_output(steady):
    assert forecast(steady, "M001").as_dict() == forecast(steady, "M001").as_dict()


def test_repeated_calls_do_not_drift(steady):
    values = [tuple(p.value for p in forecast(steady, "M001").points) for _ in range(3)]
    assert len(set(values)) == 1


# --------------------------------------------------------------------------
# 3 — too little history
# --------------------------------------------------------------------------
def test_short_history_is_refused_with_a_reason(tmp_path):
    dataset = dataset_of(tmp_path, [20] * 5)
    result = forecast(dataset, "M001")

    assert result.available is False
    assert result.points == []
    assert "5 day(s) of history" in result.reason
    assert str(MIN_HISTORY_DAYS) in result.reason


def test_exactly_the_minimum_history_is_accepted(tmp_path):
    dataset = dataset_of(tmp_path, [20] * MIN_HISTORY_DAYS)
    assert forecast(dataset, "M001").available is True


def test_one_day_below_the_minimum_is_refused(tmp_path):
    dataset = dataset_of(tmp_path, [20] * (MIN_HISTORY_DAYS - 1))
    assert forecast(dataset, "M001").available is False


def test_empty_selection_is_refused_with_a_reason(steady):
    result = forecast(steady, "M001", date(2020, 1, 1), date(2020, 2, 1))

    assert result.available is False
    assert "No sales history" in result.reason


def test_unknown_merchant_is_refused_by_the_service(steady):
    """The service reports emptiness; rejecting unknown ids is the route's job."""
    assert forecast(steady, "NOPE").available is False


def test_unavailable_forecast_still_states_the_horizon_limit(tmp_path):
    dataset = dataset_of(tmp_path, [20] * 5)
    result = forecast(dataset, "M001")
    assert any("short-term" in note for note in result.limitations)


# --------------------------------------------------------------------------
# 4 — horizon enforcement
# --------------------------------------------------------------------------
def test_horizon_is_capped_at_the_maximum(steady):
    result = forecast(steady, "M001", horizon_days=MAX_HORIZON_DAYS + 50)

    assert result.requested_horizon_days == MAX_HORIZON_DAYS + 50
    assert result.horizon_days == MAX_HORIZON_DAYS
    assert len(result.points) == MAX_HORIZON_DAYS


def test_horizon_is_capped_at_half_the_history(tmp_path):
    dataset = dataset_of(tmp_path, [20] * 20)  # 20 days of history
    result = forecast(dataset, "M001", horizon_days=MAX_HORIZON_DAYS)
    assert result.horizon_days == 10


def test_smaller_horizon_is_honoured(steady):
    result = forecast(steady, "M001", horizon_days=3)
    assert result.horizon_days == 3
    assert len(result.points) == 3


def test_zero_horizon_is_rejected(steady):
    result = forecast(steady, "M001", horizon_days=0)
    assert result.available is False
    assert "at least 1 day" in result.reason


# --------------------------------------------------------------------------
# 5 — no current-date dependency
# --------------------------------------------------------------------------
def test_forecast_starts_the_day_after_the_history_not_today(steady):
    """A `today()` dependency would make the output change overnight."""
    result = forecast(steady, "M001")

    history_end = date.fromisoformat(result.history["end"])
    assert date.fromisoformat(result.forecast_period["start"]) == history_end + timedelta(days=1)
    assert result.points[0].date == history_end + timedelta(days=1)
    # The fixture history ends in early 2026, so a today()-based forecast would
    # start somewhere quite different.
    assert result.points[0].date != date.today()


def test_forecast_dates_are_consecutive(steady):
    points = forecast(steady, "M001").points
    for earlier, later in zip(points, points[1:]):
        assert later.date == earlier.date + timedelta(days=1)


def test_no_module_uses_today(steady):
    import inspect

    source = inspect.getsource(F)
    assert "date.today" not in source
    assert "datetime.now" not in source


# --------------------------------------------------------------------------
# 6 — the existing daily series is reused, not recomputed
# --------------------------------------------------------------------------
def test_history_matches_daily_metrics(steady):
    result = forecast(steady, "M001")
    daily = daily_metrics(filter_dataset(steady, "M001"))

    assert result.history["days"] == len(daily)
    assert result.history["start"] == daily["date"].min().date().isoformat()
    assert result.history["end"] == daily["date"].max().date().isoformat()
    assert result.history_daily_mean == pytest.approx(
        round(float(daily["revenue"].mean()), 2), abs=0.01
    )


def test_every_forecastable_metric_comes_from_the_daily_frame(steady):
    daily = daily_metrics(filter_dataset(steady, "M001"))
    for metric in F.FORECASTABLE_METRICS:
        assert metric in daily.columns
        assert forecast(steady, "M001", metric=metric).available is True


def test_unknown_metric_is_refused(steady):
    result = forecast(steady, "M001", metric="unicorns")
    assert result.available is False
    assert "cannot be forecast" in result.reason


# --------------------------------------------------------------------------
# Method behaviour
# --------------------------------------------------------------------------
def test_rising_series_is_reported_as_rising(tmp_path):
    dataset = dataset_of(tmp_path, [10 + index for index in range(60)])
    assert forecast(dataset, "M001").trend_direction == "rising"


def test_falling_series_is_reported_as_falling(tmp_path):
    dataset = dataset_of(tmp_path, [80 - index for index in range(60)])
    assert forecast(dataset, "M001").trend_direction == "falling"


def test_constant_series_is_reported_as_flat(tmp_path):
    dataset = dataset_of(tmp_path, [20] * 60)
    result = forecast(dataset, "M001")

    assert result.trend_direction == "flat"
    # Zero variance means there is nothing for a fit to explain.
    assert result.fit_r_squared is None


def test_constant_series_still_forecasts_the_same_value(tmp_path):
    dataset = dataset_of(tmp_path, [20] * 60)
    values = {point.value for point in forecast(dataset, "M001").points}
    assert len(values) == 1
    assert values.pop() == pytest.approx(2000.0, abs=1.0)


def test_weekday_pattern_is_carried_into_the_forecast(tmp_path):
    """Saturdays trade at triple. A projection that ignored that would be
    visibly wrong every weekend."""
    units = [60 if (START + timedelta(days=i)).weekday() == 5 else 20 for i in range(70)]
    dataset = dataset_of(tmp_path, units)

    points = forecast(dataset, "M001", horizon_days=7).points
    saturday = next(p for p in points if p.weekday == "Saturday")
    others = [p.value for p in points if p.weekday != "Saturday"]

    assert saturday.value > max(others) * 2


def test_projection_never_goes_negative(tmp_path):
    """A steep decline runs the fitted line below zero; that is the line running
    out of data, not a forecast of negative revenue."""
    units = [max(60 - index * 2, 1) for index in range(30)]
    dataset = dataset_of(tmp_path, units)

    assert all(point.value >= 0 for point in forecast(dataset, "M001").points)


# --------------------------------------------------------------------------
# Honesty about accuracy
# --------------------------------------------------------------------------
def test_no_confidence_interval_is_invented(steady):
    """The method cannot produce a legitimate interval, so it must not imply one."""
    result = forecast(steady, "M001")
    assert result.confidence_interval is None
    assert result.as_dict()["confidence_interval"] is None
    assert any("confidence interval" in note.lower() for note in result.limitations)


def test_backtest_reports_measured_error(steady):
    backtest = forecast(steady, "M001").backtest

    assert backtest is not None
    assert backtest["days"] == F.BACKTEST_DAYS
    assert backtest["mean_absolute_error"] >= 0
    assert "past accuracy" in backtest["note"]


def test_backtest_is_skipped_when_history_cannot_spare_the_days(tmp_path):
    dataset = dataset_of(tmp_path, [20] * MIN_HISTORY_DAYS)
    assert forecast(dataset, "M001").backtest is None


def test_limitations_are_always_stated(steady):
    result = forecast(steady, "M001")
    assert len(result.limitations) >= 3
    assert any("festivals" in note or "promotions" in note for note in result.limitations)


# --------------------------------------------------------------------------
# Real dataset
# --------------------------------------------------------------------------
def _real_dataset():
    from backend.app.config import settings
    from backend.app.services.data_loader import read_dataset

    if not (settings.sales_path.exists() and settings.customers_path.exists()):
        return None
    return read_dataset(settings.sales_path, settings.customers_path)


REAL = _real_dataset()
needs_real = pytest.mark.skipif(REAL is None, reason="dataset not generated")


@needs_real
@pytest.mark.parametrize(
    ("merchant_id", "expected"),
    [("M001", "rising"), ("M003", "falling"), ("M004", "rising")],
)
def test_real_merchants_trend_as_designed(merchant_id, expected):
    assert forecast(REAL, merchant_id).trend_direction == expected


@needs_real
@pytest.mark.parametrize("merchant_id", ["M001", "M002", "M003", "M004"])
def test_every_real_merchant_forecasts_cleanly(merchant_id):
    import math

    result = forecast(REAL, merchant_id)

    assert result.available is True
    assert result.points
    for point in result.points:
        assert math.isfinite(point.value)
        assert point.value >= 0
    assert result.backtest is not None


@needs_real
def test_real_forecast_is_deterministic():
    assert forecast(REAL, "M003").as_dict() == forecast(REAL, "M003").as_dict()


@needs_real
def test_real_weekend_uplift_survives_into_the_forecast():
    """M004 trades far harder at weekends; the projection should say so."""
    points = forecast(REAL, "M004", horizon_days=7).points
    weekend = [p.value for p in points if p.weekday in {"Saturday", "Sunday"}]
    weekday = [p.value for p in points if p.weekday in {"Monday", "Tuesday", "Wednesday"}]

    assert min(weekend) > max(weekday)
