"""Prioritised action plan.

Turns the full recommendation set into the short High / Medium / Low list the
MVP promises — the answer to "what should I focus on today?".

The plan is deliberately capped. A merchant with twenty suggestions has no plan
at all, so each bucket keeps only its most significant items. Nothing is hidden
silently: `total_available` and `truncated` always report what was left out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from backend.app.services.data_loader import Dataset
from backend.app.services.recommendations import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_ORDER,
    Recommendation,
    RecommendationSet,
    recommend,
)

# How many actions each bucket may carry. Urgent work gets the most room; the
# low bucket is a short tail so the list stays readable in one glance.
MAX_PER_PRIORITY = {
    PRIORITY_HIGH: 3,
    PRIORITY_MEDIUM: 3,
    PRIORITY_LOW: 2,
}


@dataclass(frozen=True)
class ActionItem:
    rank: int
    priority: str
    title: str
    action: str
    reason: str
    category: str
    scope: str
    source_finding: str

    def as_dict(self) -> dict:
        return {
            "rank": self.rank,
            "priority": self.priority,
            "title": self.title,
            "action": self.action,
            "reason": self.reason,
            "category": self.category,
            "scope": self.scope,
            "source_finding": self.source_finding,
        }


@dataclass
class ActionPlan:
    merchant_id: str
    has_data: bool
    period: dict | None
    comparison_period: dict | None
    comparison_basis: str | None
    high: list[ActionItem] = field(default_factory=list)
    medium: list[ActionItem] = field(default_factory=list)
    low: list[ActionItem] = field(default_factory=list)
    total_available: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def items(self) -> list[ActionItem]:
        return [*self.high, *self.medium, *self.low]

    @property
    def included(self) -> int:
        return len(self.items)

    @property
    def truncated(self) -> bool:
        return self.total_available > self.included


def _to_items(recommendations: list[Recommendation], start_rank: int) -> list[ActionItem]:
    return [
        ActionItem(
            rank=start_rank + offset,
            priority=recommendation.priority,
            title=recommendation.title,
            action=recommendation.action,
            reason=recommendation.reason,
            category=recommendation.category,
            scope=recommendation.scope,
            source_finding=recommendation.source_finding,
        )
        for offset, recommendation in enumerate(recommendations)
    ]


def plan_from_recommendations(source: RecommendationSet) -> ActionPlan:
    """Bucket and cap an existing recommendation set.

    `source.recommendations` arrives already ordered by priority, then size of
    move, then id, so taking the first N of each bucket keeps the most
    significant items without any further scoring.
    """
    plan = ActionPlan(
        merchant_id=source.merchant_id,
        has_data=source.has_data,
        period=source.period,
        comparison_period=source.comparison_period,
        comparison_basis=source.comparison_basis,
        total_available=len(source.recommendations),
        notes=list(source.notes),
    )

    buckets: dict[str, list[Recommendation]] = {
        PRIORITY_HIGH: [],
        PRIORITY_MEDIUM: [],
        PRIORITY_LOW: [],
    }
    for recommendation in sorted(
        source.recommendations,
        key=lambda r: (PRIORITY_ORDER[r.priority], -abs(r.change or 0.0), r.id),
    ):
        bucket = buckets[recommendation.priority]
        if len(bucket) < MAX_PER_PRIORITY[recommendation.priority]:
            bucket.append(recommendation)

    rank = 1
    for priority, attribute in (
        (PRIORITY_HIGH, "high"),
        (PRIORITY_MEDIUM, "medium"),
        (PRIORITY_LOW, "low"),
    ):
        items = _to_items(buckets[priority], rank)
        setattr(plan, attribute, items)
        rank += len(items)

    if plan.truncated:
        plan.notes.append(
            f"Showing the {plan.included} most significant of {plan.total_available} "
            f"suggestions. The full list is available from /api/recommendations."
        )

    return plan


def build_action_plan(
    dataset: Dataset,
    merchant_id: str,
    start: date | None = None,
    end: date | None = None,
) -> ActionPlan:
    """Analyse a merchant, map findings to actions, and prioritise them."""
    return plan_from_recommendations(recommend(dataset, merchant_id, start, end))
