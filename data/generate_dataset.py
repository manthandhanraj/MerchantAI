"""Deterministic synthetic merchant dataset generator.

ALL DATA PRODUCED BY THIS SCRIPT IS SYNTHETIC. It is generated from the
hand-written business profiles below. MerchantAI does not use, and does not
claim access to, real Paytm merchant, customer or payment data.

Run from the project root:

    python data/generate_dataset.py                 # default: seed 42, 180 days
    python data/generate_dataset.py --summary       # also print a data-quality summary
    python data/generate_dataset.py --seed 7 --days 120
    python data/generate_dataset.py --out-dir data/scratch

The same seed always produces byte-identical CSVs, so the dataset can be
regenerated and diffed. The end date is fixed rather than `today()` for the
same reason — a moving window would silently change the output every day.

Output conforms to docs/DATA_SCHEMA.md. Every row is validated against
`SalesRecord` / `CustomerDailyRecord` before it is written.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

# This script lives in data/, so the project root is not on sys.path when it is
# run directly. Insert it so the locked schema models can be reused for validation.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.models.schemas import (  # noqa: E402
    CUSTOMERS_COLUMNS,
    SALES_COLUMNS,
    CustomerDailyRecord,
    SalesRecord,
)

DEFAULT_SEED = 42
DEFAULT_DAYS = 180
DEFAULT_END_DATE = date(2026, 9, 15)
RESTOCK_LEAD_DAYS = 3

# Festivals are positioned as a fraction of the generated window rather than as
# absolute dates, so they stay inside the range whatever --days is passed.
FESTIVAL_WINDOWS = (
    (0.42, 0.46),  # mid-window sale event
    (0.86, 0.94),  # main festival season near the end of the window
)


@dataclass(frozen=True)
class ProductProfile:
    """One product's behaviour over the whole window."""

    name: str
    category: str
    price: float
    cost_ratio: float  # expenses = units_sold * price * cost_ratio
    popularity: float  # share of the merchant's daily order volume
    lifecycle: float  # total multiplicative drift across the window (1.0 = flat)
    multi_unit_prob: float  # chance an order carries one extra unit
    opening_stock: int
    reorder_point: int
    reorder_qty: int
    festival_affinity: float = 1.0  # extra lift during festival windows


@dataclass(frozen=True)
class MerchantProfile:
    """One merchant's business shape. Hand-written so every pattern in the
    dataset is explainable rather than incidental."""

    merchant_id: str
    name: str
    base_orders: float  # average orders/day at the start of the window
    trend: float  # total multiplicative drift across the window
    weekday_factors: tuple[float, ...]  # Mon..Sun
    month_start_boost: float  # salary-week effect on days 1-5
    festival_boost: float
    orders_per_customer: float
    repeat_ceiling: float  # asymptotic repeat-customer share
    repeat_dip: float  # late-window retention decline (0.0 = none)
    products: tuple[ProductProfile, ...]


