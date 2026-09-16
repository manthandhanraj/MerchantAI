# Stage 2 — Completion Report

**Status: complete.** The dataset is generated, validated and reproducible; the
processing pipeline is in place and Stage 3 can start against it.

No Stage 1 decision was changed and no working Stage 1 code was rewritten.

## What was built

```
data/generate_dataset.py -> data/raw/*.csv -> validation -> loader -> metrics -> API
```

| Concern | Module |
| --- | --- |
| Generation | `data/generate_dataset.py` |
| Dataset-level validation | `backend/app/services/validation.py` |
| Load / normalise / cache | `backend/app/services/data_loader.py` |
| Reusable metrics | `backend/app/services/metrics.py` |
| Numeric helpers | `backend/app/utils/calculations.py` |
| API | `backend/app/routes/dataset.py` |

Full detail: [DATA_PIPELINE.md](DATA_PIPELINE.md).

## Dataset

4 merchants × 180 days (2026-03-20 → 2026-09-15), 27 products, 9 categories.

| File | Rows | Size |
| --- | --- | --- |
| `data/raw/merchant_sales.csv` | 4,814 | 292 KB |
| `data/raw/merchant_customers_daily.csv` | 720 | 18 KB |

Deterministic: seed 42 with a **fixed** end date regenerates byte-identical
files (verified by checksum and asserted in tests).

All data is synthetic. No real or private Paytm data is used, and
`/api/dataset/summary` returns `"synthetic": true` so this stays visible from
the API itself.

Each merchant carries a deliberate story so Stages 4–6 have real patterns to
find:

| Merchant | Shape | Measured |
| --- | --- | --- |
| M001 Sharma Electronics | Growing | +31% revenue; Smart Watch +101%, Power Bank −18% |
| M002 Gupta Kirana Store | Flat, high repeat | +7%; repeat rate 66% → 86% |
| M003 Chai Point Cafe | **Declining + retention dip** | −33%; repeat rate peaks 72% then falls to 60% |
| M004 Trendy Threads | Festival-driven | Festival days 3.2× the median |

## Schema

Unchanged from Stage 1. Two CSVs joined on `(date, merchant_id)`:

- `merchant_sales.csv` — `date, merchant_id, product, category, orders, units_sold, revenue, expenses, inventory`
- `merchant_customers_daily.csv` — `date, merchant_id, customers, new_customers, repeat_customers`

**Pricing was added without a schema change.** `avg_unit_price = revenue / units_sold`
is exact and reflects the realised price after discount, so no price column was
needed. Recorded in [DATA_SCHEMA.md](DATA_SCHEMA.md).

## Validation rules

21 rules. The two the Stage 1 audit flagged as unenforceable at row level are
the reason this layer exists.

Structural: required columns (R001/R002) · no missing values (R003/R004) ·
date format (R005/R006) · numeric types (R007/R008) · duplicate keys (R009/R010).

Row logic: `orders <= units_sold` (R011) · units imply orders (R012) ·
`new + repeat == customers` (R013) · non-negative (R014/R015).

**Cross-row: daily `customers <= orders` (R020) · inventory continuity (R021)** ·
join completeness (R022/R023).

Consistency: units without revenue (R030) · revenue without units (R031) ·
unit-price outliers (R032) · expenses above revenue (R033, **warning**).

Behaviour: nothing is ever repaired, every failure names the offending rows,
structural failures short-circuit value checks, and a bad dataset surfaces as
HTTP 503 with the command to fix it.

## Processing functions

`filter_dataset` · `daily_metrics` · `period_growth` · `summary_metrics` ·
`product_performance` · `category_performance` · `inventory_position` ·
`inventory_movement` · `merchant_directory`.

Every division goes through `safe_divide`, so a zero-order day renders as `0.0`
rather than `inf` or `NaN`.

## API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/merchants` | Merchant list for the selector |
| `GET /api/dataset/summary` | Dataset shape, totals, `synthetic: true` |
| `GET /api/dataset/validation` | Full validation report |

## Tests

100 passing, up from 7. One warning remains and it is upstream
(starlette/anyio), present since Stage 1 and not caused by this work.

| Module | Tests |
| --- | --- |
| `test_validation.py` | 28 |
| `test_metrics.py` | 29 |
| `test_generator.py` | 16 |
| `test_data_loader.py` | 14 |
| `test_api_dataset.py` | 6 |
| `test_data_schema.py` (Stage 1) | 5 |
| `test_health.py` (Stage 1) | 2 |

