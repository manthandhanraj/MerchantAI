"""Business analysis engine (Stage 4).

Purpose-built datasets are used where a pattern must be controlled exactly
(growing / declining / flat / constant), and the real generated dataset is used
to confirm the engine reaches the right conclusions about the demo merchants.

Every synthetic dataset here is written through `read_dataset`, so it must pass
Stage 2 validation — including inventory continuity — exactly like real data.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services import analysis as A
from backend.app.services.analysis import (
    CATEGORY_INVENTORY,
    CATEGORY_REVENUE,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    analyse,
)
from backend.app.services.data_loader import read_dataset
from tests.conftest import _write_csv

START = date(2026, 1, 1)

VALID_CATEGORIES = {
    "Revenue", "Orders", "Customers", "Profit",
    "Product", "Category", "Inventory", "Trend",
}


def build_dataset(
    tmp_path,
    products,
    merchant_id="M001",
    start=START,
):
    """Write a dataset from per-product daily unit counts and load it.

    `products` is a list of dicts:
        {name, category, price, cost_ratio, units: [...], opening_stock}

    Inventory is decremented by units sold so continuity holds, and one unit per
    order keeps `orders <= units_sold` true.
    """
    sales_rows = []
    day_orders: dict[str, int] = {}

    for product in products:
        stock = product.get("opening_stock", 100_000)
        for offset, units in enumerate(product["units"]):
            units = int(units)
            if units <= 0:
                continue
            stock -= units
            day = (start + timedelta(days=offset)).isoformat()
            price = product["price"]
            sales_rows.append(
                {
                    "date": day,
                    "merchant_id": merchant_id,
                    "product": product["name"],
                    "category": product["category"],
                    "orders": units,
                    "units_sold": units,
                    "revenue": f"{units * price:.2f}",
                    "expenses": f"{units * price * product.get('cost_ratio', 0.6):.2f}",
                    "inventory": stock,
                }
            )
            day_orders[day] = day_orders.get(day, 0) + units

    customer_rows = []
    for day in sorted(day_orders):
        orders = day_orders[day]
        customers = max(1, orders // 2)  # always <= orders
        repeat = customers // 2
        customer_rows.append(
            {
                "date": day,
                "merchant_id": merchant_id,
                "customers": customers,
                "new_customers": customers - repeat,
                "repeat_customers": repeat,
            }
        )

    sales_path = tmp_path / "sales.csv"
    customers_path = tmp_path / "customers.csv"
    _write_csv(sales_path, SALES_COLUMNS, sales_rows)
    _write_csv(customers_path, CUSTOMERS_COLUMNS, customer_rows)
    return read_dataset(sales_path, customers_path)


def ids(report) -> set[str]:
    return {finding.id for finding in report.findings}


def by_category(report, category) -> list:
    return [f for f in report.findings if f.category == category]


# --------------------------------------------------------------------------
# Growing / declining / flat
# --------------------------------------------------------------------------
@pytest.fixture
def growing(tmp_path):
    # 40 days: 20 flat, then 20 at +50%.
    units = [20] * 20 + [30] * 20
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units}],
    )


@pytest.fixture
def declining(tmp_path):
    units = [30] * 20 + [18] * 20  # -40%
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units}],
    )


@pytest.fixture
def flat(tmp_path):
    units = [20] * 40
    return build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units}],
    )


def test_growing_merchant_reports_revenue_rise(growing):
    report = analyse(growing, "M001", date(2026, 1, 21), date(2026, 2, 9))
    revenue = by_category(report, CATEGORY_REVENUE)

    assert len(revenue) == 1
    finding = revenue[0]
    assert finding.id == "total-revenue-up"
    assert finding.change == pytest.approx(0.5, abs=0.01)
    assert finding.severity == SEVERITY_HIGH
    assert "rose" in finding.title


def test_declining_merchant_reports_revenue_fall(declining):
    report = analyse(declining, "M001", date(2026, 1, 21), date(2026, 2, 9))
    finding = by_category(report, CATEGORY_REVENUE)[0]

    assert finding.id == "total-revenue-down"
    assert finding.change == pytest.approx(-0.4, abs=0.01)
    assert finding.severity == SEVERITY_HIGH
    assert "fell" in finding.title


def test_flat_merchant_reports_no_trend_findings(flat):
    """A business that did not change should not be told that it did."""
    report = analyse(flat, "M001", date(2026, 1, 21), date(2026, 2, 9))

    assert by_category(report, CATEGORY_REVENUE) == []
    assert by_category(report, "Orders") == []
    assert by_category(report, "Profit") == []


def test_comparison_uses_the_previous_period_when_one_exists(growing):
    report = analyse(growing, "M001", date(2026, 1, 21), date(2026, 2, 9))

    assert report.comparison_basis == A.BASIS_PREVIOUS
    assert report.comparison_period.start == date(2026, 1, 1)
    assert report.comparison_period.end == date(2026, 1, 20)


def test_comparison_falls_back_to_splitting_the_selection(growing):
    """Selecting the whole history leaves no prior window, so the engine splits
    the selection and says so."""
    report = analyse(growing, "M001")

    assert report.comparison_basis == A.BASIS_WITHIN
    assert any("second half" in note for note in report.notes)
    assert by_category(report, CATEGORY_REVENUE)[0].change > 0


def test_trend_findings_describe_the_window_they_measured(growing):
    """Regression: the within-period split must compare like with like. A bug
    here compared the full selection against only its first half."""
    report = analyse(growing, "M001")
    finding = by_category(report, CATEGORY_REVENUE)[0]

    # The described period is the later half, not the whole selection.
    assert finding.period.start == date(2026, 1, 21)
    assert finding.period.end == date(2026, 2, 9)
    assert finding.period.days == report.comparison_period.days


def test_no_comparison_when_history_is_too_short(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": [10, 10]}],
    )
    report = analyse(dataset, "M001")

    assert report.comparison_basis is None
    assert by_category(report, CATEGORY_REVENUE) == []
    # The note names the actual length and the requirement, rather than saying
    # only "not enough".
    assert any("2 days" in note and "At least 4" in note for note in report.notes)


@pytest.mark.parametrize("days", [1, 2, 3])
def test_short_selections_produce_no_trend_findings(tmp_path, days):
    """Regression: the documented 4-day minimum gated only the within-period
    split, so a previous-period comparison ran on as little as one day. For the
    fashion merchant — Sunday 1.23x an average day, Monday 0.74x — that reported
    the normal weekly rhythm as a 20% HIGH-severity collapse.
    """
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": [10] * 30}],
    )
    end = START + timedelta(days=29)
    report = analyse(dataset, "M001", end - timedelta(days=days - 1), end)

    assert report.comparison_basis is None
    assert report.comparison_period is None
    for finding in report.findings:
        assert not finding.id.startswith(("total-", "profit-margin", "repeat-rate")), (
            f"{finding.id} compared a {days}-day window"
        )
    assert report.notes


def test_the_minimum_length_is_honoured_exactly(tmp_path):
    """At the documented boundary the comparison runs; one day below it does not."""
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": [10] * 30}],
    )
    end = START + timedelta(days=29)

    at_minimum = analyse(
        dataset, "M001", end - timedelta(days=A.MIN_DAYS_FOR_COMPARISON - 1), end
    )
    below = analyse(dataset, "M001", end - timedelta(days=A.MIN_DAYS_FOR_COMPARISON - 2), end)

    assert at_minimum.comparison_basis == A.BASIS_PREVIOUS
    assert below.comparison_basis is None


def test_day_counts_read_naturally_in_finding_text(tmp_path):
    """Regression: a one-day comparison rendered as "the previous 1 days"."""
    assert A._days_phrase(1) == "1 day"
    assert A._days_phrase(7) == "7 days"


# --------------------------------------------------------------------------
# Severity thresholds
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("second_half_units", "expected"),
    [
        (21, SEVERITY_LOW),      # +5%
        (23, SEVERITY_MEDIUM),   # +15%
        (25, SEVERITY_HIGH),     # +25%
    ],
)
def test_severity_follows_documented_thresholds(tmp_path, second_half_units, expected):
    units = [20] * 20 + [second_half_units] * 20
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units}],
    )
    report = analyse(dataset, "M001", date(2026, 1, 21), date(2026, 2, 9))
    assert by_category(report, CATEGORY_REVENUE)[0].severity == expected


def test_change_below_the_floor_is_not_reported(tmp_path):
    units = [20] * 20 + [20] * 20  # identical
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0, "units": units}],
    )
    report = analyse(dataset, "M001", date(2026, 1, 21), date(2026, 2, 9))
    assert by_category(report, CATEGORY_REVENUE) == []


def test_every_finding_explains_why_it_was_flagged(growing):
    report = analyse(growing, "M001", date(2026, 1, 21), date(2026, 2, 9))

    assert report.findings
    for finding in report.findings:
        assert finding.reason, f"{finding.id} has no reason"
        assert finding.title and finding.description
        assert finding.severity in {SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}
        assert finding.category in VALID_CATEGORIES
        assert finding.scope
        assert finding.unit in {"currency", "count", "rate", "days"}


# --------------------------------------------------------------------------
# Products and categories
# --------------------------------------------------------------------------
@pytest.fixture
def multi_product(tmp_path):
    return build_dataset(
        tmp_path,
        [
            # Dominant product: ~74% of revenue.
            {"name": "Star", "category": "Tools", "price": 500.0, "units": [20] * 40},
            {"name": "Middle", "category": "Tools", "price": 100.0, "units": [30] * 40},
            # Weak product: well under the 5% share floor.
            {"name": "Laggard", "category": "Parts", "price": 10.0, "units": [5] * 40},
        ],
    )


def test_top_product_is_identified(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    top = [f for f in report.findings if f.id.startswith("product-top-")]

    assert len(top) == 1
    assert top[0].scope == "Star"
    assert top[0].value > 0.5


def test_weak_product_is_identified(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    weak = [f for f in report.findings if f.id.startswith("product-weak-")]

    assert len(weak) == 1
    assert weak[0].scope == "Laggard"
    assert weak[0].value < A.WEAK_SHARE


def test_revenue_concentration_is_flagged(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    concentration = [f for f in report.findings if f.id.startswith("product-concentration-")]

    assert len(concentration) == 1
    assert concentration[0].severity == SEVERITY_HIGH  # share above 50%
    assert concentration[0].scope == "Star"


def test_single_product_merchant_is_not_flagged_for_concentration(flat):
    """One product at 100% is not a diversification finding, it is the business."""
    report = analyse(flat, "M001", date(2026, 1, 21), date(2026, 2, 9))
    assert not [f for f in report.findings if f.id.startswith("product-concentration-")]
    assert not [f for f in report.findings if f.id.startswith("product-weak-")]


def test_product_mover_is_identified(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [
            {"name": "Riser", "category": "Tools", "price": 100.0, "units": [10] * 20 + [20] * 20},
            {"name": "Steady", "category": "Tools", "price": 100.0, "units": [15] * 40},
        ],
    )
    report = analyse(dataset, "M001", date(2026, 1, 21), date(2026, 2, 9))
    risers = [f for f in report.findings if f.id.startswith("product-riser-")]

    assert len(risers) == 1
    assert risers[0].scope == "Riser"
    assert risers[0].change == pytest.approx(1.0, abs=0.01)


def test_top_category_is_identified(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    top = [f for f in report.findings if f.id.startswith("category-top-")]

    assert len(top) == 1
    assert top[0].scope == "Tools"


def test_category_decline_is_identified(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [
            {"name": "A", "category": "Falling", "price": 100.0, "units": [30] * 20 + [15] * 20},
            {"name": "B", "category": "Steady", "price": 100.0, "units": [20] * 40},
        ],
    )
    report = analyse(dataset, "M001", date(2026, 1, 21), date(2026, 2, 9))
    declines = [f for f in report.findings if f.id.startswith("category-decline-")]

    assert len(declines) == 1
    assert declines[0].scope == "Falling"
    assert declines[0].severity == SEVERITY_HIGH


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def test_low_stock_is_flagged_with_cover_days(tmp_path):
    # Sells 10/day and closes on a small stock, so cover lands under a week.
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0,
          "units": [10] * 40, "opening_stock": 425}],
    )
    report = analyse(dataset, "M001")
    inventory = by_category(report, CATEGORY_INVENTORY)

    assert len(inventory) == 1
    finding = inventory[0]
    assert finding.scope == "Widget"
    assert finding.unit == "days"
    assert 0 < finding.value < A.LOW_COVER_DAYS
    assert finding.severity in {SEVERITY_HIGH, SEVERITY_MEDIUM}


def test_inventory_findings_state_that_stock_is_inferred(tmp_path):
    """Stage 2 infers stock from sales history; the finding must not imply a
    live warehouse feed."""
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0,
          "units": [10] * 40, "opening_stock": 425}],
    )
    finding = by_category(analyse(dataset, "M001"), CATEGORY_INVENTORY)[0]

    assert "inferred" in finding.description.lower()
    assert finding.evidence["inferred"] is True


def test_healthy_stock_produces_no_inventory_finding(flat):
    assert by_category(analyse(flat, "M001"), CATEGORY_INVENTORY) == []


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------
def test_empty_selection_returns_an_empty_report(growing):
    report = analyse(growing, "M001", date(2020, 1, 1), date(2020, 2, 1))

    assert report.has_data is False
    assert report.findings == []
    assert report.period is None
    assert report.comparison_period is None
    assert report.notes


def test_unknown_merchant_returns_an_empty_report(growing):
    """The service reports emptiness; rejecting unknown ids is the route's job."""
    report = analyse(growing, "NOPE")
    assert report.has_data is False
    assert report.findings == []


