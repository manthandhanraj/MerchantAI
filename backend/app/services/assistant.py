"""AI business assistant.

Answers a merchant's question from a structured context assembled out of the
services that already exist. It computes nothing itself:

    summary_metrics / daily_metrics / product_performance   (Stage 2)
    analyse                                                 (Stage 4)
    recommendations / action plan                           (Stage 5)
    forecast                                                (Stage 6)
            |
            v
        context  ->  answer

**The model explains; it never calculates.** Every number in an answer must
already exist in the context. When `LLM_ENABLED` is false — the default — the
assistant answers from templates built directly off the context, so the feature
works offline with no key and no network.

When the model *is* enabled, its reply is checked: any figure that cannot be
traced back to the context causes the answer to be discarded in favour of the
deterministic one. That is the mechanism that stops invented revenue, orders or
forecasts reaching the merchant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from backend.app.services.action_plan import plan_from_recommendations
# `_inr` / `_pct` are reused rather than reimplemented so the assistant's wording
# matches the findings it quotes, down to the digit grouping.
from backend.app.services.analysis import _inr, _pct, analyse
from backend.app.services.data_loader import Dataset
from backend.app.services.forecasting import forecast
from backend.app.services.llm import LLMError, complete, is_enabled
from backend.app.services.metrics import (
    daily_metrics,
    filter_dataset,
    product_performance,
    summary_metrics,
)
from backend.app.services.recommendations import recommendations_from_report

SOURCE_DETERMINISTIC = "deterministic"
SOURCE_LLM = "llm"

# How much history to carry into the context. Enough to show the recent shape
# without shipping six months of rows into a prompt.
CONTEXT_DAILY_DAYS = 14
CONTEXT_FINDINGS = 8
CONTEXT_RECOMMENDATIONS = 6
CONTEXT_PRODUCTS = 5

# Integers up to this value are treated as calendar or ordinal references
# ("7 days", "3 products") rather than business figures, so they are not
# required to appear in the context. Anything larger must be traceable.
SMALL_INTEGER_CEILING = 31

STARTER_QUESTIONS = (
    "Why did my sales decrease?",
    "Which product is performing best?",
    "What should I focus on today?",
    "How can I improve next week's revenue?",
)

STANDING_LIMITATIONS = (
    "All figures come from synthetic demo data, not real payment records.",
    "Gross profit is revenue minus cost of goods sold; rent, salaries and other "
    "overheads are not modelled.",
    "Customer counts are daily distinct shoppers. Summed over several days they "
    "describe visits, not unique people.",
    "Stock levels are inferred from sales history, not a live inventory feed.",
    "The data shows what changed, not why. There is no pricing, marketing, "
    "weather or competitor data to establish a cause.",
)


@dataclass
class AssistantAnswer:
    merchant_id: str
    question: str
    answer: str
    source: str
    llm_enabled: bool
    has_data: bool
    grounded_in: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=lambda: list(STARTER_QUESTIONS))
    limitations: list[str] = field(default_factory=list)
    context: dict | None = None

    def as_dict(self) -> dict:
        payload = {
            "merchant_id": self.merchant_id,
            "question": self.question,
            "answer": self.answer,
            "source": self.source,
            "llm_enabled": self.llm_enabled,
            "has_data": self.has_data,
            "grounded_in": self.grounded_in,
            "warnings": self.warnings,
            "suggested_questions": self.suggested_questions,
            "limitations": self.limitations,
        }
        if self.context is not None:
            payload["context"] = self.context
        return payload


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------
def build_context(
    dataset: Dataset,
    merchant_id: str,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Assemble everything the assistant is allowed to know.

    Each section is the output of an existing service. Nothing is recomputed,
    so a number quoted by the assistant is the same number the dashboard shows.
    """
    scoped = filter_dataset(dataset, merchant_id=merchant_id, start=start, end=end)

    if scoped.is_empty():
        return {
            "merchant_id": merchant_id,
            "has_data": False,
            "period": None,
            "limitations": list(STANDING_LIMITATIONS),
        }

    summary = summary_metrics(scoped)
    daily = daily_metrics(scoped)

    # Chained deliberately. `recommend()` and `build_action_plan()` would each
    # re-run `analyse()` from scratch, so calling all three ran the analysis
    # three times for one answer. Passing the report down uses the composable
    # entry points instead — same output, a third of the work.
    report = analyse(dataset, merchant_id, start, end)
    suggestions = recommendations_from_report(report)
    plan = plan_from_recommendations(suggestions)

    projection = forecast(dataset, merchant_id, start, end)
    products = product_performance(scoped).head(CONTEXT_PRODUCTS)

    recent = daily.tail(CONTEXT_DAILY_DAYS)
    daily_points = [
        {
            "date": row.date.date().isoformat(),
            "revenue": float(row.revenue),
            "orders": int(row.orders),
            "customers": int(row.customers),
        }
        for row in recent.itertuples(index=False)
    ]

    limitations = list(STANDING_LIMITATIONS)
    if projection.available:
        limitations.extend(projection.limitations)

    return {
        "merchant_id": merchant_id,
        "has_data": True,
        "period": {
            "start": summary["period_start"],
            "end": summary["period_end"],
            "days": summary["days"],
        },
        "comparison_basis": report.comparison_basis,
        "summary": summary,
        "daily_recent": daily_points,
        "findings": [f.as_dict() for f in report.findings[:CONTEXT_FINDINGS]],
        "recommendations": [
            r.as_dict() for r in suggestions.recommendations[:CONTEXT_RECOMMENDATIONS]
        ],
        "action_plan": {
            "high": [i.as_dict() for i in plan.high],
            "medium": [i.as_dict() for i in plan.medium],
            "low": [i.as_dict() for i in plan.low],
            "total_available": plan.total_available,
        },
        "forecast": projection.as_dict(),
        "top_products": [
            {
                "product": str(row.product),
                "category": str(row.category),
                "revenue": float(row.revenue),
                "units_sold": int(row.units_sold),
                "revenue_share": float(row.revenue_share),
                "profit_margin": float(row.profit_margin),
            }
            for row in products.itertuples(index=False)
        ],
        "limitations": limitations,
    }


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def _money(value) -> str:
    return _inr(float(value)) if value is not None else "unavailable"


