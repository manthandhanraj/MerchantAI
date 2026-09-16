"""Reusable metric computations over the validated dataset.

This is the analytics layer every later stage shares. The dashboard (Stage 3),
the insight engine (Stage 4), the recommendations (Stage 5) and the assistant
(Stage 6) all call these functions rather than recomputing aggregates, which is
what keeps a number on the dashboard identical to the same number quoted by the
assistant.

Formulas come from the "Derived metrics" table in docs/DATA_SCHEMA.md. Nothing
here is stored — every metric is computed on demand from the raw columns.

No FastAPI imports: this module must stay usable outside a request.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from backend.app.services.data_loader import Dataset
from backend.app.utils.calculations import growth_rate, round_money, round_rate, safe_divide

# Days of stock cover below which a product is flagged. Used by Stage 5's
# inventory advice; defined here so the thresholds have one home.
CRITICAL_COVER_DAYS = 3.0
LOW_COVER_DAYS = 7.0

# Window used for sales-velocity calculations (inventory cover, recent trend).
VELOCITY_WINDOW_DAYS = 7


def filter_dataset(
    dataset: Dataset,
    merchant_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Dataset:
    """Narrow a dataset by merchant and/or date range. Both bounds inclusive."""
    sales = dataset.sales
    customers = dataset.customers

    if merchant_id is not None:
        sales = sales[sales["merchant_id"] == merchant_id]
        customers = customers[customers["merchant_id"] == merchant_id]
    if start is not None:
        stamp = pd.Timestamp(start)
        sales = sales[sales["date"] >= stamp]
        customers = customers[customers["date"] >= stamp]
    if end is not None:
        stamp = pd.Timestamp(end)
        sales = sales[sales["date"] <= stamp]
        customers = customers[customers["date"] <= stamp]

    return Dataset(sales=sales.copy(), customers=customers.copy(), validation=dataset.validation)


# --------------------------------------------------------------------------
# Daily series
# --------------------------------------------------------------------------
def daily_metrics(dataset: Dataset) -> pd.DataFrame:
    """One row per date with every headline metric.

    This is the backbone series: trends, growth comparisons and the forecast
    all build on it. When the dataset spans several merchants the rows are
    summed across them, so `customers` becomes customer-days rather than
    distinct customers (see docs/DATA_SCHEMA.md).
    """
    if dataset.is_empty():
        return pd.DataFrame(
            columns=[
                "date", "revenue", "orders", "units_sold", "expenses", "profit",
                "profit_margin", "average_order_value", "customers", "new_customers",
                "repeat_customers", "repeat_customer_rate", "new_customer_rate",
                "revenue_per_customer",
            ]
        )

    sales = (
        dataset.sales.groupby("date", as_index=False)[["revenue", "orders", "units_sold", "expenses"]]
        .sum()
    )
    customers = (
        dataset.customers.groupby("date", as_index=False)[
            ["customers", "new_customers", "repeat_customers"]
        ].sum()
        if not dataset.customers.empty
        else pd.DataFrame(columns=["date", "customers", "new_customers", "repeat_customers"])
    )

    frame = sales.merge(customers, on="date", how="left")
    for column in ("customers", "new_customers", "repeat_customers"):
        frame[column] = frame[column].fillna(0).astype("int64")

    frame["profit"] = frame["revenue"] - frame["expenses"]
    frame["profit_margin"] = safe_divide(frame["profit"], frame["revenue"])
    frame["average_order_value"] = safe_divide(frame["revenue"], frame["orders"])
    frame["repeat_customer_rate"] = safe_divide(frame["repeat_customers"], frame["customers"])
    frame["new_customer_rate"] = safe_divide(frame["new_customers"], frame["customers"])
    frame["revenue_per_customer"] = safe_divide(frame["revenue"], frame["customers"])

    return frame.sort_values("date").reset_index(drop=True)


def period_growth(daily: pd.DataFrame, column: str = "revenue", window: int | None = None) -> float:
    """Growth of the most recent `window` days against the `window` days before.

    Defaults to a 7-day comparison, shrinking automatically when the period is
    too short to support it. Returns 0.0 when there is no comparable prior
    window — an honest answer rather than a fabricated trend.
    """
    if daily.empty or column not in daily.columns:
        return 0.0

    usable = len(daily) // 2
    size = min(window or VELOCITY_WINDOW_DAYS, usable)
    if size < 1:
        return 0.0

    recent = float(daily[column].tail(size).sum())
    prior = float(daily[column].tail(size * 2).head(size).sum())
    return growth_rate(recent, prior)


# --------------------------------------------------------------------------
# Headline summary
# --------------------------------------------------------------------------
def summary_metrics(dataset: Dataset) -> dict:
    """Headline totals for the whole filtered period, ready for JSON."""
    daily = daily_metrics(dataset)

    if daily.empty:
        return {
            "period_start": None, "period_end": None, "days": 0,
            "total_revenue": 0.0, "total_orders": 0, "total_units_sold": 0,
            "total_expenses": 0.0, "total_profit": 0.0, "profit_margin": 0.0,
            "average_order_value": 0.0, "total_customers": 0, "new_customers": 0,
            "repeat_customers": 0, "repeat_customer_rate": 0.0,
            "revenue_per_customer": 0.0, "revenue_growth_rate": 0.0,
            "active_products": 0, "active_categories": 0,
        }

    revenue = float(daily["revenue"].sum())
    expenses = float(daily["expenses"].sum())
    orders = int(daily["orders"].sum())
    customers = int(daily["customers"].sum())
    profit = revenue - expenses

    return {
        "period_start": daily["date"].min().date().isoformat(),
        "period_end": daily["date"].max().date().isoformat(),
        "days": int(len(daily)),
        "total_revenue": round_money(revenue),
        "total_orders": orders,
        "total_units_sold": int(daily["units_sold"].sum()),
        "total_expenses": round_money(expenses),
        "total_profit": round_money(profit),
        "profit_margin": round_rate(safe_divide(profit, revenue)),
        "average_order_value": round_money(safe_divide(revenue, orders)),
        "total_customers": customers,
        "new_customers": int(daily["new_customers"].sum()),
        "repeat_customers": int(daily["repeat_customers"].sum()),
        "repeat_customer_rate": round_rate(safe_divide(int(daily["repeat_customers"].sum()), customers)),
        "revenue_per_customer": round_money(safe_divide(revenue, customers)),
        "revenue_growth_rate": round_rate(period_growth(daily, "revenue")),
        "active_products": int(dataset.sales["product"].nunique()),
        "active_categories": int(dataset.sales["category"].nunique()),
    }


# --------------------------------------------------------------------------
# Product and category performance
# --------------------------------------------------------------------------
def product_performance(dataset: Dataset) -> pd.DataFrame:
    """Per-product totals over the filtered period, sorted by revenue."""
    if dataset.is_empty():
        return pd.DataFrame(
            columns=[
                "merchant_id", "product", "category", "revenue", "orders", "units_sold",
                "expenses", "profit", "profit_margin", "average_order_value",
                "avg_unit_price", "revenue_share", "active_days",
            ]
        )

    grouped = dataset.sales.groupby(["merchant_id", "product", "category"], as_index=False).agg(
        revenue=("revenue", "sum"),
        orders=("orders", "sum"),
        units_sold=("units_sold", "sum"),
        expenses=("expenses", "sum"),
        active_days=("date", "nunique"),
    )

    grouped["profit"] = grouped["revenue"] - grouped["expenses"]
    grouped["profit_margin"] = safe_divide(grouped["profit"], grouped["revenue"])
    grouped["average_order_value"] = safe_divide(grouped["revenue"], grouped["orders"])
    # Realised price after discounts — the schema has no price column because
    # this derives it exactly. See docs/DATA_PIPELINE.md.
    grouped["avg_unit_price"] = safe_divide(grouped["revenue"], grouped["units_sold"])
    grouped["revenue_share"] = safe_divide(grouped["revenue"], float(grouped["revenue"].sum()))

    return grouped.sort_values("revenue", ascending=False).reset_index(drop=True)


def category_performance(dataset: Dataset) -> pd.DataFrame:
    """Per-category totals over the filtered period, sorted by revenue."""
    if dataset.is_empty():
        return pd.DataFrame(
            columns=[
                "category", "revenue", "orders", "units_sold", "expenses", "profit",
                "profit_margin", "revenue_share", "products",
            ]
        )

    grouped = dataset.sales.groupby("category", as_index=False).agg(
        revenue=("revenue", "sum"),
        orders=("orders", "sum"),
        units_sold=("units_sold", "sum"),
        expenses=("expenses", "sum"),
        products=("product", "nunique"),
    )

    grouped["profit"] = grouped["revenue"] - grouped["expenses"]
    grouped["profit_margin"] = safe_divide(grouped["profit"], grouped["revenue"])
    grouped["revenue_share"] = safe_divide(grouped["revenue"], float(grouped["revenue"].sum()))

    return grouped.sort_values("revenue", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------
def inventory_position(dataset: Dataset) -> pd.DataFrame:
    """Latest stock snapshot per product, with sales velocity and cover.

    `days_of_inventory_cover` is NaN when a product had no sales in the
    velocity window: dividing by zero demand would imply infinite cover, which
    is a different situation from healthy stock and is labelled as such.
    """
    columns = [
        "merchant_id", "product", "category", "inventory", "as_of_date",
        "avg_daily_units", "days_of_inventory_cover", "stock_status",
    ]
    if dataset.is_empty():
        return pd.DataFrame(columns=columns)

    sales = dataset.sales
    latest_idx = sales.groupby(["merchant_id", "product"])["date"].idxmax()
    latest = sales.loc[latest_idx, ["merchant_id", "product", "category", "inventory", "date"]].copy()
    latest = latest.rename(columns={"date": "as_of_date"})

    # Velocity over the final VELOCITY_WINDOW_DAYS of the period, so cover
    # reflects current demand rather than a six-month average.
    cutoff = sales["date"].max() - pd.Timedelta(days=VELOCITY_WINDOW_DAYS - 1)
    recent = sales[sales["date"] >= cutoff]
    velocity = recent.groupby(["merchant_id", "product"], as_index=False)["units_sold"].sum()
    velocity["avg_daily_units"] = velocity["units_sold"] / VELOCITY_WINDOW_DAYS
    velocity = velocity.drop(columns="units_sold")

    frame = latest.merge(velocity, on=["merchant_id", "product"], how="left")
    frame["avg_daily_units"] = frame["avg_daily_units"].fillna(0.0)

    cover = frame["inventory"] / frame["avg_daily_units"].replace(0, np.nan)
    frame["days_of_inventory_cover"] = cover
    frame["stock_status"] = [
        _stock_status(inventory, days) for inventory, days in zip(frame["inventory"], cover)
    ]

    return frame[columns].sort_values(["merchant_id", "product"]).reset_index(drop=True)


def _stock_status(inventory: int, days_cover: float) -> str:
    if inventory <= 0:
        return "out_of_stock"
    if pd.isna(days_cover):
        return "no_recent_sales"
    if days_cover < CRITICAL_COVER_DAYS:
        return "critical"
    if days_cover < LOW_COVER_DAYS:
        return "low"
    return "healthy"


def inventory_movement(dataset: Dataset) -> pd.DataFrame:
    """Stock movement per product over time, with restocks made explicit.

    `restock_units` is the gap between the closing stock we observe and the
    closing stock implied by sales alone. The dataset has no restock column, so
    this is how a delivery becomes visible to later stages.
    """
    columns = ["date", "merchant_id", "product", "units_sold", "inventory", "restock_units"]
    if dataset.is_empty():
        return pd.DataFrame(columns=columns)

    frame = dataset.sales.sort_values(["merchant_id", "product", "date"]).copy()
    previous = frame.groupby(["merchant_id", "product"])["inventory"].shift(1)
    implied = previous - frame["units_sold"]
    frame["restock_units"] = (frame["inventory"] - implied).fillna(0).clip(lower=0).astype("int64")

    return frame[columns].reset_index(drop=True)


# --------------------------------------------------------------------------
# Merchant directory
# --------------------------------------------------------------------------
def merchant_directory(dataset: Dataset) -> list[dict]:
    """One entry per merchant for the frontend's merchant selector."""
    if dataset.is_empty():
        return []

    grouped = dataset.sales.groupby("merchant_id", as_index=False).agg(
        total_revenue=("revenue", "sum"),
        total_orders=("orders", "sum"),
        products=("product", "nunique"),
        categories=("category", "nunique"),
        first_date=("date", "min"),
        last_date=("date", "max"),
    )

    return [
        {
            "merchant_id": str(row.merchant_id),
            "total_revenue": round_money(row.total_revenue),
            "total_orders": int(row.total_orders),
            "products": int(row.products),
            "categories": int(row.categories),
            "first_date": row.first_date.date().isoformat(),
            "last_date": row.last_date.date().isoformat(),
        }
        for row in grouped.itertuples()
    ]