# --------------------------------------------------------------------------
# Merchant profiles
#
# Each merchant tells a different, deliberate story so Stages 4-6 have genuine
# patterns to find and the demo survives being questioned:
#   M001 growing, with a rising star and a declining product
#   M002 flat, high-volume, high-repeat, with a stock-out-prone staple
#   M003 declining, with a retention dip     <- the "why did sales drop?" case
#   M004 volatile, festival-driven, low repeat
# --------------------------------------------------------------------------
MERCHANTS: tuple[MerchantProfile, ...] = (
    MerchantProfile(
        merchant_id="M001",
        name="Sharma Electronics",
        base_orders=58.0,
        trend=1.18,
        weekday_factors=(0.92, 0.90, 0.95, 1.00, 1.12, 1.28, 1.05),
        month_start_boost=1.15,
        festival_boost=1.45,
        orders_per_customer=1.12,
        repeat_ceiling=0.58,
        repeat_dip=0.0,
        products=(
            ProductProfile("Wireless Earbuds", "Electronics", 1800.0, 0.70, 0.20, 1.10, 0.18, 150, 40, 180),
            ProductProfile("Smart Watch", "Electronics", 2600.0, 0.72, 0.12, 1.85, 0.10, 90, 25, 110, 1.35),
            ProductProfile("Power Bank", "Electronics", 1500.0, 0.70, 0.14, 0.58, 0.12, 110, 30, 100),
            ProductProfile("Bluetooth Speaker", "Electronics", 2200.0, 0.71, 0.09, 1.05, 0.10, 70, 20, 80, 1.20),
            ProductProfile("Phone Case", "Accessories", 250.0, 0.56, 0.20, 1.02, 0.35, 320, 90, 340),
            ProductProfile("Screen Guard", "Accessories", 150.0, 0.52, 0.15, 0.95, 0.40, 380, 110, 400),
            ProductProfile("USB-C Cable", "Accessories", 350.0, 0.58, 0.10, 1.12, 0.30, 260, 70, 280),
        ),
    ),
    MerchantProfile(
        merchant_id="M002",
        name="Gupta Kirana Store",
        base_orders=124.0,
        trend=1.03,
        weekday_factors=(0.96, 0.94, 0.98, 1.02, 1.10, 1.14, 0.98),
        month_start_boost=1.34,  # ration buying right after payday
        festival_boost=1.28,
        orders_per_customer=1.06,
        repeat_ceiling=0.86,  # a kirana store runs on regulars
        repeat_dip=0.0,
        products=(
            ProductProfile("Atta 5kg", "Grocery", 260.0, 0.82, 0.17, 1.05, 0.22, 200, 60, 240),
            ProductProfile("Cooking Oil 1L", "Grocery", 145.0, 0.84, 0.19, 1.08, 0.30, 180, 70, 200),
            ProductProfile("Rice 5kg", "Grocery", 340.0, 0.83, 0.13, 1.02, 0.20, 160, 50, 190),
            ProductProfile("Sugar 1kg", "Grocery", 48.0, 0.86, 0.12, 0.98, 0.35, 240, 80, 260),
            ProductProfile("Detergent 1kg", "Household", 120.0, 0.78, 0.11, 1.06, 0.25, 210, 65, 230),
            ProductProfile("Biscuits Pack", "Snacks", 60.0, 0.74, 0.14, 1.10, 0.45, 300, 100, 320),
            ProductProfile("Tea Powder 500g", "Beverages", 220.0, 0.75, 0.09, 1.04, 0.24, 150, 45, 170),
            ProductProfile("Milk Powder 500g", "Grocery", 290.0, 0.80, 0.05, 0.96, 0.18, 120, 35, 130),
        ),
    ),
    MerchantProfile(
        merchant_id="M003",
        name="Chai Point Cafe",
        base_orders=96.0,
        trend=0.82,  # the declining merchant
        weekday_factors=(0.88, 0.86, 0.92, 1.02, 1.22, 1.38, 1.24),
        month_start_boost=1.08,
        festival_boost=1.12,
        orders_per_customer=1.18,
        repeat_ceiling=0.72,
        repeat_dip=0.22,  # retention slides in the final stretch
        products=(
            ProductProfile("Masala Chai", "Beverages", 40.0, 0.32, 0.26, 0.92, 0.48, 400, 120, 420),
            ProductProfile("Filter Coffee", "Beverages", 50.0, 0.34, 0.16, 0.95, 0.40, 320, 100, 340),
            ProductProfile("Cold Coffee", "Beverages", 120.0, 0.38, 0.18, 0.55, 0.22, 260, 80, 260),
            ProductProfile("Veg Sandwich", "Food", 110.0, 0.42, 0.15, 0.88, 0.18, 200, 60, 210),
            ProductProfile("Samosa", "Food", 25.0, 0.30, 0.17, 1.04, 0.55, 380, 120, 400),
            ProductProfile("Cookies", "Snacks", 60.0, 0.36, 0.08, 0.90, 0.30, 220, 70, 230),
        ),
    ),
    MerchantProfile(
        merchant_id="M004",
        name="Trendy Threads",
        base_orders=44.0,
        trend=1.09,
        weekday_factors=(0.80, 0.78, 0.86, 0.98, 1.22, 1.52, 1.34),
        month_start_boost=1.18,
        festival_boost=2.10,  # fashion lives on festival season
        orders_per_customer=1.05,
        repeat_ceiling=0.34,  # apparel repeats far less than groceries
        repeat_dip=0.0,
        products=(
            ProductProfile("Cotton Kurta", "Apparel", 899.0, 0.52, 0.22, 1.12, 0.20, 140, 40, 160, 1.60),
            ProductProfile("Denim Jeans", "Apparel", 1450.0, 0.55, 0.17, 1.05, 0.12, 110, 30, 120),
            ProductProfile("T-Shirt", "Apparel", 499.0, 0.50, 0.24, 1.08, 0.28, 200, 60, 220),
            ProductProfile("Formal Shirt", "Apparel", 1100.0, 0.54, 0.14, 0.94, 0.14, 120, 35, 130),
            ProductProfile("Saree", "Ethnic Wear", 2200.0, 0.58, 0.13, 1.20, 0.10, 90, 25, 100, 2.20),
            ProductProfile("Scarf", "Accessories", 350.0, 0.46, 0.10, 1.00, 0.32, 160, 50, 170),
        ),
    ),
)