def test_constant_series_produces_no_outlier_findings(flat):
    """A perfectly flat series has zero standard deviation. Dividing by it would
    manufacture infinite outliers."""
    report = analyse(flat, "M001")
    assert [f for f in report.findings if f.id.startswith("trend-")] == []


def test_near_zero_values_do_not_divide_by_zero(tmp_path):
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 1.0, "units": [1] * 40}],
    )
    report = analyse(dataset, "M001")

    for finding in report.findings:
        assert finding.value == finding.value  # not NaN
        assert abs(finding.value) != float("inf")


def test_no_finding_carries_nan_or_infinity(growing, multi_product):
    for dataset in (growing, multi_product):
        report = analyse(dataset, "M001")
        for finding in report.findings:
            for value in (finding.value, finding.change, finding.comparison_value):
                if value is None:
                    continue
                assert value == value, f"{finding.id} produced NaN"
                assert abs(value) != float("inf"), f"{finding.id} produced Infinity"


def test_zero_baseline_is_skipped_rather_than_divided_by(tmp_path):
    """No trading in the earlier window means growth is undefined, not infinite."""
    dataset = build_dataset(
        tmp_path,
        [{"name": "Widget", "category": "Tools", "price": 100.0,
          "units": [0] * 20 + [20] * 20}],
    )
    report = analyse(dataset, "M001", date(2026, 1, 21), date(2026, 2, 9))

    assert by_category(report, CATEGORY_REVENUE) == []
    assert report.has_data is True


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
def test_repeated_analysis_is_identical(multi_product):
    first = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    second = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))

    assert [f.as_dict() for f in first.findings] == [f.as_dict() for f in second.findings]