def _rate(value) -> str:
    return _pct(float(value)) if value is not None else "unavailable"


# --------------------------------------------------------------------------
# Intent routing
# --------------------------------------------------------------------------
INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("inventory", ("stock", "inventory", "restock", "run out", "reorder", "replenish")),
    # "improve" is checked before "forecast": "how can I improve next week's
    # revenue?" is a request for actions, not for a projection. The improve
    # answer folds the forecast in anyway, so nothing is lost.
    ("improve", ("improve", "increase", "grow", "boost", "raise", "more revenue", "better")),
    # "next week" is deliberately absent here — it appears in improvement
    # questions at least as often as in forecast ones.
    ("forecast", ("forecast", "predict", "projection", "project", "expect", "coming days")),
    ("customers", ("customer", "retention", "repeat", "loyal", "churn", "footfall")),
    ("best_product", ("best", "top", "bestseller", "best-selling", "strongest", "which product")),
    ("focus", ("focus", "today", "priority", "prioritise", "prioritize", "first", "what should i do")),
    ("decline", ("why", "decrease", "decline", "drop", "fall", "fell", "down", "losing", "lost")),
)


def detect_intent(question: str) -> str:
    """Map a question to an answer template. Deterministic and order-sensitive:
    the first matching intent in the table wins."""
    text = (question or "").strip().lower()
    if not text:
        return "summary"
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return intent
    return "summary"


