"""Prioritised action plan endpoint (Stage 5).

The short High / Medium / Low list the dashboard shows. Thin: validate, call
`services/action_plan.py`, serialise.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.app.routes.dependencies import LoadedDataset, validate_query
from backend.app.services.action_plan import build_action_plan

router = APIRouter(prefix="/api", tags=["action-plan"])


class PeriodModel(BaseModel):
    start: str
    end: str
    days: int


class ActionItemModel(BaseModel):
    rank: int = Field(description="1-based position across the whole plan.")
    priority: str
    title: str
    action: str
    reason: str = Field(description="The finding that justifies this, verbatim.")
    category: str
    scope: str
    source_finding: str


class ActionPlanResponse(BaseModel):
    merchant_id: str
    requested_start: date | None = None
    requested_end: date | None = None
    has_data: bool
    period: PeriodModel | None = None
    comparison_period: PeriodModel | None = None
    comparison_basis: str | None = None
    total_available: int = Field(description="Recommendations available before capping.")
    included: int
    truncated: bool
    notes: list[str] = Field(default_factory=list)
    high: list[ActionItemModel]
    medium: list[ActionItemModel]
    low: list[ActionItemModel]


@router.get("/action-plan", response_model=ActionPlanResponse)
def action_plan(
    dataset: LoadedDataset,
    merchant_id: str = Query(..., description="Merchant to plan for, e.g. 'M001'."),
    start: date | None = Query(None, description="Inclusive start date (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Inclusive end date (YYYY-MM-DD)."),
) -> ActionPlanResponse:
    """A short, prioritised list of what to do next.

    Capped per bucket so the plan stays actionable; `total_available` and
    `truncated` report anything left out.
    """
    validate_query(dataset, merchant_id, start, end)

    plan = build_action_plan(dataset, merchant_id, start, end)

    return ActionPlanResponse(
        merchant_id=plan.merchant_id,
        requested_start=start,
        requested_end=end,
        has_data=plan.has_data,
        period=plan.period,
        comparison_period=plan.comparison_period,
        comparison_basis=plan.comparison_basis,
        total_available=plan.total_available,
        included=plan.included,
        truncated=plan.truncated,
        notes=plan.notes,
        high=[item.as_dict() for item in plan.high],
        medium=[item.as_dict() for item in plan.medium],
        low=[item.as_dict() for item in plan.low],
    )
