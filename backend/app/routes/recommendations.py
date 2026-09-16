"""Growth recommendations endpoint (Stage 5).

Thin: validate, call `services/recommendations.py`, serialise. The mapping from
findings to actions lives entirely in the service.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.recommendations import recommend

router = APIRouter(prefix="/api", tags=["recommendations"])


class PeriodModel(BaseModel):
    start: str
    end: str
    days: int


class RecommendationModel(BaseModel):
    id: str
    title: str
    action: str = Field(description="What to do. Never asserts why something happened.")
    reason: str = Field(description="The finding that justifies this, verbatim.")
    priority: str = Field(description="High, Medium or Low, taken from the finding's severity.")
    severity: str
    category: str
    scope: str = Field(description="'merchant', or the product/category this concerns.")
    metric: str
    value: float
    unit: str
    change: float | None = None
    period: PeriodModel
    source_finding: str = Field(description="Id of the finding this came from.")
    evidence: dict = Field(default_factory=dict)


class UnactionedModel(BaseModel):
    finding_id: str
    category: str
    severity: str
    title: str
    reason: str = Field(description="Why this finding produced no action.")


class RecommendationsResponse(BaseModel):
    merchant_id: str
    requested_start: date | None = None
    requested_end: date | None = None
    has_data: bool
    period: PeriodModel | None = None
    comparison_period: PeriodModel | None = None
    comparison_basis: str | None = None
    recommendation_count: int
    priority_counts: dict[str, int]
    notes: list[str] = Field(default_factory=list)
    recommendations: list[RecommendationModel]
    unactioned: list[UnactionedModel] = Field(
        default_factory=list,
        description="Findings deliberately left without an action, each with the reason.",
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(
    dataset: LoadedDataset,
    merchant_id: str = Query(..., description="Merchant to advise, e.g. 'M001'."),
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)."),
) -> RecommendationsResponse:
    """Actionable suggestions for one merchant, each traceable to a finding.

    A period with no data returns 200 with `has_data: false` and no
    recommendations — an empty answer, not an error.
    """
    validate_query(dataset, merchant_id, start, end)

    result = recommend(dataset, merchant_id, start, end)

    return RecommendationsResponse(
        merchant_id=result.merchant_id,
        requested_start=start,
        requested_end=end,
        has_data=result.has_data,
        period=result.period,
        comparison_period=result.comparison_period,
        comparison_basis=result.comparison_basis,
        recommendation_count=len(result.recommendations),
        priority_counts=result.priority_counts,
        notes=result.notes,
        recommendations=[r.as_dict() for r in result.recommendations],
        unactioned=[u.as_dict() for u in result.unactioned],
    )