# --------------------------------------------------------------------------
# Seasonality
# --------------------------------------------------------------------------
def festival_multiplier(progress: float, merchant: MerchantProfile) -> float:
    """Smooth lift while inside a festival window; 1.0 outside one."""
    for start, end in FESTIVAL_WINDOWS:
        if start <= progress <= end:
            # Triangular ramp so the spike builds and fades instead of
            # switching on for a block of days.
            mid = (start + end) / 2
            half = (end - start) / 2
            closeness = 1.0 - abs(progress - mid) / half
            return 1.0 + (merchant.festival_boost - 1.0) * closeness
    return 1.0


def day_multiplier(day: date, progress: float, merchant: MerchantProfile) -> float:
    """Combined calendar effects for one day: weekday rhythm, salary week,
    festival season and the merchant's slow trend."""
    weekday = merchant.weekday_factors[day.weekday()]
    month_start = merchant.month_start_boost if day.day <= 5 else 1.0
    festival = festival_multiplier(progress, merchant)
    trend = 1.0 + (merchant.trend - 1.0) * progress
    return weekday * month_start * festival * trend


def product_multiplier(progress: float, product: ProductProfile, in_festival: bool) -> float:
    """A product's own drift across the window, plus festival affinity."""
    lifecycle = 1.0 + (product.lifecycle - 1.0) * progress
    affinity = product.festival_affinity if in_festival else 1.0
    return lifecycle * affinity


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
def generate_merchant_rows(
    merchant: MerchantProfile,
    days: list[date],
    rng: np.random.Generator,
) -> tuple[list[dict], list[dict]]:
    """Generate sales and daily-customer rows for one merchant.

    Returns (sales_rows, customer_rows). A day where the merchant sold nothing
    produces no rows at all, matching the "absent rows, not blank cells"
    convention in docs/DATA_SCHEMA.md.
    """
    sales_rows: list[dict] = []
    customer_rows: list[dict] = []

    stock = {p.name: p.opening_stock for p in merchant.products}
    pending_restock: dict[str, int | None] = {p.name: None for p in merchant.products}
    customer_base = 0
    n = len(days)

    for index, day in enumerate(days):
        progress = index / (n - 1) if n > 1 else 0.0
        in_festival = festival_multiplier(progress, merchant) > 1.0
        day_factor = day_multiplier(day, progress, merchant)
        day_orders = 0
        day_rows: list[dict] = []

        for product in merchant.products:
            # Restock arrives at the start of the day.
            if pending_restock[product.name] == index:
                stock[product.name] += product.reorder_qty
                pending_restock[product.name] = None

            demand_rate = (
                merchant.base_orders
                * product.popularity
                * day_factor
                * product_multiplier(progress, product, in_festival)
            )
            # Gamma jitter on the rate keeps day-to-day variation from looking
            # like clean Poisson noise around a smooth curve.
            demand_rate *= rng.gamma(shape=25.0, scale=1.0 / 25.0)
            orders = int(rng.poisson(max(demand_rate, 0.0)))

            if orders == 0:
                _maybe_reorder(product, stock, pending_restock, index)
                continue

            # One product per order (locked generation rule), but an order can
            # carry a second unit.
            units_wanted = orders + int(rng.binomial(orders, product.multi_unit_prob))
            units_sold = min(units_wanted, stock[product.name])

            if units_sold == 0:  # stocked out
                _maybe_reorder(product, stock, pending_restock, index)
                continue

            # A stock-out can cap fulfilment, so orders must be capped too or
            # the orders <= units_sold invariant would break.
            orders_filled = min(orders, units_sold)
            stock[product.name] -= units_sold

            # Occasional promotion, capped so the product never sells below cost.
            max_discount = (1.0 - product.cost_ratio) * 0.5
            discount = float(rng.uniform(0.05, max_discount)) if rng.random() < 0.07 else 0.0

            revenue = round(units_sold * product.price * (1.0 - discount), 2)
            expenses = round(units_sold * product.price * product.cost_ratio, 2)

            day_rows.append(
                {
                    "date": day.isoformat(),
                    "merchant_id": merchant.merchant_id,
                    "product": product.name,
                    "category": product.category,
                    "orders": orders_filled,
                    "units_sold": units_sold,
                    "revenue": f"{revenue:.2f}",
                    "expenses": f"{expenses:.2f}",
                    "inventory": stock[product.name],
                }
            )
            day_orders += orders_filled
            _maybe_reorder(product, stock, pending_restock, index)

        if not day_rows:
            continue

        sales_rows.extend(day_rows)

        # Customers are derived from the day's orders, which is what keeps the
        # customers <= orders invariant true by construction.
        customers = min(day_orders, max(1, round(day_orders / merchant.orders_per_customer)))
        repeat = _repeat_customers(customers, customer_base, progress, merchant, rng)
        new = customers - repeat
        customer_base += new

        customer_rows.append(
            {
                "date": day.isoformat(),
                "merchant_id": merchant.merchant_id,
                "customers": customers,
                "new_customers": new,
                "repeat_customers": repeat,
            }
        )

    return sales_rows, customer_rows


