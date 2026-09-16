# Data Pipeline (Stage 2)

How the dataset is generated, validated, loaded and turned into metrics.
Column definitions live in [DATA_SCHEMA.md](DATA_SCHEMA.md); this document
covers the machinery around them.

```
data/generate_dataset.py  ->  data/raw/*.csv
                                   |
                       services/data_loader.py   read (raw types)
                                   |
                       services/validation.py    validate  -> report
                                   |
                       services/data_loader.py   normalise + cache
                                   |
                       services/metrics.py       aggregates
                                   |
                       routes/dataset.py         API
```

## Why the data is synthetic

MerchantAI uses generated demo data only. It does not use, and does not claim
access to, real Paytm merchant, customer or payment data. Every figure in the
product comes from `data/generate_dataset.py` and the hand-written business
profiles inside it. The `/api/dataset/summary` response carries a
`"synthetic": true` field so this stays visible from the API itself.

## Generation

```bash
python data/generate_dataset.py
```

| Flag | Default | Purpose |
| --- | --- | --- |
| `--seed` | `42` | RNG seed |
| `--days` | `180` | days of history |
| `--end-date` | `2026-09-15` | last day of the window |
| `--out-dir` | `data/raw` | output directory |
| `--summary` | off | print a data-quality summary |

### Determinism

Same seed, same output — byte for byte. Two details make that true:

- A single `numpy.random.default_rng(seed)` is drawn from in a fixed order.
- **The end date is a constant, not `today()`.** A moving window would silently
  produce a different dataset every day, which is not reproducible.

`tests/test_generator.py` asserts both, including byte-identical CSVs across
two separate CLI runs.

### What is modelled

Patterns are hand-specified per merchant so every signal in the data is
explainable rather than incidental:

| Merchant | Business | Story |
| --- | --- | --- |
| M001 Sharma Electronics | Electronics & accessories | Growing ~30%; Smart Watch is a rising star, Power Bank is declining |
| M002 Gupta Kirana Store | Grocery/household | Flat, high volume, very high repeat rate; Cooking Oil runs close to stock-out |
| M003 Chai Point Cafe | Food & beverage | **Declining ~33% with a retention dip** — the "why did my sales drop?" case |
| M004 Trendy Threads | Fashion | Volatile, festival-driven, low repeat rate |

Layered on top: weekday/weekend rhythm, a salary-week lift on days 1–5, two
festival windows, per-product lifecycle drift, promotional discounts, gamma
jitter on demand, and inventory that depletes, stocks out and restocks on a
three-day lead time.

Demand is Poisson around a jittered rate, so the series rises and falls rather
than tracing a clean line. `tests/test_generator.py` guards against the data
degenerating into a smooth synthetic ramp.

### Generation rules that keep the arithmetic honest

- **One product per order**, so `orders` is additive across products and
  `AOV = revenue / orders` is correct at every level.
- A stock-out caps `units_sold`, and `orders` is capped with it — otherwise
  `orders <= units_sold` would break.
- Discounts are capped at half the gross margin, so nothing ever sells below cost.
- Zero-sales days produce **no row**, per the "absent rows, not blank cells"
  convention.

## Validation

```bash
python -c "from backend.app.services.data_loader import get_dataset; print(get_dataset().validation.summary())"
```

Or over HTTP: `GET /api/dataset/validation`.

Two rules the Stage 1 audit identified as unenforceable at row level are the
reason this layer exists — Pydantic validates one row at a time and cannot see
across rows.

| Rule | Severity | Check |
| --- | --- | --- |
| R001/R002 | error | required columns present |
| R003/R004 | error | no missing values |
| R005/R006 | error | dates parse as `YYYY-MM-DD` |
| R007/R008 | error | numeric columns contain numbers |
| R009/R010 | error | no duplicate key tuples |
| R011 | error | `orders <= units_sold` |
| R012 | error | `units_sold > 0` implies `orders > 0` |
| R013 | error | `new + repeat == customers` |
| R014/R015 | error | no negative values |
| **R020** | error | **daily `customers <= orders`** — audit gap A |
| **R021** | error | **inventory continuity** — audit gap B |
| R022/R023 | error | the two files cover exactly the same `(date, merchant_id)` days |
| R030 | error | units sold with zero revenue |
| R031 | error | revenue with no units sold |
| R032 | error | realised unit price within 50–110% of that product's median |
| R033 | **warning** | expenses exceed revenue |

### Two rules worth explaining

**R021, inventory continuity.** The schema permits restocks, so strict equality
would flag every delivery. The checkable rule is:

```
inventory[t] >= inventory[t-1] - units_sold[t]
```

