"""Growth recommendations: turn findings into actions.

This layer adds no analysis of its own. It consumes the findings produced by
`services/analysis.py` and maps each one to something the merchant can actually
do. Every recommendation names the finding it came from, so any suggestion can
be traced back to the numbers that justified it.

Two rules that shape the wording:

1. **No invented causation.** The analysis establishes *what* changed, never
   *why* — the dataset holds no pricing experiments, marketing spend or
   competitor data. Actions therefore say "review", "check" and "investigate",
   and never assert a cause.
2. **Nothing without a source.** A finding with no sensible action is recorded
   in `unactioned` with the reason, rather than being dropped silently or
   padded out with filler advice.

Deterministic: no randomness, no `today()`, no external calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from backend.app.services.analysis import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    AnalysisReport,
    Finding,
    analyse,
)
from backend.app.services.data_loader import Dataset

PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"

# Priority is taken straight from the finding's severity. The severity
# thresholds are already documented in analysis.py, so introducing a second
# scoring scheme here would only add an unexplainable number.
_PRIORITY_BY_SEVERITY = {
    SEVERITY_HIGH: PRIORITY_HIGH,
    SEVERITY_MEDIUM: PRIORITY_MEDIUM,
    SEVERITY_LOW: PRIORITY_LOW,
}

PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}

# Finding-id prefixes, longest first so "inventory-critical" is matched before
# a hypothetical "inventory". The ids are Stage 4's stable contract.
_KINDS = (
    "total-revenue-up",
    "total-revenue-down",
    "total-orders-up",
    "total-orders-down",
    "total-customers-up",
    "total-customers-down",
    "total-profit-up",
    "total-profit-down",
    "profit-margin-up",
    "profit-margin-down",
    "repeat-rate-up",
    "repeat-rate-down",
    "product-concentration",
    "product-riser",
    "product-faller",
    "product-weak",
    "product-top",
    "category-decline",
    "category-top",
    "inventory-out_of_stock",
    "inventory-critical",
    "inventory-low",
    "trend-peak-day",
    "trend-trough-day",
)


def finding_kind(finding: Finding) -> str | None:
    """Classify a finding by its stable id prefix."""
    for kind in sorted(_KINDS, key=len, reverse=True):
        if finding.id == kind or finding.id.startswith(f"{kind}-"):
            return kind
    return None


# --------------------------------------------------------------------------
# Action templates
#
# `{scope}` is the product, category or "merchant" the finding is about. The
# specific numbers are never duplicated here — they come from the finding and
# are carried on the recommendation's `reason`, `value` and `change` fields.
# --------------------------------------------------------------------------
_ACTIONS: dict[str, tuple[str, str]] = {
    "total-revenue-down": (
        "Act on falling revenue",
        "Work through the product and category items in this plan to see which lines "
        "moved, then choose one recovery action — a targeted promotion, a pricing "
        "review, or outreach to recent customers — and measure it over the next "
        "comparable period.",
    ),
    "total-revenue-up": (
        "Protect the revenue you have gained",
        "Identify which products drove the increase and make sure they stay in stock "
        "and visible. Repeat whatever changed before the gain, and keep measuring it.",
    ),
    "total-orders-down": (
        "Investigate the drop in order volume",
        "Check whether fewer customers are buying or the same customers are buying "
        "less often, using the customer items in this plan. Address whichever of the "
        "two the numbers point to.",
    ),
    "total-orders-up": (
        "Keep order volume climbing",
        "Confirm stock and staffing can carry the higher volume, then keep doing "
        "whatever preceded it.",
    ),
    "total-customers-down": (
        "Rebuild customer footfall",
        "Fewer customer visits were recorded. Re-engage customers who bought recently "
        "and review how visible the business is to new ones.",
    ),
    "total-customers-up": (
        "Convert the extra footfall",
        "More customers are visiting. Review average order value and product mix to "
        "turn those visits into larger baskets.",
    ),
    "total-profit-down": (
        "Defend gross profit",
        "Compare the revenue and margin items in this plan to see whether the fall "
        "came from selling less or from thinner margins, then act on that one.",
    ),
    "total-profit-up": (
        "Reinvest the profit gain",
        "Gross profit improved. Consider putting part of it into stock for the "
        "growing products flagged in this plan.",
    ),
    "profit-margin-down": (
        "Review pricing and cost on the weakest margins",
        "Margin has thinned. Check purchase costs and discounting on the highest-"
        "volume products, since a small change there moves the most money.",
    ),
    "profit-margin-up": (
        "Hold the improved margin",
        "Note what changed in pricing or purchase cost and keep it in place as volume "
        "grows.",
    ),
    "repeat-rate-down": (
        "Win back repeat customers",
        "A smaller share of customers are returning. Run a re-engagement offer for "
        "recent buyers and review what changed in service or availability for them.",
    ),
    "repeat-rate-up": (
        "Build on improving loyalty",
        "More customers are returning. Consider a simple loyalty or reorder prompt to "
        "reinforce the habit.",
    ),
    "product-faller": (
        "Review {scope} before the decline compounds",
        "Check {scope}'s price, placement and promotion, and compare it with your "
        "growing lines. Decide whether to reposition it, bundle it, or move stock and "
        "attention elsewhere.",
    ),
    "product-riser": (
        "Give {scope} more room to grow",
        "{scope} is growing faster than the rest of the range. Keep it in stock, give "
        "it better visibility, and consider widening the variants you carry.",
    ),
    "product-weak": (
        "Decide what to do about {scope}",
        "{scope} contributes very little revenue. Either give it a deliberate push — "
        "pricing, placement, a bundle — or free the stock budget and shelf space for "
        "better performers.",
    ),
    "product-concentration": (
        "Reduce dependence on {scope}",
        "A large share of revenue rests on {scope}. Build up the next strongest "
        "products so a dip in this one line cannot move the whole business.",
    ),
    "category-decline": (
        "Address the decline across {scope}",
        "The fall spans the whole {scope} category, not one product. Review pricing "
        "and range for the category together rather than product by product.",
    ),
    "inventory-out_of_stock": (
        "Restock {scope} now",
        "{scope} has run out and cannot sell until it is replenished. Reorder it "
        "ahead of anything else in this plan.",
    ),
    "inventory-critical": (
        "Reorder {scope} before it runs out",
        "{scope} has only a few days of cover left at its recent selling rate. Place "
        "a replenishment order now, allowing for delivery time.",
    ),
    "inventory-low": (
        "Plan a replenishment for {scope}",
        "{scope} is heading towards a stock-out at its recent selling rate. Schedule a "
        "reorder in the next few days.",
    ),
}

# Findings that are genuine context but not, on their own, something to do.
_NO_ACTION: dict[str, str] = {
    "product-top": (
        "Informational. Knowing the leading product is context; the actions come from "
        "the concentration and inventory items."
    ),
    "category-top": (
        "Informational. Knowing the leading category is context; the actions come from "
        "the product-level items."
    ),
    "trend-peak-day": (
        "A single unusual day is context, not an action. Acting on one day's trading "
        "would be reading noise as a trend."
    ),
    "trend-trough-day": (
        "A single unusual day is context, not an action. Acting on one day's trading "
        "would be reading noise as a trend."
    ),
}


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Recommendation:
    id: str
    title: str
    action: str
    reason: str
    priority: str
    severity: str
    category: str
    scope: str
    metric: str
    value: float
    unit: str
    period: dict
    source_finding: str
    change: float | None = None
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "action": self.action,
            "reason": self.reason,
            "priority": self.priority,
            "severity": self.severity,
            "category": self.category,
            "scope": self.scope,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "change": self.change,
            "period": self.period,
            "source_finding": self.source_finding,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class UnactionedFinding:
    """A finding deliberately left without an action, and why."""

    finding_id: str
    category: str
    severity: str
    title: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
        }


@dataclass
class RecommendationSet:
    merchant_id: str
    has_data: bool
    period: dict | None
    comparison_period: dict | None
    comparison_basis: str | None
    recommendations: list[Recommendation] = field(default_factory=list)
    unactioned: list[UnactionedFinding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def priority_counts(self) -> dict[str, int]:
        counts = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 0, PRIORITY_LOW: 0}
        for recommendation in self.recommendations:
            counts[recommendation.priority] += 1
        return counts


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def _build(finding: Finding, kind: str) -> Recommendation:
    title_template, action_template = _ACTIONS[kind]
    scope = finding.scope if finding.scope != "merchant" else "the business"

    return Recommendation(
        id=f"rec-{finding.id}",
        title=title_template.format(scope=scope),
        action=action_template.format(scope=scope),
        # The reason is the finding, verbatim: what was observed plus the
        # threshold that made it noteworthy. Nothing is added.
        reason=f"{finding.title}. {finding.reason}",
        priority=_PRIORITY_BY_SEVERITY[finding.severity],
        severity=finding.severity,
        category=finding.category,
        scope=finding.scope,
        metric=finding.metric,
        value=finding.value,
        unit=finding.unit,
        change=finding.change,
        period=finding.period.as_dict(),
        source_finding=finding.id,
        # Carried through untouched, so inventory keeps its `inferred: true`
        # marker and nothing here implies a live stock feed.
        evidence=dict(finding.evidence),
    )


def recommendations_from_report(report: AnalysisReport) -> RecommendationSet:
    """Map an existing analysis report onto actions.

    Takes the report rather than a dataset so callers that already ran
    `analyse()` — the action plan, and Stage 6's assistant — do not pay for it
    twice.
    """
    result = RecommendationSet(
        merchant_id=report.merchant_id,
        has_data=report.has_data,
        period=report.period.as_dict() if report.period else None,
        comparison_period=report.comparison_period.as_dict() if report.comparison_period else None,
        comparison_basis=report.comparison_basis,
        notes=list(report.notes),
    )

    for finding in report.findings:
        kind = finding_kind(finding)

        if kind in _ACTIONS:
            result.recommendations.append(_build(finding, kind))
            continue

        explanation = _NO_ACTION.get(kind) or (
            "No action template is defined for this finding type, so no advice is "
            "offered rather than guessing at one."
        )
        result.unactioned.append(
            UnactionedFinding(
                finding_id=finding.id,
                category=finding.category,
                severity=finding.severity,
                title=finding.title,
                reason=explanation,
            )
        )

    # Priority, then size of the move, then id. A total order, so the same
    # inputs always produce the same sequence.
    result.recommendations.sort(
        key=lambda r: (PRIORITY_ORDER[r.priority], -abs(r.change or 0.0), r.id)
    )
    result.unactioned.sort(key=lambda u: u.finding_id)
    return result


def recommend(
    dataset: Dataset,
    merchant_id: str,
    start: date | None = None,
    end: date | None = None,
) -> RecommendationSet:
    """Analyse a merchant and map the findings to actions."""
    return recommendations_from_report(analyse(dataset, merchant_id, start, end))