# --------------------------------------------------------------------------
# Deterministic answers
# --------------------------------------------------------------------------
def _answer_summary(context: dict) -> tuple[str, list[str]]:
    summary = context["summary"]
    period = context["period"]
    lines = [
        f"Between {period['start']} and {period['end']} ({period['days']} days), "
        f"{context['merchant_id']} took {_money(summary['total_revenue'])} across "
        f"{summary['total_orders']:,} orders, with {_money(summary['total_profit'])} "
        f"gross profit at a {_rate(summary['profit_margin'])} margin.",
        f"Average order value was {_money(summary['average_order_value'])}, from "
        f"{summary['total_customers']:,} customer visits of which "
        f"{_rate(summary['repeat_customer_rate'])} were repeat customers.",
    ]

    findings = context.get("findings") or []
    if findings:
        top = findings[0]
        lines.append(f"The most significant change: {top['title'].lower()}.")
    return " ".join(lines), ["summary", "findings"]


def _answer_decline(context: dict) -> tuple[str, list[str]]:
    findings = context.get("findings") or []
    falling = [
        f for f in findings if f.get("change") is not None and f["change"] < 0
    ]

    if not falling:
        summary = context["summary"]
        return (
            f"Nothing in this period reads as a decline. Revenue was "
            f"{_money(summary['total_revenue'])} and no metric fell far enough to be "
            f"flagged. If you are seeing a drop elsewhere, it may fall outside the "
            f"selected dates.",
            ["summary", "findings"],
        )

    parts = [f"{len(falling)} measure(s) fell in this period."]
    for finding in falling[:3]:
        parts.append(f"{finding['title']} ({finding['category'].lower()}).")
    parts.append(
        "The data shows what moved, not why it moved — there is no pricing, "
        "marketing or competitor information here to establish a cause."
    )

    actions = [
        item
        for item in context["action_plan"]["high"] + context["action_plan"]["medium"]
        if item["category"] in {"Revenue", "Product", "Category", "Customers"}
    ]
    if actions:
        parts.append(f"The suggested next step is: {actions[0]['action']}")

    return " ".join(parts), ["findings", "action_plan"]


def _answer_best_product(context: dict) -> tuple[str, list[str]]:
    products = context.get("top_products") or []
    if not products:
        return "No product data is available for this period.", ["top_products"]

    best = products[0]
    text = (
        f"{best['product']} is the strongest performer, taking "
        f"{_money(best['revenue'])} ({_rate(best['revenue_share'])} of revenue) from "
        f"{best['units_sold']:,} units at a {_rate(best['profit_margin'])} margin."
    )
    if len(products) > 1:
        runners = ", ".join(f"{p['product']} ({_rate(p['revenue_share'])})" for p in products[1:3])
        text += f" Behind it: {runners}."
    return text, ["top_products"]


def _answer_focus(context: dict) -> tuple[str, list[str]]:
    plan = context["action_plan"]
    ordered = plan["high"] + plan["medium"] + plan["low"]

    if not ordered:
        return (
            "Nothing needs attention in this period — no metric moved far enough, "
            "and no product is close to a stock-out.",
            ["action_plan"],
        )

    parts = [f"There are {len(ordered)} action(s) for this period, most urgent first."]
    for item in ordered[:3]:
        parts.append(f"{item['rank']}. {item['title']} ({item['priority']} priority) — {item['action']}")
    return " ".join(parts), ["action_plan"]


def _answer_improve(context: dict) -> tuple[str, list[str]]:
    recommendations = context.get("recommendations") or []
    grounded = ["recommendations"]

    if not recommendations:
        return (
            "No specific improvement action is supported by this period's data.",
            grounded,
        )

    parts = ["Based on what moved in this period:"]
    for recommendation in recommendations[:3]:
        parts.append(f"{recommendation['title']} — {recommendation['action']}")

    projection = context.get("forecast") or {}
    if projection.get("available"):
        grounded.append("forecast")
        parts.append(
            f"On current trend the next {projection['horizon_days']} days project to "
            f"{_money(projection['forecast_total'])}, so any change you make should be "
            f"measured against that."
        )
    return " ".join(parts), grounded