def test_findings_are_ordered_most_severe_first(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    ranks = [A._SEVERITY_ORDER[f.severity] for f in report.findings]
    assert ranks == sorted(ranks)


def test_finding_ids_are_unique(multi_product):
    report = analyse(multi_product, "M001", date(2026, 1, 21), date(2026, 2, 9))
    assert len(ids(report)) == len(report.findings)


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------
def test_indian_digit_grouping():
    assert A._indian_group(564) == "564"
    assert A._indian_group(17518) == "17,518"
    assert A._indian_group(17518564) == "1,75,18,564"


def test_currency_formatting_handles_sign_and_zero():
    assert A._inr(0) == "₹0"
    assert A._inr(1751857) == "₹17,51,857"
    assert A._inr(-2500) == "-₹2,500"


def test_finite_guard_neutralises_bad_values():
    assert A._finite(float("nan")) == 0.0
    assert A._finite(float("inf")) == 0.0
    assert A._finite(None) == 0.0
    assert A._finite("abc") == 0.0
    assert A._finite(4.5) == 4.5


# --------------------------------------------------------------------------
# The real generated dataset
# --------------------------------------------------------------------------
def _real_dataset():
    from backend.app.config import settings
    from backend.app.services.data_loader import read_dataset as load

    if not (settings.sales_path.exists() and settings.customers_path.exists()):
        return None
    return load(settings.sales_path, settings.customers_path)


REAL = _real_dataset()
needs_real = pytest.mark.skipif(REAL is None, reason="dataset not generated")

LAST_30 = (date(2026, 8, 17), date(2026, 9, 15))


@needs_real
def test_real_declining_merchant_is_diagnosed():
    """M003 is the declining café. The engine should say so, and reach the
    retention problem built into the data."""
    report = analyse(REAL, "M003", *LAST_30)

    revenue = by_category(report, CATEGORY_REVENUE)
    assert revenue and revenue[0].change < 0

    repeat = [f for f in report.findings if f.id.startswith("repeat-rate-")]
    assert repeat and repeat[0].change < 0, "the retention dip should surface"


@needs_real
def test_real_growing_merchant_is_diagnosed():
    report = analyse(REAL, "M001", *LAST_30)

    revenue = by_category(report, CATEGORY_REVENUE)
    assert revenue and revenue[0].change > 0
    assert revenue[0].id == "total-revenue-up"


@needs_real
def test_real_growing_merchant_surfaces_its_star_product():
    """Smart Watch is the deliberately fast-growing line in M001."""
    report = analyse(REAL, "M001", *LAST_30)
    risers = [f for f in report.findings if f.id.startswith("product-riser-")]

    assert risers and risers[0].scope == "Smart Watch"


@needs_real
def test_real_kirana_stock_out_risk_surfaces():
    """M002's Cooking Oil is generated to run close to a stock-out."""
    report = analyse(REAL, "M002", *LAST_30)
    inventory = by_category(report, CATEGORY_INVENTORY)

    assert any(f.scope == "Cooking Oil 1L" for f in inventory)


@needs_real
@pytest.mark.parametrize("merchant_id", ["M001", "M002", "M003", "M004"])
def test_every_real_merchant_analyses_cleanly(merchant_id):
    report = analyse(REAL, merchant_id, *LAST_30)

    assert report.has_data is True
    assert report.findings, f"{merchant_id} produced no findings at all"
    for finding in report.findings:
        assert finding.category in VALID_CATEGORIES
        assert finding.severity in {SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}
        assert finding.value == finding.value
        assert abs(finding.value) != float("inf")


@needs_real
def test_real_analysis_is_deterministic():
    first = analyse(REAL, "M003", *LAST_30)
    second = analyse(REAL, "M003", *LAST_30)
    assert [f.as_dict() for f in first.findings] == [f.as_dict() for f in second.findings]