def _maybe_reorder(
    product: ProductProfile,
    stock: dict[str, int],
    pending_restock: dict[str, int | None],
    index: int,
) -> None:
    """Schedule a delivery once stock falls to the reorder point. The lead time
    is what produces occasional genuine stock-outs rather than perfect supply."""
    if stock[product.name] <= product.reorder_point and pending_restock[product.name] is None:
        pending_restock[product.name] = index + RESTOCK_LEAD_DAYS


def _repeat_customers(
    customers: int,
    customer_base: int,
    progress: float,
    merchant: MerchantProfile,
    rng: np.random.Generator,
) -> int:
    """Repeat share grows as the customer base builds, then optionally decays
    for merchants carrying a retention problem."""
    if customer_base == 0:
        return 0

    saturation = 1.0 - np.exp(-customer_base / 400.0)
    probability = merchant.repeat_ceiling * saturation

    if merchant.repeat_dip and progress > 0.65:
        decline = (progress - 0.65) / 0.35
        probability *= 1.0 - merchant.repeat_dip * decline

    probability = float(np.clip(probability, 0.0, 0.95))
    return int(min(rng.binomial(customers, probability), customer_base))


def build_dataset(
    days: int = DEFAULT_DAYS,
    seed: int = DEFAULT_SEED,
    end_date: date = DEFAULT_END_DATE,
) -> tuple[list[dict], list[dict]]:
    """Generate the full dataset. Deterministic for a given (days, seed, end_date)."""
    if days < 2:
        raise ValueError("days must be at least 2 so trends and continuity exist")

    rng = np.random.default_rng(seed)
    start_date = end_date - timedelta(days=days - 1)
    calendar = [start_date + timedelta(days=i) for i in range(days)]

    sales: list[dict] = []
    customers: list[dict] = []
    for merchant in MERCHANTS:
        merchant_sales, merchant_customers = generate_merchant_rows(merchant, calendar, rng)
        sales.extend(merchant_sales)
        customers.extend(merchant_customers)

    # Canonical sort order from docs/DATA_SCHEMA.md, so output diffs stay readable.
    sales.sort(key=lambda r: (r["date"], r["merchant_id"], r["product"]))
    customers.sort(key=lambda r: (r["date"], r["merchant_id"]))
    return sales, customers


