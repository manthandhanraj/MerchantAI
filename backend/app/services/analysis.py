"""Business analysis: turn computed metrics into explainable findings.

This layer answers "why is this happening" on top of the "what is happening"
that `metrics.py` already reports. It computes nothing itself — every number in
every finding comes from an existing Stage 2 service, so an insight can never
contradict the dashboard.

Three rules the whole module follows:

1. **Deterministic.** No randomness, no `today()`. The same merchant, dates and
   dataset always produce the same findings in the same order.
2. **Evidence or silence.** A finding is emitted only when the data supports it.
   Where the data cannot support a conclusion, that is recorded as a note rather
   than guessed at.
3. **Every finding explains itself.** It carries what happened, where, how big,
   over which period, and which documented threshold made it noteworthy.

No FastAPI imports: this must stay usable outside a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from backend.app.services.data_loader import Dataset
from backend.app.services.metrics import (
    CRITICAL_COVER_DAYS,
    LOW_COVER_DAYS,
    category_performance,
    daily_metrics,
    filter_dataset,
    inventory_position,
    product_performance,
    summary_metrics,
)
from backend.app.utils.calculations import growth_rate, round_money, round_rate, safe_divide

# --------------------------------------------------------------------------
# Severity thresholds
#
# All documented here so the rules are auditable and easy to retune. Nothing
# below these floors is reported at all: a 2% move on a noisy daily series is
# not a business event, and filling the page with it buries the real findings.
# --------------------------------------------------------------------------
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

_SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}

# Relative change in a total (revenue, orders, visits, profit), period on period.
CHANGE_LOW = 0.05
CHANGE_MEDIUM = 0.10
CHANGE_HIGH = 0.20

# Change in a rate (margin, repeat rate) measured in percentage POINTS.
# A rate that moves from 30% to 33% has risen 3 points, not 10% — using the
# relative scale here would badly overstate small moves on small rates.
POINTS_LOW = 0.015
POINTS_MEDIUM = 0.030
POINTS_HIGH = 0.050

# Share of merchant revenue held by a single product.
CONCENTRATION_MEDIUM = 0.35
CONCENTRATION_HIGH = 0.50

# A product earning less than this share of revenue is flagged as weak.
WEAK_SHARE = 0.05

# Daily revenue this many standard deviations from the period mean is unusual.
OUTLIER_SIGMA = 2.0

# Minimum sizes before a rule is allowed to draw a conclusion.
MIN_DAYS_FOR_COMPARISON = 4  # 2 days each side of a within-period split
MIN_DAYS_FOR_OUTLIER = 14
MIN_PRODUCTS_FOR_RANKING = 2

CATEGORY_REVENUE = "Revenue"
CATEGORY_ORDERS = "Orders"
CATEGORY_CUSTOMERS = "Customers"
CATEGORY_PROFIT = "Profit"
CATEGORY_PRODUCT = "Product"
CATEGORY_CATEGORY = "Category"
CATEGORY_INVENTORY = "Inventory"
CATEGORY_TREND = "Trend"

BASIS_PREVIOUS = "previous_period"
BASIS_WITHIN = "within_period"


# --------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Period:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def as_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat(), "days": self.days}


@dataclass(frozen=True)
class Finding:
    """One explainable business observation."""

    id: str
    category: str
    severity: str
    title: str
    description: str
    metric: str
    value: float
    unit: str  # "currency" | "count" | "rate" | "days"
    scope: str  # "merchant", or the product/category the finding is about
    reason: str  # which threshold made this noteworthy
    period: Period
    change: float | None = None
    comparison_value: float | None = None
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "scope": self.scope,
            "reason": self.reason,
            "period": self.period.as_dict(),
            "change": self.change,
            "comparison_value": self.comparison_value,
            "evidence": self.evidence,
        }


@dataclass
class AnalysisReport:
    merchant_id: str
    has_data: bool
    period: Period | None
    comparison_period: Period | None
    comparison_basis: str | None
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def severity_counts(self) -> dict[str, int]:
        counts = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 0, SEVERITY_LOW: 0}
        for finding in self.findings:
            counts[finding.severity] += 1
        return counts


# --------------------------------------------------------------------------
# Formatting helpers (used inside finding text, not for API values)
# --------------------------------------------------------------------------
def _indian_group(number: int) -> str:
    """Group digits the Indian way: 17518564 -> 1,75,18,564."""
    digits = str(abs(int(number)))
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return f"{','.join(parts)},{tail}"


def _inr(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}₹{_indian_group(round(abs(value)))}"


def _pct(fraction: float, decimals: int = 1) -> str:
    return f"{fraction * 100:.{decimals}f}%"


def _points(fraction: float, decimals: int = 1) -> str:
    return f"{abs(fraction) * 100:.{decimals}f} points"


def _count(value: float) -> str:
    return _indian_group(round(value))


def _days_phrase(days: int) -> str:
    """"1 day" / "7 days" — avoids "the previous 1 days" in finding text."""
    return "1 day" if days == 1 else f"{days} days"


def _finite(value, default: float = 0.0) -> float:
    """Coerce anything non-finite to a usable number.

    Guards every value on its way into a finding, so a divide-by-zero deep in a
    metric can never surface as `NaN` in an API response.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _slug(text: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in str(text).lower()).strip("-")


