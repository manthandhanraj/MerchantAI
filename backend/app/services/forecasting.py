"""Short-term forecasting.

Built on `daily_metrics()` — the same series the dashboard charts. Nothing is
recomputed here; this module only projects the series forward.

**Method: least-squares linear trend with multiplicative day-of-week factors.**

A plain trend or moving average would be simpler, but this dataset has a
measured weekly rhythm: Saturday runs about 1.37x an average day for the fashion
merchant while Tuesday runs 0.77x. A forecast that predicted the same value for
both would be visibly wrong every weekend. The seasonal step is two lines of
arithmetic — group the residual ratios by weekday and take the mean — so the
method stays transparent and hand-checkable. No ML library is involved.

**No confidence intervals.** A least-squares fit can produce them, but only
under assumptions this data violates: daily retail revenue is autocorrelated and
seasonal, so an interval computed that way would look rigorous and mean nothing.
Instead the forecast reports a *measured* error — a holdout backtest on the most
recent days — which is an honest statement of how the method has actually
performed on this merchant.

Deterministic: no randomness, no `today()`. The forecast always starts the day
after the last observed date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from backend.app.services.data_loader import Dataset
from backend.app.services.metrics import daily_metrics, filter_dataset
from backend.app.utils.calculations import round_money, safe_divide

# Metrics that can be projected. All are columns of `daily_metrics()`.
FORECASTABLE_METRICS = ("revenue", "orders", "units_sold", "profit", "customers")
DEFAULT_METRIC = "revenue"

# Two full weeks, so every weekday has at least two observations before a
# seasonal factor is estimated from it.
MIN_HISTORY_DAYS = 14

DEFAULT_HORIZON_DAYS = 7
MAX_HORIZON_DAYS = 14

# A forecast may not reach further than half the history it was fitted on.
HORIZON_HISTORY_DIVISOR = 2

# Days held out to measure error. Skipped when history is too short to spare them.
BACKTEST_DAYS = 7
MIN_DAYS_FOR_BACKTEST = MIN_HISTORY_DAYS + BACKTEST_DAYS

# Trend direction is judged on how far the fitted line moves across the whole
# history, not per day. A drift of 0.15% of an average day sounds negligible but
# compounds to 27% over six months, so the per-day view would call a clearly
# growing merchant "flat".
FLAT_TREND_THRESHOLD = 0.05

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

HORIZON_LIMITATION = (
    f"This is a short-term projection only. The horizon is capped at "
    f"{MAX_HORIZON_DAYS} days and at half the fitted history, because the dataset "
    f"covers months rather than years and carries no yearly seasonality to learn from."
)


@dataclass(frozen=True)
class ForecastPoint:
    date: date
    value: float
    weekday: str

    def as_dict(self) -> dict:
        return {"date": self.date.isoformat(), "value": self.value, "weekday": self.weekday}


@dataclass
class Forecast:
    merchant_id: str
    metric: str
    available: bool
    reason: str | None = None
    method: str | None = None
    history: dict | None = None
    forecast_period: dict | None = None
    points: list[ForecastPoint] = field(default_factory=list)
    horizon_days: int = 0
    requested_horizon_days: int = 0
    trend_direction: str | None = None
    trend_per_day: float | None = None
    fit_r_squared: float | None = None
    backtest: dict | None = None
    # Stated explicitly rather than omitted, so a consumer cannot mistake its
    # absence for an oversight.
    confidence_interval: None = None
    history_daily_mean: float | None = None
    forecast_total: float | None = None
    limitations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "merchant_id": self.merchant_id,
            "metric": self.metric,
            "available": self.available,
            "reason": self.reason,
            "method": self.method,
            "history": self.history,
            "forecast_period": self.forecast_period,
            "points": [p.as_dict() for p in self.points],
            "horizon_days": self.horizon_days,
            "requested_horizon_days": self.requested_horizon_days,
            "trend_direction": self.trend_direction,
            "trend_per_day": self.trend_per_day,
            "fit_r_squared": self.fit_r_squared,
            "backtest": self.backtest,
            "confidence_interval": self.confidence_interval,
            "history_daily_mean": self.history_daily_mean,
            "forecast_total": self.forecast_total,
            "limitations": self.limitations,
        }


def _unavailable(merchant_id: str, metric: str, requested: int, reason: str) -> Forecast:
    return Forecast(
        merchant_id=merchant_id,
        metric=metric,
        available=False,
        reason=reason,
        requested_horizon_days=requested,
        limitations=[HORIZON_LIMITATION],
    )


def _fit(values: np.ndarray) -> tuple[float, float]:
    """Least-squares line through the series. Returns (intercept, slope)."""
    index = np.arange(len(values), dtype="float64")
    slope, intercept = np.polyfit(index, values, 1)
    return float(intercept), float(slope)


def _weekday_factors(values: np.ndarray, weekdays: np.ndarray, fitted: np.ndarray) -> np.ndarray:
    """Average ratio of actual to trend, per weekday, normalised to mean 1.

    Weekdays with no usable observation fall back to 1.0 (no adjustment), which
    is the neutral answer when there is nothing to learn from.
    """
    factors = np.ones(7, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        ratios = np.where(fitted > 0, values / fitted, np.nan)

    for day in range(7):
        selected = ratios[(weekdays == day) & np.isfinite(ratios)]
        if selected.size > 0:
            factors[day] = float(selected.mean())

    mean = float(factors.mean())
    if mean > 0:
        factors = factors / mean
    return factors


def _project(
    intercept: float, slope: float, factors: np.ndarray, start_index: int, days: list[date]
) -> list[float]:
    projected = []
    for offset, day in enumerate(days):
        trend = intercept + slope * (start_index + offset)
        value = trend * factors[day.weekday()]
        # A negative projection is not a forecast, it is the line running out of
        # data. Clamp at zero.
        projected.append(max(float(value), 0.0))
    return projected


def _r_squared(values: np.ndarray, predicted: np.ndarray) -> float | None:
    """None for a constant series: with zero variance there is nothing to explain."""
    total = float(((values - values.mean()) ** 2).sum())
    if total <= 0:
        return None
    residual = float(((values - predicted) ** 2).sum())
    return round(1.0 - residual / total, 4)


def _backtest(values: np.ndarray, weekdays: np.ndarray, holdout: int) -> dict | None:
    """Refit on everything except the last `holdout` days and score those days.

    This is the only accuracy figure the forecast reports, and it is measured
    rather than assumed.
    """
    if len(values) < MIN_DAYS_FOR_BACKTEST:
        return None

    train_values = values[:-holdout]
    train_weekdays = weekdays[:-holdout]
    actual = values[-holdout:]
    actual_weekdays = weekdays[-holdout:]

    intercept, slope = _fit(train_values)
    fitted = intercept + slope * np.arange(len(train_values), dtype="float64")
    factors = _weekday_factors(train_values, train_weekdays, fitted)

    predicted = np.array(
        [
            max((intercept + slope * (len(train_values) + offset)) * factors[weekday], 0.0)
            for offset, weekday in enumerate(actual_weekdays)
        ]
    )

    errors = np.abs(predicted - actual)
    with np.errstate(divide="ignore", invalid="ignore"):
        percentage = np.where(actual > 0, errors / actual, np.nan)
    usable = percentage[np.isfinite(percentage)]

    return {
        "days": int(holdout),
        "mean_absolute_error": round(float(errors.mean()), 2),
        "mean_absolute_percentage_error": round(float(usable.mean()), 4) if usable.size else None,
        "note": (
            "Measured by refitting on the earlier history and scoring the most recent "
            f"{holdout} days. It describes past accuracy, not a guarantee."
        ),
    }


def forecast(
    dataset: Dataset,
    merchant_id: str,
    start: date | None = None,
    end: date | None = None,
    metric: str = DEFAULT_METRIC,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
) -> Forecast:
    """Project one metric forward from the selected history.

    Returns an unavailable forecast — with a reason — rather than raising, so a
    thin history is an answer the UI can render instead of an error.
    """
    requested = int(horizon_days)

    if metric not in FORECASTABLE_METRICS:
        return _unavailable(
            merchant_id,
            metric,
            requested,
            f"'{metric}' cannot be forecast. Available metrics: {', '.join(FORECASTABLE_METRICS)}.",
        )
    if requested < 1:
        return _unavailable(
            merchant_id, metric, requested, "The forecast horizon must be at least 1 day."
        )

    scoped = filter_dataset(dataset, merchant_id=merchant_id, start=start, end=end)
    daily = daily_metrics(scoped)

    if daily.empty:
        return _unavailable(
            merchant_id, metric, requested, "No sales history for this merchant in the selected period."
        )

    history_days = len(daily)
    if history_days < MIN_HISTORY_DAYS:
        return _unavailable(
            merchant_id,
            metric,
            requested,
            f"Only {history_days} day(s) of history in this period. At least "
            f"{MIN_HISTORY_DAYS} are needed before a trend and a weekly pattern can be "
            f"separated from noise.",
        )

    effective_horizon = min(requested, MAX_HORIZON_DAYS, history_days // HORIZON_HISTORY_DIVISOR)
    if effective_horizon < 1:
        return _unavailable(
            merchant_id,
            metric,
            requested,
            f"{history_days} days of history supports no usable horizon.",
        )

    values = daily[metric].astype("float64").to_numpy()
    weekdays = daily["date"].dt.dayofweek.to_numpy()

    intercept, slope = _fit(values)
    index = np.arange(history_days, dtype="float64")
    fitted = intercept + slope * index
    factors = _weekday_factors(values, weekdays, fitted)

    last_date = daily["date"].max().date()
    future_dates = [last_date + timedelta(days=offset + 1) for offset in range(effective_horizon)]
    projected = _project(intercept, slope, factors, history_days, future_dates)

    is_currency = metric in {"revenue", "profit"}
    points = [
        ForecastPoint(
            date=day,
            value=round_money(value) if is_currency else int(round(value)),
            weekday=WEEKDAY_NAMES[day.weekday()],
        )
        for day, value in zip(future_dates, projected)
    ]

    daily_mean = float(values.mean())
    direction = "flat"
    if daily_mean > 0:
        # Total movement of the fitted line across the history, as a share of an
        # average day.
        span = abs(safe_divide(slope * (history_days - 1), daily_mean))
        if span >= FLAT_TREND_THRESHOLD:
            direction = "rising" if slope > 0 else "falling"

    limitations = [
        HORIZON_LIMITATION,
        "No confidence interval is given. A least-squares interval would assume "
        "independent, evenly-scattered errors, which daily retail data does not "
        "satisfy; the backtest error is reported instead.",
        "The projection continues the observed trend and weekly pattern. It cannot "
        "anticipate festivals, promotions, stock-outs or anything else not already "
        "in the history.",
    ]

    return Forecast(
        merchant_id=merchant_id,
        metric=metric,
        available=True,
        method="linear_trend_with_weekday_seasonality",
        history={
            "start": daily["date"].min().date().isoformat(),
            "end": last_date.isoformat(),
            "days": history_days,
        },
        forecast_period={
            "start": future_dates[0].isoformat(),
            "end": future_dates[-1].isoformat(),
            "days": effective_horizon,
        },
        points=points,
        horizon_days=effective_horizon,
        requested_horizon_days=requested,
        trend_direction=direction,
        trend_per_day=round(float(slope), 2),
        fit_r_squared=_r_squared(values, fitted * factors[weekdays]),
        backtest=_backtest(values, weekdays, BACKTEST_DAYS),
        history_daily_mean=round_money(daily_mean) if is_currency else round(daily_mean, 2),
        forecast_total=round_money(sum(p.value for p in points))
        if is_currency
        else int(sum(p.value for p in points)),
        limitations=limitations,
    )
