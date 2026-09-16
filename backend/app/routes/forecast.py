"""Short-term forecast endpoint (Stage 6).

Thin: validate, call `services/forecasting.py`, serialise. The projection method
and every threshold live in the service.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.forecasting import (
    DEFAULT_HORIZON_DAYS,
    DEFAULT_METRIC,
    FORECASTABLE_METRICS,
    MAX_HORIZON_DAYS,
    forecast as build_forecast,
)

router = APIRouter(prefix="/api", tags=["forecast"])


class PeriodModel(BaseModel):
    start: str
    end: str
    days: int


class ForecastPointModel(BaseModel):
    date: str
    value: float
    weekday: str


class BacktestModel(BaseModel):
    days: int
    mean_absolute_error: float
    mean_absolute_percentage_error: float | None = None
    note: str


class ForecastResponse(BaseModel):
    merchant_id: str
    metric: str
    available: bool = Field(
        description="False when the history is too short. The reason field then explains why."
    )
    reason: str | None = None
    method: str | None = Field(
        default=None, description="The projection method actually used."
    )
    history: PeriodModel | None = None
    forecast_period: PeriodModel | None = None
    points: list[ForecastPointModel] = Field(default_factory=list)
    horizon_days: int = 0
    requested_horizon_days: int = 0
    trend_direction: str | None = Field(
        default=None, description="rising, falling or flat, from the fitted trend."
    )
    trend_per_day: float | None = None
    fit_r_squared: float | None = Field(
        default=None, description="Null for a constant series, which has no variance to explain."
    )
    backtest: BacktestModel | None = Field(
        default=None, description="Measured error on held-out recent days."
    )
    confidence_interval: None = Field(
        default=None,
        description="Always null. This method cannot produce a legitimate interval; "
        "the backtest error is reported instead.",
    )
    history_daily_mean: float | None = None
    forecast_total: float | None = None
    limitations: list[str] = Field(default_factory=list)


@router.get("/forecast", response_model=ForecastResponse)
def forecast_endpoint(
    dataset: LoadedDataset,
    merchant_id: str = Query(..., description="Merchant to forecast, e.g. 'M001'."),
    start: date | None = Query(None, description="Inclusive start of the history (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Inclusive end of the history (YYYY-MM-DD)."),
    metric: str = Query(DEFAULT_METRIC, description=f"One of: {', '.join(FORECASTABLE_METRICS)}."),
    horizon_days: int = Query(
        DEFAULT_HORIZON_DAYS,
        ge=1,
        le=MAX_HORIZON_DAYS,
        description=f"Days to project. Capped at {MAX_HORIZON_DAYS} and at half the history.",
    ),
) -> ForecastResponse:
    """Project one metric forward from the selected history.

    Too little history is a 200 with `available: false` and a reason, not an
    error: the UI renders it as an explained empty state.
    """
    validate_query(dataset, merchant_id, start, end)

    result = build_forecast(
        dataset,
        merchant_id,
        start=start,
        end=end,
        metric=metric,
        horizon_days=horizon_days,
    )
    return ForecastResponse(**result.as_dict())