def _answer_forecast(context: dict) -> tuple[str, list[str]]:
    projection = context.get("forecast") or {}

    if not projection.get("available"):
        reason = projection.get("reason") or "A forecast is not available for this period."
        return f"No forecast is available. {reason}", ["forecast"]

    period = projection["forecast_period"]
    text = [
        f"Projecting {projection['metric']} for {period['days']} days "
        f"({period['start']} to {period['end']}): {_money(projection['forecast_total'])} "
        f"in total, against a recent daily average of "
        f"{_money(projection['history_daily_mean'])}.",
        f"The underlying trend is {projection['trend_direction']}.",
    ]

    backtest = projection.get("backtest")
    if backtest and backtest.get("mean_absolute_percentage_error") is not None:
        text.append(
            f"On a holdout test of the last {backtest['days']} days this method was off "
            f"by {_rate(backtest['mean_absolute_percentage_error'])} on average. That is "
            f"measured past accuracy, not a guarantee."
        )
    text.append(
        "It is a short-term projection that continues the existing trend and weekly "
        "pattern; it cannot anticipate festivals, promotions or stock-outs."
    )
    return " ".join(text), ["forecast"]


def _answer_inventory(context: dict) -> tuple[str, list[str]]:
    items = [
        item
        for bucket in ("high", "medium", "low")
        for item in context["action_plan"][bucket]
        if item["category"] == "Inventory"
    ]

    if not items:
        return (
            "No product is close to running out in this period, based on stock "
            "inferred from sales history.",
            ["action_plan"],
        )

    parts = [f"{len(items)} product(s) need a stock decision."]
    for item in items:
        parts.append(f"{item['title']} — {item['reason']}")
    parts.append(
        "Stock levels are inferred from sales history, not a live inventory feed, "
        "so confirm against what is physically on the shelf."
    )
    return " ".join(parts), ["action_plan"]


def _answer_customers(context: dict) -> tuple[str, list[str]]:
    summary = context["summary"]
    parts = [
        f"This period recorded {summary['total_customers']:,} customer visits — "
        f"{summary['new_customers']:,} new and {summary['repeat_customers']:,} "
        f"returning, a repeat rate of {_rate(summary['repeat_customer_rate'])}.",
        f"Revenue per visit was {_money(summary['revenue_per_customer'])}.",
    ]

    grounded = ["summary"]
    customer_findings = [f for f in (context.get("findings") or []) if f["category"] == "Customers"]
    if customer_findings:
        grounded.append("findings")
        parts.append(f"Notable: {customer_findings[0]['title']}.")

    parts.append(
        "The dataset holds daily counts only, with no per-customer records, so "
        "cohort retention and lifetime value cannot be calculated."
    )
    return " ".join(parts), grounded


_ANSWERERS = {
    "summary": _answer_summary,
    "decline": _answer_decline,
    "best_product": _answer_best_product,
    "focus": _answer_focus,
    "improve": _answer_improve,
    "forecast": _answer_forecast,
    "inventory": _answer_inventory,
    "customers": _answer_customers,
}


def answer_from_context(question: str, context: dict) -> tuple[str, list[str]]:
    """The offline answer path. Pure function of (question, context)."""
    if not context.get("has_data"):
        return (
            "There is no sales data for this merchant in the selected period, so "
            "there is nothing to report. Try a wider date range.",
            [],
        )
    return _ANSWERERS[detect_intent(question)](context)


# --------------------------------------------------------------------------
# Numeric grounding check
# --------------------------------------------------------------------------
_NUMBER_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")


def _collect_numbers(node, found: set[float]) -> None:
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        found.add(float(node))
    elif isinstance(node, str):
        # Strings in the context carry numbers too — dates ("2026-09-15") and
        # finding titles ("declined 30.4%"). Anything already written in the
        # context is by definition traceable to it.
        for token in _NUMBER_PATTERN.findall(node):
            try:
                found.add(float(token.replace(",", "").rstrip(".")))
            except ValueError:
                continue
    elif isinstance(node, dict):
        for value in node.values():
            _collect_numbers(value, found)
    elif isinstance(node, (list, tuple)):
        for value in node:
            _collect_numbers(value, found)