def _severity_for_change(change: float) -> str | None:
    magnitude = abs(change)
    if magnitude >= CHANGE_HIGH:
        return SEVERITY_HIGH
    if magnitude >= CHANGE_MEDIUM:
        return SEVERITY_MEDIUM
    if magnitude >= CHANGE_LOW:
        return SEVERITY_LOW
    return None


def _severity_for_points(delta: float) -> str | None:
    magnitude = abs(delta)
    if magnitude >= POINTS_HIGH:
        return SEVERITY_HIGH
    if magnitude >= POINTS_MEDIUM:
        return SEVERITY_MEDIUM
    if magnitude >= POINTS_LOW:
        return SEVERITY_LOW
    return None


def _threshold_reason(change: float, severity: str) -> str:
    floor = {
        SEVERITY_HIGH: CHANGE_HIGH,
        SEVERITY_MEDIUM: CHANGE_MEDIUM,
        SEVERITY_LOW: CHANGE_LOW,
    }[severity]
    return f"A change of {_pct(abs(change))} meets the {severity.lower()} threshold of {_pct(floor, 0)}."


def _points_reason(delta: float, severity: str) -> str:
    floor = {
        SEVERITY_HIGH: POINTS_HIGH,
        SEVERITY_MEDIUM: POINTS_MEDIUM,
        SEVERITY_LOW: POINTS_LOW,
    }[severity]
    return (
        f"A move of {_points(delta)} meets the {severity.lower()} threshold of "
        f"{_points(floor)}."
    )


# --------------------------------------------------------------------------
# Period handling
# --------------------------------------------------------------------------
def _actual_period(scoped: Dataset) -> Period | None:
    if scoped.is_empty():
        return None
    start, end = scoped.date_range
    return Period(start=start, end=end)


def _previous_period(period: Period) -> Period:
    """The equal-length window immediately before `period`."""
    end = period.start - timedelta(days=1)
    return Period(start=end - timedelta(days=period.days - 1), end=end)


