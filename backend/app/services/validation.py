"""Dataset-level validation.

`models/schemas.py` validates one row at a time. It structurally cannot express
rules that span rows — the Stage 1 audit flagged exactly two such gaps:

    * daily customers <= daily orders   (spans both files)
    * inventory continuity              (spans consecutive rows of a product)

This module closes them and adds the structural, consistency and range checks
the pipeline needs before any later stage trusts the data.

Two rules the whole module follows:

1. **Nothing is ever repaired.** Validation reports; it does not mutate. A
   silent fix would let corrupt data reach the dashboard wearing a clean face.
2. **Every failure names the rows.** An issue carries a count and concrete
   examples so the problem is actionable, not just detected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS

MAX_EXAMPLES = 5

# A product's realised unit price (revenue / units_sold) must stay in this band
# around its own median. Wide enough for the promotional discounts the generator
# applies, tight enough to catch a corrupted revenue figure.
PRICE_BAND = (0.50, 1.10)

SALES_NUMERIC = ["orders", "units_sold", "revenue", "expenses", "inventory"]
CUSTOMERS_NUMERIC = ["customers", "new_customers", "repeat_customers"]


class DatasetValidationError(Exception):
    """Raised when a dataset fails validation. The message lists every error."""


@dataclass(frozen=True)
class ValidationIssue:
    rule: str
    severity: str  # "error" | "warning"
    message: str
    count: int
    examples: tuple[str, ...] = ()

    def __str__(self) -> str:
        line = f"[{self.severity.upper()} {self.rule}] {self.message} ({self.count} affected)"
        if self.examples:
            line += "\n    e.g. " + "\n    e.g. ".join(self.examples)
        return line


@dataclass
class ValidationReport:
    """Outcome of validating one dataset."""

    issues: list[ValidationIssue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        """True when nothing blocking was found. Warnings do not block."""
        return not self.errors

    def raise_if_invalid(self) -> None:
        if self.ok:
            return
        detail = "\n".join(str(issue) for issue in self.errors)
        raise DatasetValidationError(
            f"Dataset failed validation with {len(self.errors)} error(s):\n{detail}"
        )

    def summary(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return f"{status} - {len(self.errors)} error(s), {len(self.warnings)} warning(s)"


def _coerce_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Return a copy with the given columns as numbers.

    Only called once the columns are known to be coercible, so nothing is lost
    or silently blanked here.
    """
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column])
    return out


def _examples(frame: pd.DataFrame, columns: list[str]) -> tuple[str, ...]:
    """Format up to MAX_EXAMPLES offending rows into readable identifiers."""
    available = [c for c in columns if c in frame.columns]
    rows = frame.head(MAX_EXAMPLES)
    return tuple(
        ", ".join(f"{c}={row[c]}" for c in available) for _, row in rows.iterrows()
    )


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------
def _check_columns(frame: pd.DataFrame, expected: list[str], name: str, rule: str) -> list[ValidationIssue]:
    missing = [c for c in expected if c not in frame.columns]
    if missing:
        return [
            ValidationIssue(
                rule,
                "error",
                f"{name} is missing required column(s): {', '.join(missing)}",
                len(missing),
                tuple(missing),
            )
        ]
    return []


def _check_missing_values(frame: pd.DataFrame, columns: list[str], name: str, rule: str) -> list[ValidationIssue]:
    null_counts = {c: int(frame[c].isna().sum()) for c in columns if c in frame.columns}
    offenders = {c: n for c, n in null_counts.items() if n}
    if offenders:
        detail = ", ".join(f"{c}={n}" for c, n in offenders.items())
        return [
            ValidationIssue(
                rule,
                "error",
                f"{name} contains missing values (blank cells are not allowed; "
                f"a day with no activity should have no row): {detail}",
                sum(offenders.values()),
            )
        ]
    return []


def _check_duplicates(frame: pd.DataFrame, keys: list[str], name: str, rule: str) -> list[ValidationIssue]:
    if not all(k in frame.columns for k in keys):
        return []
    duplicated = frame[frame.duplicated(subset=keys, keep=False)]
    if not duplicated.empty:
        return [
            ValidationIssue(
                rule,
                "error",
                f"{name} has duplicate rows for key ({', '.join(keys)}); the grain must be unique",
                len(duplicated),
                _examples(duplicated, keys),
            )
        ]
    return []