def context_numbers(context: dict) -> set[float]:
    """Every numeric value the context contains, plus percentage renderings.

    Two renderings have to be accepted or correct answers would be rejected:

    * a rate stored as 0.257 is written "25.7%" in prose, so the x100 form counts;
    * a change stored as -0.167 is written "fell 16.7%", so the magnitude counts
      too — prose carries the direction in the verb, not the sign.
    """
    found: set[float] = set()
    _collect_numbers(context, found)

    allowed: set[float] = set()
    for value in found:
        for variant in (value, value * 100):
            for signed in (variant, abs(variant)):
                allowed.add(signed)
                allowed.add(round(signed))
                allowed.add(round(signed, 1))
                allowed.add(round(signed, 2))
    return allowed


def unsupported_numbers(text: str, context: dict) -> list[str]:
    """Numbers in `text` that cannot be traced to the context.

    Integers at or below `SMALL_INTEGER_CEILING` are allowed through as calendar
    and ordinal references. The check therefore targets the figures that matter —
    revenue, orders, customers, forecasts — rather than every digit.
    """
    allowed = context_numbers(context)
    unsupported: list[str] = []

    for token in _NUMBER_PATTERN.findall(text or ""):
        cleaned = token.replace(",", "").rstrip(".")
        if not cleaned or cleaned in {"-", "."}:
            continue
        try:
            value = float(cleaned)
        except ValueError:
            continue

        if abs(value) <= SMALL_INTEGER_CEILING and float(value).is_integer():
            continue
        if any(abs(value - candidate) <= 0.51 for candidate in allowed):
            continue
        if any(
            candidate != 0 and abs(value - candidate) / abs(candidate) <= 0.005
            for candidate in allowed
        ):
            continue
        unsupported.append(token)

    return unsupported


# --------------------------------------------------------------------------
# Prompting
# --------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a business assistant for a small merchant. Answer only from the "
    "JSON context provided. Every number you state must appear in that context — "
    "never estimate, extrapolate or invent a figure. If the context does not "
    "support an answer, say plainly that the data does not show it. The data "
    "establishes what changed, not why, so never assert a cause. Be concise and "
    "concrete: two short paragraphs at most, in plain language a shop owner would "
    "use. Amounts are Indian rupees."
)


def build_prompt(question: str, context: dict) -> str:
    import json

    return (
        f"Merchant question: {question}\n\n"
        f"Context (the only facts you may use):\n{json.dumps(context, default=str)}"
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def ask(
    dataset: Dataset,
    merchant_id: str,
    question: str,
    start: date | None = None,
    end: date | None = None,
    include_context: bool = False,
) -> AssistantAnswer:
    """Answer a merchant's question, grounded in computed analytics.

    Falls back to the deterministic answer whenever the model is disabled,
    fails, or returns a figure that cannot be traced to the context.
    """
    context = build_context(dataset, merchant_id, start, end)
    fallback_text, grounded = answer_from_context(question, context)

    result = AssistantAnswer(
        merchant_id=merchant_id,
        question=question,
        answer=fallback_text,
        source=SOURCE_DETERMINISTIC,
        llm_enabled=is_enabled(),
        has_data=bool(context.get("has_data")),
        grounded_in=grounded,
        limitations=list(context.get("limitations", [])),
        context=context if include_context else None,
    )

    if not is_enabled():
        return result

    try:
        generated = complete(SYSTEM_PROMPT, build_prompt(question, context))
    except LLMError as exc:
        # A model failure degrades to the offline answer; it never surfaces as
        # an error, because a usable answer already exists.
        result.warnings.append(f"Language model unavailable, answered from the data instead. {exc}")
        return result

    invented = unsupported_numbers(generated, context)
    if invented:
        result.warnings.append(
            "The language model's reply contained figures that could not be traced "
            f"to the merchant's data ({', '.join(invented[:5])}), so the verified "
            "answer is shown instead."
        )
        return result

    result.answer = generated
    result.source = SOURCE_LLM
    return result
