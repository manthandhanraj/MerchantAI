"""Business insights endpoint (Stage 4).

Thin by design: validate, call `services/analysis.py`, serialise. All analysis
rules and thresholds live in the service, so the same findings are available to
Stage 5's recommendations and Stage 6's assistant without going through HTTP.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.analysis import analyse

router = APIRouter(prefix="/api", tags=["insights"])


class PeriodModel(BaseModel):
    start: str
    end: str
    days: int


class FindingModel(BaseModel):
    id: str = Field(description="Stable identifier; the same finding keeps the same id.")
    category: str = Field(description="Revenue, Orders, Customers, Profit, Product, Category, Inventory or Trend.")
    severity: str = Field(description="HIGH, MEDIUM or LOW, from documented thresholds.")
    title: str
    description: str
    metric: str
    value: float
    unit: str = Field(description="currency, count, rate or days.")
    scope: str = Field(description="'merchant', or the product/category this is about.")
    reason: str = Field(description="Which threshold made this noteworthy.")
    period: PeriodModel
    change: float | None = None
    comparison_value: float | None = None
    evidence: dict = Field(default_factory=dict)


class InsightsResponse(BaseModel):
    merchant_id: str
    requested_start: date | None = None
    requested_end: date | None = None
    has_data: bool
    period: PeriodModel | None = None
    comparison_period: PeriodModel | None = None
    comparison_basis: str | None = Field(
        default=None,
        description="'previous_period' when a true prior window exists, "
        "'within_period' when the selection was split in half instead.",
    )
    finding_count: int
    severity_counts: dict[str, int]
    notes: list[str] = Field(
        default_factory=list,
        description="Limits of this analysis, e.g. that no baseline period was available.",
    )
    findings: list[FindingModel]


@router.get("/insights", response_model=InsightsResponse)
def insights(
    dataset: LoadedDataset,
    merchant_id: str = Query(..., description="Merchant to analyse, e.g. 'M001'."),
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)."),
) -> InsightsResponse:
    """Explainable business findings for one merchant over a period.

    A period with no data returns 200 with `has_data: false` and no findings —
    an empty answer, not an error.
    """
    validate_query(dataset, merchant_id, start, end)

    report = analyse(dataset, merchant_id, start, end)

    return InsightsResponse(
        merchant_id=report.merchant_id,
        requested_start=start,
        requested_end=end,
        has_data=report.has_data,
        period=report.period.as_dict() if report.period else None,
        comparison_period=report.comparison_period.as_dict() if report.comparison_period else None,
        comparison_basis=report.comparison_basis,
        finding_count=len(report.findings),
        severity_counts=report.severity_counts,
        notes=report.notes,
        findings=[finding.as_dict() for finding in report.findings],
    )