def validate_rows(sales: list[dict], customers: list[dict]) -> None:
    """Row-level validation against the locked Stage 1 models before writing.
    Cross-row invariants are checked separately by services/validation.py."""
    for row in sales:
        SalesRecord(**row)
    for row in customers:
        CustomerDailyRecord(**row)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" plus an explicit \n terminator keeps output identical on
    # Windows and POSIX, which matters for reproducible diffs.
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarise(sales: list[dict], customers: list[dict]) -> str:
    """Basic sanity figures, printed with --summary."""
    revenue = sum(float(r["revenue"]) for r in sales)
    expenses = sum(float(r["expenses"]) for r in sales)
    orders = sum(int(r["orders"]) for r in sales)
    units = sum(int(r["units_sold"]) for r in sales)
    dates = sorted({r["date"] for r in sales})
    merchants = sorted({r["merchant_id"] for r in sales})
    products = {r["product"] for r in sales}
    categories = {r["category"] for r in sales}

    lines = [
        f"sales rows        : {len(sales)}",
        f"customer rows     : {len(customers)}",
        f"date range        : {dates[0]} -> {dates[-1]} ({len(dates)} days)",
        f"merchants         : {len(merchants)} ({', '.join(merchants)})",
        f"products          : {len(products)}",
        f"categories        : {len(categories)}",
        f"total orders      : {orders:,}",
        f"total units sold  : {units:,}",
        f"total revenue     : INR {revenue:,.2f}",
        f"gross profit      : INR {revenue - expenses:,.2f} ({(revenue - expenses) / revenue:.1%} margin)",
        f"avg order value   : INR {revenue / orders:,.2f}",
    ]
    return "\n".join(lines)


def _display_path(path: Path) -> str:
    """Show a project-relative path when possible, otherwise the absolute one.
    `--out-dir` may legitimately point outside the project."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the synthetic MerchantAI dataset (deterministic).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"RNG seed (default {DEFAULT_SEED})")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help=f"days of history (default {DEFAULT_DAYS})")
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=DEFAULT_END_DATE,
        help=f"last day of the window, YYYY-MM-DD (default {DEFAULT_END_DATE.isoformat()})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/raw"),
        help="output directory, relative to the project root (default data/raw)",
    )
    parser.add_argument("--summary", action="store_true", help="print a data-quality summary")
    args = parser.parse_args(argv)

    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir

    sales, customers = build_dataset(days=args.days, seed=args.seed, end_date=args.end_date)
    validate_rows(sales, customers)

    sales_path = out_dir / "merchant_sales.csv"
    customers_path = out_dir / "merchant_customers_daily.csv"
    write_csv(sales_path, SALES_COLUMNS, sales)
    write_csv(customers_path, CUSTOMERS_COLUMNS, customers)

    print(f"seed={args.seed} days={args.days} end_date={args.end_date.isoformat()}")
    print(f"wrote {len(sales):,} rows -> {_display_path(sales_path)}")
    print(f"wrote {len(customers):,} rows -> {_display_path(customers_path)}")
    if args.summary:
        print()
        print(summarise(sales, customers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