def _check_dates(frame: pd.DataFrame, name: str, rule: str) -> list[ValidationIssue]:
    if "date" not in frame.columns:
        return []
    parsed = pd.to_datetime(frame["date"], errors="coerce", format="%Y-%m-%d")
    bad = frame[parsed.isna()]
    if not bad.empty:
        return [
            ValidationIssue(
                rule,
                "error",
                f"{name} has unparseable dates (expected YYYY-MM-DD)",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product"]),
            )
        ]
    return []


# --------------------------------------------------------------------------
# Ranges and row-level logic
# --------------------------------------------------------------------------
def _check_non_negative(frame: pd.DataFrame, columns: list[str], name: str, rule: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for column in columns:
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        bad = frame[numeric.notna() & (numeric < 0)]
        if not bad.empty:
            issues.append(
                ValidationIssue(
                    rule,
                    "error",
                    f"{name}.{column} has negative values, which are impossible",
                    len(bad),
                    _examples(bad, ["date", "merchant_id", "product", column]),
                )
            )
    return issues


def _check_numeric_types(frame: pd.DataFrame, columns: list[str], name: str, rule: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for column in columns:
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        bad = frame[numeric.isna() & frame[column].notna()]
        if not bad.empty:
            issues.append(
                ValidationIssue(
                    rule,
                    "error",
                    f"{name}.{column} contains non-numeric values",
                    len(bad),
                    _examples(bad, ["date", "merchant_id", "product", column]),
                )
            )
    return issues


def _check_orders_units(sales: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not {"orders", "units_sold"} <= set(sales.columns):
        return issues

    bad = sales[sales["orders"] > sales["units_sold"]]
    if not bad.empty:
        issues.append(
            ValidationIssue(
                "R011",
                "error",
                "orders exceeds units_sold; an order must carry at least one unit",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product", "orders", "units_sold"]),
            )
        )

    bad = sales[(sales["units_sold"] > 0) & (sales["orders"] == 0)]
    if not bad.empty:
        issues.append(
            ValidationIssue(
                "R012",
                "error",
                "units were sold with zero orders",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product", "orders", "units_sold"]),
            )
        )
    return issues


def _check_customer_split(customers: pd.DataFrame) -> list[ValidationIssue]:
    if not set(CUSTOMERS_NUMERIC) <= set(customers.columns):
        return []
    total = customers["new_customers"] + customers["repeat_customers"]
    bad = customers[total != customers["customers"]]
    if not bad.empty:
        return [
            ValidationIssue(
                "R013",
                "error",
                "new_customers + repeat_customers does not equal customers",
                len(bad),
                _examples(bad, ["date", "merchant_id", "customers", "new_customers", "repeat_customers"]),
            )
        ]
    return []


def _check_revenue_consistency(sales: pd.DataFrame) -> list[ValidationIssue]:
    """Revenue must move with units sold, and the realised unit price must stay
    near that product's own typical price."""
    issues: list[ValidationIssue] = []
    if not {"revenue", "units_sold", "product", "merchant_id"} <= set(sales.columns):
        return issues

    bad = sales[(sales["units_sold"] > 0) & (sales["revenue"] <= 0)]
    if not bad.empty:
        issues.append(
            ValidationIssue(
                "R030",
                "error",
                "units were sold but revenue is zero or negative",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product", "units_sold", "revenue"]),
            )
        )

    bad = sales[(sales["units_sold"] == 0) & (sales["revenue"] > 0)]
    if not bad.empty:
        issues.append(
            ValidationIssue(
                "R031",
                "error",
                "revenue recorded with no units sold",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product", "units_sold", "revenue"]),
            )
        )

    priced = sales[sales["units_sold"] > 0].copy()
    if not priced.empty:
        priced["unit_price"] = priced["revenue"] / priced["units_sold"]
        median = priced.groupby(["merchant_id", "product"])["unit_price"].transform("median")
        low, high = PRICE_BAND
        outliers = priced[(priced["unit_price"] < median * low) | (priced["unit_price"] > median * high)]
        if not outliers.empty:
            issues.append(
                ValidationIssue(
                    "R032",
                    "error",
                    f"realised unit price falls outside {low:.0%}-{high:.0%} of the product's "
                    "median price, which suggests a corrupted revenue value",
                    len(outliers),
                    _examples(outliers, ["date", "merchant_id", "product", "units_sold", "revenue"]),
                )
            )
    return issues


def _check_profit_consistency(sales: pd.DataFrame) -> list[ValidationIssue]:
    """Expenses are cost of goods sold, so a row selling below cost is possible
    in the real world but never expected from our generator. Warn, don't block."""
    if not {"revenue", "expenses"} <= set(sales.columns):
        return []
    bad = sales[sales["expenses"] > sales["revenue"]]
    if not bad.empty:
        return [
            ValidationIssue(
                "R033",
                "warning",
                "expenses exceed revenue (negative gross profit on these rows)",
                len(bad),
                _examples(bad, ["date", "merchant_id", "product", "revenue", "expenses"]),
            )
        ]
    return []


# --------------------------------------------------------------------------
# Cross-row invariants (the Stage 1 audit gaps)
# --------------------------------------------------------------------------
def _check_customers_vs_orders(sales: pd.DataFrame, customers: pd.DataFrame) -> list[ValidationIssue]:
    """Invariant 4: distinct daily customers cannot exceed that day's orders."""
    if "orders" not in sales.columns or "customers" not in customers.columns:
        return []

    daily_orders = sales.groupby(["date", "merchant_id"], as_index=False)["orders"].sum()
    merged = customers.merge(daily_orders, on=["date", "merchant_id"], how="left", suffixes=("", "_sales"))
    merged["orders"] = merged["orders"].fillna(0)

    bad = merged[merged["customers"] > merged["orders"]]
    if not bad.empty:
        return [
            ValidationIssue(
                "R020",
                "error",
                "daily customers exceed that day's total orders",
                len(bad),
                _examples(bad, ["date", "merchant_id", "customers", "orders"]),
            )
        ]
    return []


def _check_inventory_continuity(sales: pd.DataFrame) -> tuple[list[ValidationIssue], int]:
    """Invariant 8: closing stock must fall by exactly units_sold between a
    product's consecutive rows, unless a restock raised it.

    So the checkable rule is `inventory[t] >= inventory[t-1] - units_sold[t]`.
    A shortfall means stock disappeared without being sold — corruption.
    Restocks are counted and returned so they stay visible rather than silently
    absorbed by a loose rule.
    """
    required = {"merchant_id", "product", "date", "inventory", "units_sold"}
    if not required <= set(sales.columns):
        return [], 0

    ordered = sales.sort_values(["merchant_id", "product", "date"]).copy()
    previous = ordered.groupby(["merchant_id", "product"])["inventory"].shift(1)
    expected = previous - ordered["units_sold"]
    has_previous = previous.notna()

    shortfall = ordered[has_previous & (ordered["inventory"] < expected)]
    restocks = int((has_previous & (ordered["inventory"] > expected)).sum())

    issues: list[ValidationIssue] = []
    if not shortfall.empty:
        detail = shortfall.copy()
        detail["expected_inventory"] = expected[shortfall.index]
        issues.append(
            ValidationIssue(
                "R021",
                "error",
                "inventory fell by more than units_sold; stock cannot disappear "
                "without being sold (a restock may only raise it)",
                len(shortfall),
                _examples(
                    detail,
                    ["date", "merchant_id", "product", "units_sold", "inventory", "expected_inventory"],
                ),
            )
        )
    return issues, restocks


def _check_join_completeness(sales: pd.DataFrame, customers: pd.DataFrame) -> list[ValidationIssue]:
    """Invariant 7: the two files are joined on (date, merchant_id), so each
    must cover exactly the same days. An orphan on either side silently drops
    data from customer analysis."""
    if "date" not in sales.columns or "date" not in customers.columns:
        return []

    sales_keys = set(map(tuple, sales[["date", "merchant_id"]].drop_duplicates().to_numpy()))
    customer_keys = set(map(tuple, customers[["date", "merchant_id"]].drop_duplicates().to_numpy()))

    issues: list[ValidationIssue] = []
    missing_customers = sales_keys - customer_keys
    if missing_customers:
        issues.append(
            ValidationIssue(
                "R022",
                "error",
                "sales days have no matching row in the customers file",
                len(missing_customers),
                tuple(f"date={d}, merchant_id={m}" for d, m in sorted(missing_customers)[:MAX_EXAMPLES]),
            )
        )

    orphan_customers = customer_keys - sales_keys
    if orphan_customers:
        issues.append(
            ValidationIssue(
                "R023",
                "error",
                "customer days have no matching sales rows",
                len(orphan_customers),
                tuple(f"date={d}, merchant_id={m}" for d, m in sorted(orphan_customers)[:MAX_EXAMPLES]),
            )
        )
    return issues


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def validate_dataset(sales: pd.DataFrame, customers: pd.DataFrame) -> ValidationReport:
    """Run every dataset-level rule and return a report. Never mutates input.

    Structural problems short-circuit the value checks, because running range
    logic against a frame with a missing column just produces noise on top of
    the real problem.
    """
    report = ValidationReport()

    structural: list[ValidationIssue] = []
    structural += _check_columns(sales, SALES_COLUMNS, "sales", "R001")
    structural += _check_columns(customers, CUSTOMERS_COLUMNS, "customers", "R002")
    if structural:
        report.issues.extend(structural)
        return report

    report.issues.extend(_check_missing_values(sales, SALES_COLUMNS, "sales", "R003"))
    report.issues.extend(_check_missing_values(customers, CUSTOMERS_COLUMNS, "customers", "R004"))
    report.issues.extend(_check_dates(sales, "sales", "R005"))
    report.issues.extend(_check_dates(customers, "customers", "R006"))
    report.issues.extend(_check_numeric_types(sales, SALES_NUMERIC, "sales", "R007"))
    report.issues.extend(_check_numeric_types(customers, CUSTOMERS_NUMERIC, "customers", "R008"))

    # Non-numeric or unparseable values make every downstream comparison
    # meaningless, so stop here if any were found.
    if report.errors:
        return report

    # Work on numeric copies from here on. Callers may hand us frames built
    # from raw dicts or from a CSV read, where a column can arrive as text that
    # merely looks numeric; comparing those against numbers raises instead of
    # validating. Copies keep the caller's frames untouched.
    sales = _coerce_numeric(sales, SALES_NUMERIC)
    customers = _coerce_numeric(customers, CUSTOMERS_NUMERIC)

    report.issues.extend(_check_duplicates(sales, ["date", "merchant_id", "product"], "sales", "R009"))
    report.issues.extend(_check_duplicates(customers, ["date", "merchant_id"], "customers", "R010"))
    report.issues.extend(_check_non_negative(sales, SALES_NUMERIC, "sales", "R014"))
    report.issues.extend(_check_non_negative(customers, CUSTOMERS_NUMERIC, "customers", "R015"))
    report.issues.extend(_check_orders_units(sales))
    report.issues.extend(_check_customer_split(customers))
    report.issues.extend(_check_revenue_consistency(sales))
    report.issues.extend(_check_profit_consistency(sales))
    report.issues.extend(_check_customers_vs_orders(sales, customers))
    report.issues.extend(_check_join_completeness(sales, customers))

    continuity_issues, restocks = _check_inventory_continuity(sales)
    report.issues.extend(continuity_issues)

    report.stats = {
        "sales_rows": int(len(sales)),
        "customer_rows": int(len(customers)),
        "merchants": int(sales["merchant_id"].nunique()),
        "products": int(sales["product"].nunique()),
        "categories": int(sales["category"].nunique()),
        "date_min": str(sales["date"].min()),
        "date_max": str(sales["date"].max()),
        "restock_events": restocks,
        "errors": len(report.errors),
        "warnings": len(report.warnings),
    }
    return report