## Data quality verification

| Check | Result |
| --- | --- |
| Missing values / duplicates / negatives | 0 |
| Invariant violations (all 8) | 0 |
| Date gaps per merchant | 0 |
| `customers > orders` | 0 |
| Inventory continuity violations | 0 |
| Restock events / stock-out rows | 376 / 128 |
| Rows with negative gross profit | 0 |
| Unit price above list price | 0 |
| `inf` / `NaN` anywhere | 0 |
| Margin by merchant | 18.7% kirana, 30.2% electronics, 45.3% fashion, 63.2% café |
| Top product share of revenue | 15.2% (no single product dominates) |

Margins differing by business type, a long-tailed revenue distribution
(median ₹3,335, max ₹117,000) and genuine stock-outs are what separate this
from random CSV noise.

## Bugs found and fixed during the stage

1. **`safe_divide` index-aligned instead of broadcasting.** `pd.Series(scalar)`
   builds a one-element Series, so `Series / scalar` blanked every row but the
   first — `revenue_share` was silently 0.0 almost everywhere. Now covered by a
   named regression test.
2. **Validator assumed numeric dtypes.** A frame built from the generator's
   dicts holds formatted strings, and `revenue <= 0` raised `TypeError`.
   Validation now coerces numerics on a copy once they are known coercible, so
   it works regardless of how the frame was built.
3. **Generator crashed on an out-of-project `--out-dir`** via
   `relative_to(PROJECT_ROOT)`. Now falls back to the absolute path.

## Cleanups made

Three items introduced during this stage were removed or wired in rather than
left as dead weight: `dataset_available()` (duplicated the health endpoint's own
check, no caller) and `Dataset.for_merchant()` (duplicated
`metrics.filter_dataset`) were deleted; `Dataset.is_empty()` was adopted in
`metrics.py` in place of six repetitions of `dataset.sales.empty`.

## Assumptions

1. One product per order, so `orders` is additive and AOV is correct at every level.
2. `expenses` is **cost of goods sold only** — `profit` is gross profit; rent,
   salaries and utilities are not modelled.
3. Customer counts are daily distinct; summing across days gives visits, not
   distinct customers.
4. INR throughout, no tax or shipping.
5. Restocks arrive on a fixed three-day lead time.

## Limitations

- **No customer-level records**, so cohort retention and lifetime value are out
  of reach. Retention is visible only as the daily new/repeat split.
- **R032 is self-referential** — it compares a row against its own product's
  median, so it catches per-row corruption but not uniform corruption.
- **No restock column**; deliveries are inferred from the stock gap.
- **Festival windows are positioned by fraction of the window**, so they move if
  `--days` changes.
- **180 days supports weekly patterns and short-term trends only** — not
  year-over-year. This is why Stage 6 forecasting stays at a days-to-weeks horizon.
- Regeneration is wholesale; there is no incremental append.

## Intentionally NOT implemented

❌ Dashboard UI and charts (Stage 3) — `App.jsx` is still the Stage 1
connectivity card · ❌ `/api/dashboard` · ❌ business analysis and insights
(Stage 4) · ❌ recommendations and action plan (Stage 5) · ❌ forecasting
(Stage 6) — `ml/` is still empty · ❌ LLM integration (Stage 6) — config
placeholders only · ❌ auth, deployment, Docker.

## Exact handoff point for Stage 3

The data layer is done. Stage 3 builds the dashboard UI and the one endpoint
that feeds it.

1. Add `backend/app/routes/dashboard.py` with
   `GET /api/dashboard?merchant_id=&start=&end=`. It should be thin:
   `filter_dataset(...)` → `summary_metrics(...)` + `daily_metrics(...)` →
   response. **Do not add aggregation logic** — every metric it needs already
   exists in `services/metrics.py`.
2. Register the router in `backend/app/main.py`.
3. Build the frontend: merchant selector from `GET /api/merchants`, metric cards
   from `summary_metrics`, and a revenue trend chart from `daily_metrics` using
   Recharts.
4. Handle all three states per [USER_FLOW.md](USER_FLOW.md) — loading, error and
   empty. `summary_metrics` already returns zeros rather than `NaN` for an empty
   selection, so the empty state has real values to render.
5. Add frontend calls to `frontend/src/services/api.js` only; no `fetch` inside
   components.

Useful starting points: **M003** is the declining merchant, **M001** the growing
one — both make the dashboard visibly interesting in a demo.