Equality on ordinary days; a restock may raise closing stock. A *shortfall*
means stock disappeared without being sold, which is corruption. Restocks are
counted into `stats.restock_events` so they stay visible rather than being
quietly absorbed by a loose rule. Continuity is checked between a product's
**consecutive rows**, since zero-sales days have no row.

**R033 warns rather than blocks.** A merchant really can sell below cost. The
generator never does, so this firing means something is worth a look — but it
is not grounds for refusing to start.

### Behaviour

- **Nothing is ever repaired.** Validation reports; it does not mutate. A silent
  fix would let corrupt data reach the dashboard looking clean.
- **Every failure names the rows** — rule id, message, count and concrete
  examples, so a failure is actionable.
- Structural failures short-circuit the value checks, so a missing column
  reports once instead of cascading.
- A missing or invalid dataset surfaces as HTTP **503** with the exact command
  to fix it, not a stack trace.

## Loading

`services/data_loader.py` is the only module that opens a CSV. Everything else
goes through `get_dataset()`.

```
read (types left raw) -> validate -> normalise types -> cache
```

Validating *before* normalising is deliberate: coercing on read would turn a
corrupted `"abc"` into `NaN` and the validator would never see it.

The dataset is small and read-only, so it is loaded once per process and cached
in memory. That is the whole reason no database is needed.

```python
from backend.app.services.data_loader import get_dataset
dataset = get_dataset()           # cached
dataset.merchant_ids              # ['M001', ...]
dataset.date_range                # (date, date)
dataset.for_merchant("M003")      # narrowed Dataset
```

## Metrics

`services/metrics.py` holds every aggregate. Stages 3–6 call these rather than
recomputing, which is what keeps a number on the dashboard identical to the
same number quoted by the assistant.

| Function | Returns |
| --- | --- |
| `filter_dataset(ds, merchant_id, start, end)` | narrowed `Dataset` |
| `daily_metrics(ds)` | one row per date: revenue, orders, units, expenses, profit, margin, AOV, customers, repeat/new rate, revenue per customer |
| `summary_metrics(ds)` | headline totals as a JSON-safe dict |
| `period_growth(daily, column)` | recent window vs the one before it |
| `product_performance(ds)` | per-product totals, margin, AOV, `avg_unit_price`, revenue share |
| `category_performance(ds)` | per-category totals, margin, revenue share |
| `inventory_position(ds)` | latest stock, velocity, days of cover, status |
| `inventory_movement(ds)` | stock over time with restocks made explicit |
| `merchant_directory(ds)` | merchant list for the selector |

Every division goes through `utils/calculations.safe_divide`. A quiet day with
zero orders is real data, and it must render as `0.0`, never `inf` or `NaN`.

**Pricing is derived, not stored.** `avg_unit_price = revenue / units_sold` is
exact and reflects the *realised* price after discount, so the locked schema
needs no price column.

`stock_status` thresholds: `out_of_stock` (zero), `critical` (<3 days cover),
`low` (<7 days), `no_recent_sales` (no sales in the velocity window — different
from healthy, and labelled as such), otherwise `healthy`.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/merchants` | merchant list for the selector |
| `GET /api/dataset/summary` | dataset shape + portfolio totals + `synthetic: true` |
| `GET /api/dataset/validation` | full validation report |

Routes stay thin — load the dataset, call one service, return. No aggregation
in a route handler.

## Assumptions

1. **One product per order.** Makes `orders` additive; the reason AOV is
   trustworthy at every level.
2. **`expenses` is cost of goods sold only.** Rent, salaries and utilities are
   not modelled, so `profit` is **gross profit**. Naming it "profit" is the
   schema's choice; treat it as gross.
3. **Customer counts are daily distinct.** Summing across days gives
   customer-*visits*, not distinct customers.
4. **Currency is INR throughout**, with no tax or shipping modelled.
5. **Restocks arrive on a fixed three-day lead time** and in a fixed quantity
   per product.

## Limitations

- **No customer-level records.** There is no per-customer table, so cohort
  retention, lifetime value and true multi-day unique counts are out of reach.
  Retention is visible only as the daily new/repeat split.
- **R032 is self-referential.** It compares each row against its own product's
  median price, so it catches per-row corruption but not a uniform corruption
  of every row for a product.
- **Inventory has no restock column.** Deliveries are inferred from the gap
  between observed and implied stock, so a restock and a same-day correction
  are indistinguishable.
- **Festival windows are positioned by fraction of the window**, not by real
  calendar dates, so they move if `--days` changes.
- **180 days is short for seasonality.** It supports weekly patterns and
  short-term trends; it cannot support year-over-year comparison, which is why
  Stage 6 forecasting is scoped to a days-to-weeks horizon.
- Stage 2 regenerates the dataset wholesale. There is no incremental append.
