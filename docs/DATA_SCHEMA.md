# Dataset Schema

Status: **locked in Stage 1**. The machine-readable twin of this document is
[`backend/app/models/schemas.py`](../backend/app/models/schemas.py).
**If a column changes, change it in both places.**

All data is **synthetic**. MerchantAI does not use real or private merchant data.

## Why two files

The MVP uses two flat CSVs joined on `(date, merchant_id)`:

| File | Grain | Powers |
| --- | --- | --- |
| `merchant_sales.csv` | one row per `(date, merchant_id, product)` | revenue, orders, products, inventory, trends |
| `merchant_customers_daily.csv` | one row per `(date, merchant_id)` | customer counts, retention, repeat rate |

Customer counts live at the **daily** grain deliberately. A customer who buys
two products in one day would appear in two product rows, so per-product
customer columns cannot be summed without double counting — and the natural
instinct in pandas is to call `.sum()`. Splitting the grain makes the correct
thing also the easy thing. The cost is a single `pd.merge`.

## File 1 — `data/raw/merchant_sales.csv`

Grain: one row per `(date, merchant_id, product)`. Sorted by `date, merchant_id, product`.

| Column | Type | Description | Aggregation |
| --- | --- | --- | --- |
| `date` | date `YYYY-MM-DD` | Business date | key |
| `merchant_id` | string, e.g. `M001` | Merchant identifier | key |
| `product` | string | Product name | key |
| `category` | string | Product category, e.g. `Electronics` | dimension |
| `orders` | int ≥ 0 | Orders for this product that day | **additive** |
| `units_sold` | int ≥ 0 | Units sold | **additive** |
| `revenue` | float ≥ 0 (INR) | Gross revenue | **additive** |
| `expenses` | float ≥ 0 (INR) | Cost attributable to this product | **additive** |
| `inventory` | int ≥ 0 | **Closing** stock in units at end of day | **point-in-time — never sum across dates** |

`inventory` is the one trap in this file. Summing it across dates produces a
meaningless number. Take the latest date's value for stock on hand.

`units_sold` is carried separately from `orders` because inventory advice needs
sales *velocity in units* against stock on hand. Without it, days-of-cover is
wrong whenever an order contains more than one unit.

## File 2 — `data/raw/merchant_customers_daily.csv`

Grain: one row per `(date, merchant_id)`. Sorted by `date, merchant_id`.

| Column | Type | Description | Aggregation |
| --- | --- | --- | --- |
| `date` | date `YYYY-MM-DD` | Business date | key |
| `merchant_id` | string | Merchant identifier | key |
| `customers` | int ≥ 0 | Distinct customers who purchased that day | **additive across dates only as "customer-days"** |
| `new_customers` | int ≥ 0 | First-ever purchase that day | additive |
| `repeat_customers` | int ≥ 0 | Had purchased before | additive |

Summing `customers` over a week gives customer-*visits*, not distinct weekly
customers. Label it accordingly in the UI; do not call it "unique customers"
for any window longer than a day.

## Invariants

Enforced by `schemas.py` and by `tests/test_data_schema.py`. Stage 2's generated
dataset must satisfy all of them.

1. `new_customers + repeat_customers == customers`
2. `orders <= units_sold` (an order carries at least one unit)
3. `units_sold > 0` implies `orders > 0`
4. `customers <= orders` at the daily level
5. All numeric columns are `>= 0`
6. Key tuples are unique within each file
7. Every `(date, merchant_id)` in sales has a matching row in customers
8. Inventory continuity: `inventory[t] == inventory[t-1] - units_sold[t]` per
   product, except on restock days (restocks raise it — an expected, visible jump)

### Generation rule that makes the maths work

**In the synthetic dataset, each order contains exactly one product.** This makes
`orders` fully additive across products, so `AOV = revenue / orders` is correct
at product, merchant and portfolio level alike. Stage 2 must preserve this rule.
It is a simplification, and it is the reason the arithmetic is trustworthy.

## Derived metrics

Computed at request time in `services/metrics.py` — **never stored in the CSVs.**
Storing them would let them drift out of sync with their inputs.

| Metric | Formula | Notes |
| --- | --- | --- |
| `profit` | `revenue - expenses` | |
| `profit_margin` | `profit / revenue` | Guard `revenue == 0` |
| `average_order_value` | `revenue / orders` | Guard `orders == 0` |
| `growth_rate` | `(current - previous) / previous` | Comparable windows, e.g. last 7d vs prior 7d. Guard `previous == 0` |
| `repeat_customer_rate` | `repeat_customers / customers` | Headline retention signal |
| `new_customer_rate` | `new_customers / customers` | Acquisition signal |
| `revenue_per_customer` | `revenue / customers` | Join both files first |
| `days_of_inventory_cover` | `inventory / mean(units_sold over last 7d)` | Drives inventory advice; guard divide-by-zero |
| `avg_unit_price` | `revenue / units_sold` | Realised price after discount. This is why the schema needs no price column |

Every division above needs a zero guard. A quiet day with zero orders is normal
data, not an error, and must not produce `inf` or `NaN` in the UI.

## Conventions

- **Dates**: `YYYY-MM-DD`, no timestamps, no timezones. Daily grain throughout.
- **Currency**: INR, plain numbers, two decimals, no symbols or separators in CSV.
- **Merchant ids**: `M001`, `M002`, … zero-padded to three digits.
- **Encoding**: UTF-8, comma-separated, `\n` line endings, header row required.
- **Missing data**: absent rows, not blank cells. A day with no sales for a
  product simply has no row for it.

## Sample data

[`data/sample/`](../data/sample/) holds a hand-built two-merchant, three-day
extract that satisfies every invariant above. It exists to prove this schema is
valid and loadable, and is validated by `tests/test_data_schema.py` on every run.

It is **not** the demo dataset. Stage 2 generates the real synthetic dataset into
`data/raw/`. Do not build features against the sample files.

## Notes for Stage 2 — done

Stage 2 is complete; see [DATA_PIPELINE.md](DATA_PIPELINE.md) for how the
dataset is generated, validated and loaded. The original brief was:

- Generate into `data/raw/` using exactly the column names and order above.
- Target roughly 3–6 months of daily history so trend and growth comparisons
  have something to work with, across a handful of merchants and ~5–10 products each.
- Build in realistic, *explainable* signal — weekly seasonality, a category
  trending up, one product declining, a stock-out risk, a retention dip. The
  intelligence layers in Stages 4–6 need something real to find, and the demo
  needs findings that hold up when questioned.
- Commit the generated CSVs. They are small and synthetic, and committing them
  keeps deployment free of a data-provisioning step.
- Reuse `SalesRecord` / `CustomerDailyRecord` to validate output before writing.
