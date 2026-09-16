"""Recommendation engine and action plan (Stage 5).

The engine adds no analysis, so these tests focus on the mapping: that every
finding becomes either an action or an explicitly-unactioned entry, that the
result is traceable and deterministic, and that the wording never claims a cause
the dataset cannot support.

`build_dataset` is imported from the Stage 4 tests rather than copied — it is a
plain deterministic builder, and duplicating it would let the two drift.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.services.action_plan import (
    MAX_PER_PRIORITY,
    ActionPlan,
    build_action_plan,
    plan_from_recommendations,
)
from backend.app.services.analysis import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    analyse,
)
from backend.app.services.recommendations import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    Recommendation,
    RecommendationSet,
    finding_kind,
    recommend,
    recommendations_from_report,
)
from tests.test_analysis import build_dataset

WINDOW = (date(2026, 1, 21), date(2026, 2, 9))

# Words that would assert a cause the dataset cannot establish.
CAUSAL_CLAIMS = (
    "because", "due to", "caused by", "as a result of", "led to",
    "resulted in", "the reason is", "this happened when", "owing to",
)


def single_product(tmp_path, first_half, second_half, **kwargs):
    units = [first_half] * 20 + [second_half] * 20
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units, **kwargs}],
    )


def by_source(result: RecommendationSet, finding_id: str):
    return next((r for r in result.recommendations if r.source_finding == finding_id), None)


# --------------------------------------------------------------------------
# A / B / C — each severity produces a recommendation
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("second_half", "severity", "priority"),
    [
        (25, SEVERITY_HIGH, PRIORITY_HIGH),      # +25%
        (23, SEVERITY_MEDIUM, PRIORITY_MEDIUM),  # +15%
        (21, SEVERITY_LOW, PRIORITY_LOW),        # +5%
    ],
)
def test_each_severity_produces_a_recommendation(tmp_path, second_half, severity, priority):
    dataset = single_product(tmp_path, 20, second_half)
    result = recommend(dataset, "M001", *WINDOW)

    recommendation = by_source(result, "total-revenue-up")
    assert recommendation is not None
    assert recommendation.severity == severity
    assert recommendation.priority == priority
    assert recommendation.action


def test_priority_is_taken_from_finding_severity(tmp_path):
    dataset = single_product(tmp_path, 30, 18)  # -40%
    result = recommend(dataset, "M001", *WINDOW)

    for recommendation in result.recommendations:
        expected = {
            SEVERITY_HIGH: PRIORITY_HIGH,
            SEVERITY_MEDIUM: PRIORITY_MEDIUM,
            SEVERITY_LOW: PRIORITY_LOW,
        }[recommendation.severity]
        assert recommendation.priority == expected


# --------------------------------------------------------------------------
# D — findings that should not produce an action
# --------------------------------------------------------------------------
def test_informational_findings_are_unactioned_with_a_reason(tmp_path):
    dataset = single_product(tmp_path, 20, 25)
    result = recommend(dataset, "M001", *WINDOW)

    unactioned_ids = {u.finding_id for u in result.unactioned}
    assert any(fid.startswith("product-top-") for fid in unactioned_ids)

    for entry in result.unactioned:
        assert entry.reason, f"{entry.finding_id} was dropped without explanation"
        assert entry.title


def test_unactioned_findings_never_appear_as_recommendations(tmp_path):
    dataset = single_product(tmp_path, 20, 25)
    result = recommend(dataset, "M001", *WINDOW)

    actioned = {r.source_finding for r in result.recommendations}
    unactioned = {u.finding_id for u in result.unactioned}
    assert actioned.isdisjoint(unactioned)


def test_every_finding_is_either_actioned_or_explained(tmp_path):
    """Nothing may be silently dropped between analysis and advice."""
    dataset = single_product(tmp_path, 30, 18)
    report = analyse(dataset, "M001", *WINDOW)
    result = recommendations_from_report(report)

    accounted = {r.source_finding for r in result.recommendations} | {
        u.finding_id for u in result.unactioned
    }
    assert accounted == {f.id for f in report.findings}


def test_unknown_finding_kind_is_reported_not_guessed():
    """A finding the engine does not recognise must produce an explicit
    unactioned entry, never invented advice."""
    from backend.app.services.analysis import AnalysisReport, Finding, Period

    period = Period(start=date(2026, 1, 1), end=date(2026, 1, 31))
    mystery = Finding(
        id="brand-new-rule-nobody-mapped",
        category="Revenue",
        severity=SEVERITY_HIGH,
        title="Something new happened",
        description="...",
        metric="x",
        value=1.0,
        unit="count",
        scope="merchant",
        reason="...",
        period=period,
    )
    report = AnalysisReport(
        merchant_id="M001",
        has_data=True,
        period=period,
        comparison_period=None,
        comparison_basis=None,
        findings=[mystery],
    )

    result = recommendations_from_report(report)
    assert result.recommendations == []
    assert len(result.unactioned) == 1
    assert "No action template" in result.unactioned[0].reason


def test_finding_kind_classifies_scoped_ids():
    from backend.app.services.analysis import Finding, Period

    period = Period(start=date(2026, 1, 1), end=date(2026, 1, 2))

    def make(finding_id):
        return Finding(
            id=finding_id, category="Product", severity=SEVERITY_LOW, title="t",
            description="d", metric="m", value=1.0, unit="count", scope="s",
            reason="r", period=period,
        )

    assert finding_kind(make("inventory-critical-cooking-oil-1l")) == "inventory-critical"
    assert finding_kind(make("product-riser-smart-watch")) == "product-riser"
    assert finding_kind(make("total-revenue-down")) == "total-revenue-down"
    assert finding_kind(make("trend-peak-day")) == "trend-peak-day"
    assert finding_kind(make("something-unmapped")) is None


# --------------------------------------------------------------------------
# E — traceability
# --------------------------------------------------------------------------
def test_every_recommendation_names_its_source_finding(tmp_path):
    dataset = single_product(tmp_path, 30, 18)
    report = analyse(dataset, "M001", *WINDOW)
    result = recommendations_from_report(report)

    finding_ids = {f.id for f in report.findings}
    assert result.recommendations
    for recommendation in result.recommendations:
        assert recommendation.source_finding in finding_ids
        assert recommendation.id == f"rec-{recommendation.source_finding}"


def test_recommendation_carries_the_findings_supporting_numbers(tmp_path):
    dataset = single_product(tmp_path, 30, 18)
    report = analyse(dataset, "M001", *WINDOW)
    result = recommendations_from_report(report)

    findings = {f.id: f for f in report.findings}
    for recommendation in result.recommendations:
        source = findings[recommendation.source_finding]
        assert recommendation.value == source.value
        assert recommendation.change == source.change
        assert recommendation.unit == source.unit
        assert recommendation.scope == source.scope
        assert recommendation.category == source.category
        assert source.title in recommendation.reason


def test_no_recommendation_exists_without_a_finding(tmp_path):
    """The empty case is the strongest form of this rule."""
    dataset = single_product(tmp_path, 20, 20)
    result = recommend(dataset, "M001", date(2020, 1, 1), date(2020, 2, 1))

    assert result.has_data is False
    assert result.recommendations == []
    assert result.unactioned == []


# --------------------------------------------------------------------------
# F / G / H / I — determinism and ordering
# --------------------------------------------------------------------------
def test_recommendations_are_deterministic(tmp_path):
    dataset = single_product(tmp_path, 30, 18)
    first = recommend(dataset, "M001", *WINDOW)
    second = recommend(dataset, "M001", *WINDOW)

    assert [r.as_dict() for r in first.recommendations] == [
        r.as_dict() for r in second.recommendations
    ]
    assert [u.as_dict() for u in first.unactioned] == [u.as_dict() for u in second.unactioned]


def test_action_plan_is_deterministic(tmp_path):
    dataset = single_product(tmp_path, 30, 18)
    first = build_action_plan(dataset, "M001", *WINDOW)
    second = build_action_plan(dataset, "M001", *WINDOW)

    assert [i.as_dict() for i in first.items] == [i.as_dict() for i in second.items]


def _recommendation(rec_id: str, priority: str, change: float) -> Recommendation:
    return Recommendation(
        id=rec_id,
        title=f"Title {rec_id}",
        action="Do the thing.",
        reason="Because the finding said so.",
        priority=priority,
        severity={PRIORITY_HIGH: SEVERITY_HIGH, PRIORITY_MEDIUM: SEVERITY_MEDIUM,
                  PRIORITY_LOW: SEVERITY_LOW}[priority],
        category="Revenue",
        scope="merchant",
        metric="total_revenue",
        value=1.0,
        unit="currency",
        period={"start": "2026-01-01", "end": "2026-01-31", "days": 31},
        source_finding=rec_id.removeprefix("rec-"),
        change=change,
    )


def _plan_of(*recommendations) -> ActionPlan:
    return plan_from_recommendations(
        RecommendationSet(
            merchant_id="M001",
            has_data=True,
            period=None,
            comparison_period=None,
            comparison_basis=None,
            recommendations=list(recommendations),
        )
    )


def test_high_ranks_before_medium_and_low():
    plan = _plan_of(
        _recommendation("rec-c", PRIORITY_LOW, 0.9),
        _recommendation("rec-b", PRIORITY_MEDIUM, 0.9),
        _recommendation("rec-a", PRIORITY_HIGH, 0.1),
    )

    assert [item.priority for item in plan.items] == [
        PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW
    ]
    assert [item.rank for item in plan.items] == [1, 2, 3]


def test_same_priority_orders_by_magnitude_then_id():
    plan = _plan_of(
        _recommendation("rec-b", PRIORITY_HIGH, 0.20),
        _recommendation("rec-a", PRIORITY_HIGH, 0.50),
        _recommendation("rec-c", PRIORITY_HIGH, 0.20),
    )

    # Largest move first; the two equal moves fall back to id order.
    assert [item.source_finding for item in plan.high] == ["a", "b", "c"]


def test_ordering_ignores_the_sign_of_the_change():
    """A 40% fall and a 40% rise are equally significant to rank."""
    plan = _plan_of(
        _recommendation("rec-small", PRIORITY_HIGH, 0.10),
        _recommendation("rec-big", PRIORITY_HIGH, -0.40),
    )
    assert plan.high[0].source_finding == "big"


def test_recommendations_without_a_change_still_rank():
    """Inventory findings carry no `change`; they must not crash the sort."""
    no_change = _recommendation("rec-inv", PRIORITY_HIGH, 0.0)
    object.__setattr__(no_change, "change", None)

    plan = _plan_of(no_change, _recommendation("rec-other", PRIORITY_HIGH, 0.3))
    assert plan.included == 2
    assert plan.high[0].source_finding == "other"


# --------------------------------------------------------------------------
# Action plan capping
# --------------------------------------------------------------------------
def test_plan_caps_each_bucket():
    many = [_recommendation(f"rec-{i:02d}", PRIORITY_HIGH, 0.5) for i in range(10)]
    plan = _plan_of(*many)

    assert len(plan.high) == MAX_PER_PRIORITY[PRIORITY_HIGH]
    assert plan.total_available == 10
    assert plan.included == MAX_PER_PRIORITY[PRIORITY_HIGH]
    assert plan.truncated is True


def test_truncation_is_reported_not_hidden():
    many = [_recommendation(f"rec-{i:02d}", PRIORITY_HIGH, 0.5) for i in range(10)]
    plan = _plan_of(*many)
    assert any("most significant" in note for note in plan.notes)


def test_short_plan_is_not_marked_truncated():
    plan = _plan_of(_recommendation("rec-a", PRIORITY_HIGH, 0.5))
    assert plan.truncated is False
    assert plan.notes == []


def test_ranks_are_contiguous_across_buckets():
    plan = _plan_of(
        _recommendation("rec-h1", PRIORITY_HIGH, 0.5),
        _recommendation("rec-h2", PRIORITY_HIGH, 0.4),
        _recommendation("rec-m1", PRIORITY_MEDIUM, 0.3),
        _recommendation("rec-l1", PRIORITY_LOW, 0.2),
    )
    assert [item.rank for item in plan.items] == [1, 2, 3, 4]


# --------------------------------------------------------------------------
# J — inventory semantics preserved
# --------------------------------------------------------------------------
def test_inventory_recommendation_preserves_inferred_flag(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0,
          "units": [10] * 40, "opening_stock": 425}],
    )
    result = recommend(dataset, "M001")

    inventory = [r for r in result.recommendations if r.category == "Inventory"]
    assert inventory
    for recommendation in inventory:
        assert recommendation.evidence["inferred"] is True
        assert recommendation.unit == "days"


def test_inventory_advice_does_not_imply_a_live_stock_feed(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0,
          "units": [10] * 40, "opening_stock": 425}],
    )
    result = recommend(dataset, "M001")
    inventory = [r for r in result.recommendations if r.category == "Inventory"][0]

    text = f"{inventory.title} {inventory.action}".lower()
    for phrase in ("warehouse", "live stock", "real-time", "real time"):
        assert phrase not in text


# --------------------------------------------------------------------------
# K — no unsupported causal claims
# --------------------------------------------------------------------------
def test_recommendation_text_never_asserts_a_cause(tmp_path):
    """The analysis establishes what changed, never why. The advice must say
    what to investigate, not assert an explanation."""
    datasets = []
    for name, first, second in (("falling", 30, 18), ("rising", 20, 30)):
        directory = tmp_path / name
        directory.mkdir()
        datasets.append(single_product(directory, first, second))

    for dataset in datasets:
        for recommendation in recommend(dataset, "M001", *WINDOW).recommendations:
            text = f"{recommendation.title} {recommendation.action}".lower()
            for claim in CAUSAL_CLAIMS:
                assert claim not in text, f"{recommendation.id} claims a cause: '{claim}'"


def test_actions_are_phrased_as_things_to_do(tmp_path):
    dataset = single_product(tmp_path, 30, 18)
    for recommendation in recommend(dataset, "M001", *WINDOW).recommendations:
        assert recommendation.action.endswith("."), recommendation.id
        assert len(recommendation.action) > 40, f"{recommendation.id} action is too thin"


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------
def test_empty_period_produces_an_empty_plan(tmp_path):
    dataset = single_product(tmp_path, 20, 25)
    plan = build_action_plan(dataset, "M001", date(2020, 1, 1), date(2020, 2, 1))

    assert plan.has_data is False
    assert plan.items == []
    assert plan.total_available == 0
    assert plan.truncated is False


def test_unknown_merchant_produces_an_empty_plan(tmp_path):
    dataset = single_product(tmp_path, 20, 25)
    plan = build_action_plan(dataset, "NOPE")

    assert plan.has_data is False
    assert plan.items == []


def test_flat_merchant_produces_no_trend_actions(tmp_path):
    """A business that did not change should not be handed busywork."""
    dataset = single_product(tmp_path, 20, 20)
    result = recommend(dataset, "M001", *WINDOW)

    sources = {r.source_finding for r in result.recommendations}
    assert "total-revenue-up" not in sources
    assert "total-revenue-down" not in sources


def test_notes_from_the_analysis_are_carried_through(tmp_path):
    """The within-period caveat must reach the merchant, not stop at analysis."""
    dataset = single_product(tmp_path, 20, 30)
    result = recommend(dataset, "M001")

    assert any("second half" in note for note in result.notes)
    assert any("second half" in note for note in build_action_plan(dataset, "M001").notes)


# --------------------------------------------------------------------------
# Real dataset
# --------------------------------------------------------------------------
def _real_dataset():
    from backend.app.config import settings
    from backend.app.services.data_loader import read_dataset

    if not (settings.sales_path.exists() and settings.customers_path.exists()):
        return None
    return read_dataset(settings.sales_path, settings.customers_path)


REAL = _real_dataset()
needs_real = pytest.mark.skipif(REAL is None, reason="dataset not generated")
LAST_30 = (date(2026, 8, 17), date(2026, 9, 15))


@needs_real
def test_declining_merchant_gets_recovery_and_retention_actions():
    result = recommend(REAL, "M003", *LAST_30)
    sources = {r.source_finding for r in result.recommendations}

    assert "total-revenue-down" in sources
    assert "repeat-rate-down" in sources, "the retention dip should become an action"


@needs_real
def test_kirana_stock_out_becomes_a_high_priority_restock():
    result = recommend(REAL, "M002", *LAST_30)
    restock = by_source(result, "inventory-critical-cooking-oil-1l")

    assert restock is not None
    assert restock.priority == PRIORITY_HIGH
    assert "Cooking Oil 1L" in restock.title
    assert restock.evidence["inferred"] is True


@needs_real
def test_growing_merchant_is_told_to_scale_its_star_product():
    result = recommend(REAL, "M001", *LAST_30)
    riser = by_source(result, "product-riser-smart-watch")

    assert riser is not None
    assert "Smart Watch" in riser.title


@needs_real
@pytest.mark.parametrize("merchant_id", ["M001", "M002", "M003", "M004"])
def test_every_real_merchant_gets_a_usable_plan(merchant_id):
    plan = build_action_plan(REAL, merchant_id, *LAST_30)

    assert plan.has_data is True
    assert plan.items, f"{merchant_id} got no actions at all"
    assert plan.included <= sum(MAX_PER_PRIORITY.values())
    assert [item.rank for item in plan.items] == list(range(1, plan.included + 1))
    for item in plan.items:
        assert item.source_finding and item.reason and item.action


@needs_real
def test_real_recommendations_are_deterministic():
    first = recommend(REAL, "M003", *LAST_30)
    second = recommend(REAL, "M003", *LAST_30)
    assert [r.as_dict() for r in first.recommendations] == [
        r.as_dict() for r in second.recommendations
    ]


@needs_real
@pytest.mark.parametrize("merchant_id", ["M001", "M002", "M003", "M004"])
def test_no_real_recommendation_claims_a_cause(merchant_id):
    for recommendation in recommend(REAL, merchant_id, *LAST_30).recommendations:
        text = f"{recommendation.title} {recommendation.action}".lower()
        for claim in CAUSAL_CLAIMS:
            assert claim not in text, f"{recommendation.id} claims a cause: '{claim}'"
