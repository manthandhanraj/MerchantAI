"""Merchant dashboard endpoint (Stage 3).

Thin by design: validate the parameters, narrow the dataset, and hand back what
`services/metrics.py` already computes. There is deliberately no aggregation
logic in this module — a second copy of the maths is how the dashboard and the
assistant end up quoting different numbers for the same thing.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.metrics import daily_metrics, filter_dataset, summary_metrics
from backend.app.utils.calculations import round_money, round_rate

router = APIRouter(prefix="/api", tags=["dashboard"])

# Fields carried in the daily series. Enough for the revenue, profit, orders
# and customer trends without shipping the full frame on every request.
DAILY_MONEY_FIELDS = ("revenue", "expenses", "profit", "average_order_value")
DAILY_COUNT_FIELDS = ("orders", "units_sold", "customers", "new_customers", "repeat_customers")
DAILY_RATE_FIELDS = ("profit_margin", "repeat_customer_rate")


class DashboardSummary(BaseModel):
    """Headline totals. Mirrors `summary_metrics()` exactly."""

    period_start: str | None
    period_end: str | None
    days: int
    total_revenue: float
    total_orders: int
    total_units_sold: int
    total_expenses: float
    total_profit: float
    profit_margin: float
    average_order_value: float
    total_customers: int
    new_customers: int
    repeat_customers: int
    repeat_customer_rate: float
    revenue_per_customer: float
    revenue_growth_rate: float
    active_products: int
    active_categories: int


class DailyPoint(BaseModel):
    date: str
    revenue: float
    expenses: float
    profit: float
    average_order_value: float
    orders: int
    units_sold: int
    customers: int
    new_customers: int
    repeat_customers: int
    profit_margin: float
    repeat_customer_rate: float


class DashboardResponse(BaseModel):
    merchant_id: str
    requested_start: date | None = Field(
        default=None, description="Start date as requested; null means 'from the beginning'."
    )
    requested_end: date | None = Field(
        default=None, description="End date as requested; null means 'to the latest day'."
    )
    has_data: bool = Field(
        description="False when the filters matched no rows. The summary is then all zeros."
    )
    summary: DashboardSummary
    daily: list[DailyPoint]


def _to_daily_points(frame: pd.DataFrame) -> list[DailyPoint]:
    """Convert the daily frame to JSON-safe points.

    Rounding happens here, at the API boundary, so floating-point noise never
    reaches the chart while the stored metrics stay untouched.
    """
    if frame.empty:
        return []

    points: list[DailyPoint] = []
    for row in frame.itertuples(index=False):
        values = {"date": row.date.date().isoformat()}
        for field in DAILY_MONEY_FIELDS:
            values[field] = round_money(getattr(row, field))
        for field in DAILY_COUNT_FIELDS:
            values[field] = int(getattr(row, field))
        for field in DAILY_RATE_FIELDS:
            values[field] = round_rate(getattr(row, field))
        points.append(DailyPoint(**values))
    return points


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    dataset: LoadedDataset,
    merchant_id: str = Query(..., description="Merchant to report on, e.g. 'M001'."),
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)."),
) -> DashboardResponse:
    """Headline metrics and the daily trend series for one merchant.

    A range that matches no data is a valid request with an empty answer, not an
    error: it returns 200 with `has_data: false` and a zeroed summary, so the
    frontend renders an empty state instead of an error state.
    """
    validate_query(dataset, merchant_id, start, end)

    scoped = filter_dataset(dataset, merchant_id=merchant_id, start=start, end=end)

    return DashboardResponse(
        merchant_id=merchant_id,
        requested_start=start,
        requested_end=end,
        has_data=not scoped.is_empty(),
        summary=DashboardSummary(**summary_metrics(scoped)),
        daily=_to_daily_points(daily_metrics(scoped)),
    )
