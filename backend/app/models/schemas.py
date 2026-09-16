"""Canonical dataset contract for MerchantAI.

This module is the machine-readable twin of `docs/DATA_SCHEMA.md`. If a
column changes, change it in BOTH places.

The MVP uses two flat CSVs joined on (date, merchant_id):

  1. merchant_sales.csv            - grain: one row per (date, merchant_id, product)
  2. merchant_customers_daily.csv  - grain: one row per (date, merchant_id)

Customer counts live at the daily grain on purpose: a customer can buy more
than one product in a day, so per-product customer columns cannot be summed
without double counting. See docs/DATA_SCHEMA.md for the full rationale.
"""

from datetime import date as Date

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Column order used when reading/writing the CSVs. Stage 2 generates files
# in exactly this order so diffs stay readable.
SALES_COLUMNS: list[str] = [
    "date",
    "merchant_id",
    "product",
    "category",
    "orders",
    "units_sold",
    "revenue",
    "expenses",
    "inventory",
]

CUSTOMERS_COLUMNS: list[str] = [
    "date",
    "merchant_id",
    "customers",
    "new_customers",
    "repeat_customers",
]


class SalesRecord(BaseModel):
    """One product's trading activity for one merchant on one day."""

    model_config = ConfigDict(extra="forbid")

    date: Date = Field(description="Business date (YYYY-MM-DD).")
    merchant_id: str = Field(min_length=1, description="Merchant identifier, e.g. 'M001'.")
    product: str = Field(min_length=1, description="Product name.")
    category: str = Field(min_length=1, description="Product category, e.g. 'Electronics'.")

    orders: int = Field(ge=0, description="Orders placed for this product. Additive.")
    units_sold: int = Field(ge=0, description="Units sold. Additive.")
    revenue: float = Field(ge=0, description="Gross revenue in INR. Additive.")
    expenses: float = Field(ge=0, description="Cost attributable to this product in INR. Additive.")
    inventory: int = Field(ge=0, description="Closing stock in units. Point-in-time, NOT additive across dates.")

    @model_validator(mode="after")
    def check_invariants(self) -> "SalesRecord":
        # Synthetic data is generated with one product per order, so an
        # order can carry several units but never fewer than one.
        if self.orders > self.units_sold:
            raise ValueError(
                f"orders ({self.orders}) cannot exceed units_sold ({self.units_sold})"
            )
        if self.units_sold > 0 and self.orders == 0:
            raise ValueError("units_sold > 0 requires orders > 0")
        return self


class CustomerDailyRecord(BaseModel):
    """Distinct-customer counts for one merchant on one day."""

    model_config = ConfigDict(extra="forbid")

    date: Date = Field(description="Business date (YYYY-MM-DD).")
    merchant_id: str = Field(min_length=1, description="Merchant identifier, e.g. 'M001'.")

    customers: int = Field(ge=0, description="Distinct customers who purchased that day.")
    new_customers: int = Field(ge=0, description="Customers making their first-ever purchase.")
    repeat_customers: int = Field(ge=0, description="Customers who had purchased before.")

    @model_validator(mode="after")
    def check_split(self) -> "CustomerDailyRecord":
        total = self.new_customers + self.repeat_customers
        if total != self.customers:
            raise ValueError(
                f"new_customers + repeat_customers ({total}) must equal customers ({self.customers})"
            )
        return self