def _split_period(period: Period) -> tuple[Period, Period]:
    """Split a period into earlier and later halves for a within-period trend."""
    midpoint = period.start + timedelta(days=period.days // 2)
    return (
        Period(start=period.start, end=midpoint - timedelta(days=1)),
        Period(start=midpoint, end=period.end),
    )


def _scope(dataset: Dataset, merchant_id: str, period: Period) -> Dataset:
    return filter_dataset(dataset, merchant_id=merchant_id, start=period.start, end=period.end)


# --------------------------------------------------------------------------
# Trend analysers
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _MetricSpec:
    key: str  # key in summary_metrics()
    label: str
    metric: str
    unit: str
    category: str


_TREND_METRICS = (
    _MetricSpec("total_revenue", "Revenue", "total_revenue", "currency", CATEGORY_REVENUE),
    _MetricSpec("total_orders", "Orders", "total_orders", "count", CATEGORY_ORDERS),
    _MetricSpec("total_customers", "Customer visits", "total_customers", "count", CATEGORY_CUSTOMERS),
    _MetricSpec("total_profit", "Gross profit", "total_profit", "currency", CATEGORY_PROFIT),
)


def _format_value(value: float, unit: str) -> str:
    if unit == "currency":
        return _inr(value)
    if unit == "rate":
        return _pct(value)
    if unit == "days":
        return f"{value:.1f} days"
    return _count(value)


def _analyse_totals(
    current: dict,
    previous: dict,
    period: Period,
    comparison: Period,
    basis: str,
) -> list[Finding]:
    """Period-on-period movement in the headline totals."""
    findings: list[Finding] = []
    against = (
        f"the previous {_days_phrase(comparison.days)}"
        if basis == BASIS_PREVIOUS
        else f"the first half of the period ({_days_phrase(comparison.days)})"
    )

    for spec in _TREND_METRICS:
        now = _finite(current.get(spec.key))
        before = _finite(previous.get(spec.key))
        if before <= 0:
            continue  # no baseline to divide by; growth would be undefined

        change = growth_rate(now, before)
        severity = _severity_for_change(change)
        if severity is None:
            continue

        direction = "rose" if change > 0 else "fell"
        findings.append(
            Finding(
                id=f"{_slug(spec.metric)}-{'up' if change > 0 else 'down'}",
                category=spec.category,
                severity=severity,
                title=f"{spec.label} {direction} {_pct(abs(change))} versus {against}",
                description=(
                    f"{spec.label} was {_format_value(now, spec.unit)} between "
                    f"{period.start.isoformat()} and {period.end.isoformat()}, "
                    f"compared with {_format_value(before, spec.unit)} over {against} "
                    f"({comparison.start.isoformat()} to {comparison.end.isoformat()}). "
                    f"That is a {direction[:-1]}e of {_pct(abs(change))}."
                ),
                metric=spec.metric,
                value=round_money(now) if spec.unit == "currency" else int(now),
                unit=spec.unit,
                scope="merchant",
                reason=_threshold_reason(change, severity),
                period=period,
                change=round_rate(change),
                comparison_value=round_money(before) if spec.unit == "currency" else int(before),
                evidence={
                    "comparison_basis": basis,
                    "comparison_period": comparison.as_dict(),
                },
            )
        )
    return findings


def _analyse_rates(
    current: dict,
    previous: dict,
    period: Period,
    comparison: Period,
    basis: str,
) -> list[Finding]:
    """Movement in margin and repeat rate, measured in percentage points."""
    findings: list[Finding] = []
    against = (
        f"the previous {_days_phrase(comparison.days)}"
        if basis == BASIS_PREVIOUS
        else "the first half of the period"
    )

    specs = (
        ("profit_margin", "Gross margin", CATEGORY_PROFIT, "profit-margin"),
        ("repeat_customer_rate", "Repeat customer rate", CATEGORY_CUSTOMERS, "repeat-rate"),
    )

    for key, label, category, slug in specs:
        now = _finite(current.get(key))
        before = _finite(previous.get(key))
        if now == 0 and before == 0:
            continue

        delta = now - before
        severity = _severity_for_points(delta)
        if severity is None:
            continue

        direction = "improved" if delta > 0 else "slipped"
        findings.append(
            Finding(
                id=f"{slug}-{'up' if delta > 0 else 'down'}",
                category=category,
                severity=severity,
                title=f"{label} {direction} {_points(delta)} to {_pct(now)}",
                description=(
                    f"{label} was {_pct(now)} between {period.start.isoformat()} and "
                    f"{period.end.isoformat()}, against {_pct(before)} over {against}. "
                    f"That is a move of {_points(delta)}."
                ),
                metric=key,
                value=round_rate(now),
                unit="rate",
                scope="merchant",
                reason=_points_reason(delta, severity),
                period=period,
                change=round_rate(delta),
                comparison_value=round_rate(before),
                evidence={
                    "comparison_basis": basis,
                    "comparison_period": comparison.as_dict(),
                    "measured_in": "percentage_points",
                },
            )
        )
    return findings


# --------------------------------------------------------------------------
# Product and category analysers
# --------------------------------------------------------------------------
def _analyse_products(current: pd.DataFrame, period: Period) -> list[Finding]:
    """Standing product findings over the selected period: who leads, who lags,
    and whether too much rests on one line. Period-on-period movement is handled
    separately by `_analyse_product_movers`, which uses the comparison windows."""
    findings: list[Finding] = []
    if current.empty:
        return findings

    top = current.iloc[0]
    top_share = _finite(top["revenue_share"])

    # Top performer — informational, but the anchor for most product decisions.
    findings.append(
        Finding(
            id=f"product-top-{_slug(top['product'])}",
            category=CATEGORY_PRODUCT,
            severity=SEVERITY_LOW,
            title=f"{top['product']} is the top product at {_pct(top_share)} of revenue",
            description=(
                f"{top['product']} earned {_inr(_finite(top['revenue']))} over the period, "
                f"{_pct(top_share)} of this merchant's revenue, at a "
                f"{_pct(_finite(top['profit_margin']))} margin."
            ),
            metric="revenue_share",
            value=round_rate(top_share),
            unit="rate",
            scope=str(top["product"]),
            reason="Highest revenue of any product in the period.",
            period=period,
            evidence={
                "revenue": round_money(_finite(top["revenue"])),
                "units_sold": int(_finite(top["units_sold"])),
                "profit_margin": round_rate(_finite(top["profit_margin"])),
            },
        )
    )

    # Concentration risk.
    if top_share >= CONCENTRATION_MEDIUM and len(current) >= MIN_PRODUCTS_FOR_RANKING:
        severity = SEVERITY_HIGH if top_share >= CONCENTRATION_HIGH else SEVERITY_MEDIUM
        floor = CONCENTRATION_HIGH if severity == SEVERITY_HIGH else CONCENTRATION_MEDIUM
        findings.append(
            Finding(
                id=f"product-concentration-{_slug(top['product'])}",
                category=CATEGORY_PRODUCT,
                severity=severity,
                title=f"{_pct(top_share)} of revenue depends on {top['product']}",
                description=(
                    f"{top['product']} accounts for {_pct(top_share)} of revenue across "
                    f"{len(current)} products. A fall in this one line would move the "
                    f"whole business."
                ),
                metric="revenue_share",
                value=round_rate(top_share),
                unit="rate",
                scope=str(top["product"]),
                reason=(
                    f"A single product holding {_pct(top_share)} of revenue meets the "
                    f"{severity.lower()} concentration threshold of {_pct(floor, 0)}."
                ),
                period=period,
                evidence={"product_count": int(len(current))},
            )
        )

    # Weakest product.
    if len(current) >= MIN_PRODUCTS_FOR_RANKING:
        weakest = current.iloc[-1]
        weak_share = _finite(weakest["revenue_share"])
        if weak_share < WEAK_SHARE:
            findings.append(
                Finding(
                    id=f"product-weak-{_slug(weakest['product'])}",
                    category=CATEGORY_PRODUCT,
                    severity=SEVERITY_LOW,
                    title=f"{weakest['product']} contributes only {_pct(weak_share)} of revenue",
                    description=(
                        f"{weakest['product']} earned {_inr(_finite(weakest['revenue']))} "
                        f"over the period, the lowest of {len(current)} products, selling "
                        f"{_count(_finite(weakest['units_sold']))} units."
                    ),
                    metric="revenue_share",
                    value=round_rate(weak_share),
                    unit="rate",
                    scope=str(weakest["product"]),
                    reason=(
                        f"Revenue share below the {_pct(WEAK_SHARE, 0)} weak-product threshold."
                    ),
                    period=period,
                    evidence={
                        "revenue": round_money(_finite(weakest["revenue"])),
                        "units_sold": int(_finite(weakest["units_sold"])),
                    },
                )
            )

    return findings


def _analyse_product_movers(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    period: Period,
    comparison: Period,
    basis: str | None,
) -> list[Finding]:
    """The single largest riser and faller in product revenue."""
    merged = current[["product", "revenue"]].merge(
        previous[["product", "revenue"]],
        on="product",
        how="inner",
        suffixes=("", "_prev"),
    )
    merged = merged[merged["revenue_prev"] > 0]
    if merged.empty:
        return []

    merged["change"] = (merged["revenue"] - merged["revenue_prev"]) / merged["revenue_prev"]
    # Deterministic ordering: ties broken by product name, never by row order.
    merged = merged.sort_values(["change", "product"], ascending=[False, True])

    against = (
        f"the previous {_days_phrase(comparison.days)}"
        if basis == BASIS_PREVIOUS
        else "the first half of the period"
    )
    findings: list[Finding] = []

    for row, label in ((merged.iloc[0], "riser"), (merged.iloc[-1], "faller")):
        change = _finite(row["change"])
        severity = _severity_for_change(change)
        if severity is None:
            continue
        if label == "riser" and change <= 0:
            continue
        if label == "faller" and change >= 0:
            continue

        direction = "grew" if change > 0 else "declined"
        findings.append(
            Finding(
                id=f"product-{label}-{_slug(row['product'])}",
                category=CATEGORY_PRODUCT,
                severity=severity,
                title=f"{row['product']} {direction} {_pct(abs(change))} versus {against}",
                description=(
                    f"{row['product']} earned {_inr(_finite(row['revenue']))} this period "
                    f"against {_inr(_finite(row['revenue_prev']))} over {against}, "
                    f"a {direction[:-1] if direction.endswith('d') else direction} of "
                    f"{_pct(abs(change))}."
                ),
                metric="revenue",
                value=round_money(_finite(row["revenue"])),
                unit="currency",
                scope=str(row["product"]),
                reason=_threshold_reason(change, severity),
                period=period,
                change=round_rate(change),
                comparison_value=round_money(_finite(row["revenue_prev"])),
                evidence={
                    "comparison_basis": basis,
                    "comparison_period": comparison.as_dict(),
                },
            )
        )
    return findings


def _analyse_categories(current: pd.DataFrame, period: Period) -> list[Finding]:
    """Which category leads over the selected period."""
    findings: list[Finding] = []
    if current.empty or len(current) < MIN_PRODUCTS_FOR_RANKING:
        return findings

    top = current.iloc[0]
    share = _finite(top["revenue_share"])
    findings.append(
        Finding(
            id=f"category-top-{_slug(top['category'])}",
            category=CATEGORY_CATEGORY,
            severity=SEVERITY_LOW,
            title=f"{top['category']} leads with {_pct(share)} of revenue",
            description=(
                f"{top['category']} earned {_inr(_finite(top['revenue']))} across "
                f"{int(_finite(top['products']))} product(s), {_pct(share)} of revenue, "
                f"at a {_pct(_finite(top['profit_margin']))} margin."
            ),
            metric="revenue_share",
            value=round_rate(share),
            unit="rate",
            scope=str(top["category"]),
            reason="Highest revenue of any category in the period.",
            period=period,
            evidence={
                "revenue": round_money(_finite(top["revenue"])),
                "products": int(_finite(top["products"])),
            },
        )
    )

    return findings


def _analyse_category_change(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    period: Period,
    comparison: Period,
    basis: str | None,
) -> list[Finding]:
    """The category that fell hardest between the comparison windows."""
    findings: list[Finding] = []
    if current.empty or previous.empty:
        return findings

    merged = current[["category", "revenue"]].merge(
        previous[["category", "revenue"]], on="category", how="inner", suffixes=("", "_prev")
    )
    merged = merged[merged["revenue_prev"] > 0]
    if merged.empty:
        return findings

    merged["change"] = (merged["revenue"] - merged["revenue_prev"]) / merged["revenue_prev"]
    merged = merged.sort_values(["change", "category"], ascending=[True, True])

    worst = merged.iloc[0]
    change = _finite(worst["change"])
    severity = _severity_for_change(change)
    if severity is not None and change < 0:
        against = (
            f"the previous {_days_phrase(comparison.days)}"
            if basis == BASIS_PREVIOUS
            else "the first half of the period"
        )
        findings.append(
            Finding(
                id=f"category-decline-{_slug(worst['category'])}",
                category=CATEGORY_CATEGORY,
                severity=severity,
                title=f"{worst['category']} revenue fell {_pct(abs(change))} versus {against}",
                description=(
                    f"The {worst['category']} category earned "
                    f"{_inr(_finite(worst['revenue']))} this period against "
                    f"{_inr(_finite(worst['revenue_prev']))} over {against}."
                ),
                metric="revenue",
                value=round_money(_finite(worst["revenue"])),
                unit="currency",
                scope=str(worst["category"]),
                reason=_threshold_reason(change, severity),
                period=period,
                change=round_rate(change),
                comparison_value=round_money(_finite(worst["revenue_prev"])),
                evidence={
                    "comparison_basis": basis,
                    "comparison_period": comparison.as_dict(),
                },
            )
        )
    return findings


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def _analyse_inventory(position: pd.DataFrame, period: Period) -> list[Finding]:
    """Stock risk from the inferred inventory position.

    Stage 2 derives stock from the sales file and infers restocks from the gap
    between observed and implied closing stock. It is not a live warehouse feed,
    and every finding here says so.
    """
    findings: list[Finding] = []
    if position.empty:
        return findings

    severities = {
        "out_of_stock": SEVERITY_HIGH,
        "critical": SEVERITY_HIGH,
        "low": SEVERITY_MEDIUM,
    }
    at_risk = position[position["stock_status"].isin(severities)]
    if at_risk.empty:
        return findings

    # Most urgent first; product name breaks ties so the order never varies.
    at_risk = at_risk.sort_values(
        ["days_of_inventory_cover", "product"], ascending=[True, True], na_position="first"
    )

    for row in at_risk.itertuples(index=False):
        status = str(row.stock_status)
        severity = severities[status]
        cover = _finite(row.days_of_inventory_cover, default=0.0)
        as_of = row.as_of_date.date() if hasattr(row.as_of_date, "date") else row.as_of_date

        if status == "out_of_stock":
            title = f"{row.product} is out of stock"
            reason = "Closing stock reached zero."
        else:
            floor = CRITICAL_COVER_DAYS if status == "critical" else LOW_COVER_DAYS
            title = f"{row.product} has {cover:.1f} days of stock cover"
            reason = (
                f"Cover of {cover:.1f} days is below the {status} threshold of "
                f"{floor:.0f} days."
            )

        findings.append(
            Finding(
                id=f"inventory-{status}-{_slug(row.product)}",
                category=CATEGORY_INVENTORY,
                severity=severity,
                title=title,
                description=(
                    f"{row.product} closed at {int(_finite(row.inventory))} units on "
                    f"{as_of}, selling {_finite(row.avg_daily_units):.1f} units/day over the "
                    f"last 7 days. Stock is inferred from sales history, not a live "
                    f"inventory feed."
                ),
                metric="days_of_inventory_cover",
                value=round(cover, 2),
                unit="days",
                scope=str(row.product),
                reason=reason,
                period=Period(start=as_of, end=as_of),
                evidence={
                    "inventory_units": int(_finite(row.inventory)),
                    "avg_daily_units": round(_finite(row.avg_daily_units), 2),
                    "stock_status": status,
                    "inferred": True,
                },
            )
        )
    return findings


# --------------------------------------------------------------------------
# Unusual days
# --------------------------------------------------------------------------
def _analyse_outlier_days(daily: pd.DataFrame, period: Period) -> list[Finding]:
    """Days whose revenue sits far from the period's own average."""
    findings: list[Finding] = []
    if len(daily) < MIN_DAYS_FOR_OUTLIER:
        return findings

    revenue = daily["revenue"].astype(float)
    mean = float(revenue.mean())
    # Population std, and a flat series has none — a constant series has no
    # outliers, and dividing by zero here would manufacture infinite ones.
    deviation = float(revenue.std(ddof=0))
    if deviation <= 0 or mean <= 0:
        return findings

    for label, index in (("peak", revenue.idxmax()), ("trough", revenue.idxmin())):
        row = daily.loc[index]
        value = float(row["revenue"])
        sigma = _finite(safe_divide(value - mean, deviation))
        if abs(sigma) < OUTLIER_SIGMA:
            continue

        day = row["date"].date() if hasattr(row["date"], "date") else row["date"]
        strong = label == "peak"
        findings.append(
            Finding(
                id=f"trend-{label}-day",
                category=CATEGORY_TREND,
                severity=SEVERITY_LOW,
                title=(
                    f"{'Strongest' if strong else 'Weakest'} day was {day} at "
                    f"{_inr(value)}"
                ),
                description=(
                    f"{day} recorded {_inr(value)} against a period average of "
                    f"{_inr(mean)} — {abs(sigma):.1f} standard deviations "
                    f"{'above' if strong else 'below'} the mean, on "
                    f"{_count(_finite(row['orders']))} orders."
                ),
                metric="revenue",
                value=round_money(value),
                unit="currency",
                scope="merchant",
                reason=(
                    f"Daily revenue {abs(sigma):.1f} standard deviations from the mean "
                    f"meets the {OUTLIER_SIGMA:.0f}-sigma threshold."
                ),
                period=Period(start=day, end=day),
                change=round_rate(growth_rate(value, mean)),
                comparison_value=round_money(mean),
                evidence={
                    "period_mean_revenue": round_money(mean),
                    "standard_deviations": round(sigma, 2),
                    "orders": int(_finite(row["orders"])),
                },
            )
        )
    return findings


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def analyse(
    dataset: Dataset,
    merchant_id: str,
    start: date | None = None,
    end: date | None = None,
) -> AnalysisReport:
    """Produce explainable findings for one merchant over a period.

    `dataset` is the full dataset, not a pre-filtered one: the comparison
    baseline lives *outside* the selected window, so the analyser needs to be
    able to look back past `start`.
    """
    scoped = filter_dataset(dataset, merchant_id=merchant_id, start=start, end=end)
    period = _actual_period(scoped)

    if period is None:
        return AnalysisReport(
            merchant_id=merchant_id,
            has_data=False,
            period=None,
            comparison_period=None,
            comparison_basis=None,
            notes=["No sales data for this merchant in the selected period."],
        )

    notes: list[str] = []
    findings: list[Finding] = []

    # Two different questions, two different windows:
    #   * standing findings (who leads, stock risk, unusual days) describe the
    #     whole selection the user asked for;
    #   * trend findings compare a `current_window` against a `baseline_window`.
    # Conflating them is how a 180-day total ends up being compared against a
    # 90-day one.
    current_window: Period | None = None
    baseline_window: Period | None = None
    basis: str | None = None

    # The minimum applies to *both* comparison paths. A window shorter than this
    # is dominated by the weekly rhythm rather than by any business change:
    # comparing one Monday against the Sunday before it reads as a 20% collapse
    # for the fashion merchant, whose Sunday trades at 1.23x an average day and
    # whose Monday trades at 0.74x. Reporting that as a HIGH finding would alarm
    # a merchant about nothing.
    if period.days >= MIN_DAYS_FOR_COMPARISON:
        candidate = _previous_period(period)
        if not _scope(dataset, merchant_id, candidate).is_empty():
            current_window, baseline_window, basis = period, candidate, BASIS_PREVIOUS
        else:
            earlier, later = _split_period(period)
            if not _scope(dataset, merchant_id, earlier).is_empty() and not _scope(
                dataset, merchant_id, later
            ).is_empty():
                current_window, baseline_window, basis = later, earlier, BASIS_WITHIN
                notes.append(
                    "No data exists before the selected period, so trends compare the "
                    "second half of the selection against the first half."
                )

    if baseline_window is None:
        if period.days < MIN_DAYS_FOR_COMPARISON:
            notes.append(
                f"The selected period is {_days_phrase(period.days)}. At least "
                f"{MIN_DAYS_FOR_COMPARISON} are needed before a change can be told apart "
                f"from the normal weekly rhythm, so no trend findings were produced."
            )
        else:
            notes.append(
                "Not enough history to compare against, so no trend findings were produced."
            )
    else:
        current_scope = _scope(dataset, merchant_id, current_window)
        baseline_scope = _scope(dataset, merchant_id, baseline_window)

        findings.extend(
            _analyse_totals(
                summary_metrics(current_scope),
                summary_metrics(baseline_scope),
                current_window,
                baseline_window,
                basis,
            )
        )
        findings.extend(
            _analyse_rates(
                summary_metrics(current_scope),
                summary_metrics(baseline_scope),
                current_window,
                baseline_window,
                basis,
            )
        )
        findings.extend(
            _analyse_product_movers(
                product_performance(current_scope),
                product_performance(baseline_scope),
                current_window,
                baseline_window,
                basis,
            )
        )
        findings.extend(
            _analyse_category_change(
                category_performance(current_scope),
                category_performance(baseline_scope),
                current_window,
                baseline_window,
                basis,
            )
        )

    # Standing findings always read the full selection.
    findings.extend(_analyse_products(product_performance(scoped), period))
    findings.extend(_analyse_categories(category_performance(scoped), period))
    findings.extend(_analyse_inventory(inventory_position(scoped), period))
    findings.extend(_analyse_outlier_days(daily_metrics(scoped), period))

    # Most severe first, then largest movement, then id — a total order, so the
    # same inputs always yield the same sequence.
    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], -abs(f.change or 0.0), f.id))

    return AnalysisReport(
        merchant_id=merchant_id,
        has_data=True,
        period=period,
        comparison_period=baseline_window,
        comparison_basis=basis,
        findings=findings,
        notes=notes,
    )
