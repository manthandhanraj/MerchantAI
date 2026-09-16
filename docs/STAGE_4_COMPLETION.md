# Stage 4 — Completion Report

**Status: complete.** The insights engine turns Stage 2 metrics into
explainable, deterministic business findings, exposed at `/api/insights`.

No LLM was added. Every finding is computed in Python from the existing
dataset, with a documented threshold behind each severity.

Stage 1–3 contracts are unchanged; all 154 pre-existing tests still pass.

## Files created

- `backend/app/services/analysis.py` — the engine: finding types, thresholds,
  eight analysers, and the `analyse()` entry point
- `backend/app/routes/insights.py` — thin endpoint and response models
- `tests/test_analysis.py` (43 tests)
- `tests/test_api_insights.py` (20 tests)

## Files modified

| File | Change |
| --- | --- |
| `backend/app/routes/dependencies.py` | Added `validate_query()` — shared merchant + date-range validation |
| `backend/app/routes/dashboard.py` | Uses `validate_query()` instead of its own copy (behaviour identical; its 22 tests pass unchanged) |
| `backend/app/main.py` | Register the insights router |
| `backend/app/routes/__init__.py`, `services/__init__.py` | Docstrings |
| `README.md`, `docs/ARCHITECTURE.md` | Status |

No frontend file was touched. Stage 4's scope is the engine, the API and tests;
rendering insights is left for Stage 5/7 integration.

## Analysis rules

Eight analysers, each reusing Stage 2 services and computing nothing of its own.

| Analyser | Produces | Source |
| --- | --- | --- |
| Totals | Revenue, orders, customer-visit and gross-profit movement | `summary_metrics()` |
| Rates | Gross margin and repeat-rate movement, in percentage points | `summary_metrics()` |
| Product movers | Largest riser and largest faller by revenue | `product_performance()` |
| Products (standing) | Top performer, weakest performer, concentration risk | `product_performance()` |
| Categories (standing) | Leading category | `category_performance()` |
| Category change | Category that fell hardest | `category_performance()` |
| Inventory | Out-of-stock, critical and low cover | `inventory_position()` |
| Trend | Unusually strong / weak days | `daily_metrics()` |

### Comparison baseline

"Declined" is meaningless without a baseline, so the engine picks one explicitly
and reports which it used:

- **`previous_period`** — the equal-length window immediately before the
  selection. Preferred whenever it holds data.
- **`within_period`** — when the selection reaches the start of the dataset
  (e.g. "All"), the selection is split in half and the later half is compared
  against the earlier. A note in the response says so.
- **None** — under 4 days, no trend findings are produced and a note explains why.

Trend findings describe the window they actually measured. Standing findings
(top product, stock risk, unusual days) always describe the full selection.

## Severity thresholds

All constants live at the top of `analysis.py`. Anything below the floor is not
reported — a 2% move on a noisy daily series is not a business event, and
reporting it buries the real findings.

**Totals** (relative change, period on period):

| Severity | Threshold |
| --- | --- |
| HIGH | ≥ 20% |
| MEDIUM | ≥ 10% |
| LOW | ≥ 5% |

**Rates** (margin, repeat rate — measured in percentage *points*, because a rate
moving 30% → 33% has risen 3 points, and the relative scale would overstate it):

| Severity | Threshold |
| --- | --- |
| HIGH | ≥ 5.0 points |
| MEDIUM | ≥ 3.0 points |
| LOW | ≥ 1.5 points |

**Other rules:**

| Rule | Threshold |
| --- | --- |
| Concentration HIGH / MEDIUM | top product ≥ 50% / ≥ 35% of revenue |
| Weak product | revenue share < 5% |
| Inventory HIGH | out of stock, or cover < 3 days |
| Inventory MEDIUM | cover < 7 days |
| Unusual day | ≥ 2.0 standard deviations from the period mean |
| Minimum days for comparison | 4 |
| Minimum days for outlier detection | 14 |

## Insight categories

Eight, matching the brief: **Revenue, Orders, Customers, Profit, Product,
Category, Inventory, Trend**.

## API contract

`GET /api/insights?merchant_id=&start=&end=`

```json
{
  "merchant_id": "M003",
  "requested_start": "2026-08-17",
  "requested_end": "2026-09-15",
  "has_data": true,
  "period": {"start": "2026-08-17", "end": "2026-09-15", "days": 30},
  "comparison_period": {"start": "2026-07-18", "end": "2026-08-16", "days": 30},
  "comparison_basis": "previous_period",
  "finding_count": 13,
  "severity_counts": {"HIGH": 2, "MEDIUM": 8, "LOW": 3},
  "notes": [],
  "findings": [ ... ]
}
```

Each finding carries the six things a merchant needs:

| Field | Answers |
| --- | --- |
| `title`, `description` | **What** happened |
| `severity`, `change` | **How significant** |
| `scope` | **Where** — "merchant", or the product/category |
| `metric`, `value`, `unit`, `comparison_value` | **Supporting figure** |
| `period` | **When** |
| `reason` | **Why this was flagged** — names the threshold it met |

Plus `id` (stable) and `evidence` (comparison basis, units, raw supporting numbers).

| Case | Response |
| --- | --- |
| Valid merchant | 200 |
| Unknown merchant | 404, listing available ids |
| Missing `merchant_id` | 422 |
| Malformed date | 422 |
| `start` after `end` | 400 |
| Range outside the data | 200, `has_data: false`, no findings, explanatory note |
| Dataset missing/invalid | 503 with the regeneration command |

## Tests

**185 backend tests passing** (up from 122), plus the 32 frontend tests unchanged
— **217 total**.

| Suite | Tests |
| --- | --- |
| `test_analysis.py` | 43 (38 functions; two are parametrised) |
| `test_api_insights.py` | 20 |
| Stage 1–3 backend suites | 122 (unchanged) |

Covering, as required: growing merchant · declining merchant · flat merchant
(asserts *no* trend findings — a business that did not change must not be told
it did) · inventory risk · strong and weak product · strong and weak category ·
empty data · invalid merchant · invalid dates · zero and near-zero values ·
determinism · the API response contract.

Synthetic test datasets are written through `read_dataset`, so they must pass
Stage 2 validation — including inventory continuity — exactly like real data.

## Real-data verification

Confirmed against the committed dataset, both in tests and through a live server.

**M003 (declining café), last 30 days** — 13 findings, 2 HIGH:

```
[HIGH  ] Product   Cold Coffee declined 25.7% versus the previous 30 days
[HIGH  ] Customers Repeat customer rate slipped 7.3 points to 60.1%
[MEDIUM] Category  Beverages revenue fell 18.0% versus the previous 30 days
[MEDIUM] Revenue   Revenue fell 16.1% versus the previous 30 days
[MEDIUM] Profit    Gross profit fell 15.7% versus the previous 30 days
```

That is the engine independently rediscovering the story built into the data in
Stage 2 — the decline, its worst product, and the retention dip.

**M001 (growing)** surfaces `Smart Watch grew 34.7%` and `Revenue rose 19.5%`.
**M002 (flat kirana)** produces no revenue-trend finding but does flag
`Cooking Oil 1L has 0.8 days of stock cover` — the stock-out risk designed into
Stage 2. Tests assert each of these specifically.

## Determinism

No randomness, no `today()`, no current-time dependency anywhere. Findings are
sorted by severity, then magnitude, then id — a total order, so the sequence
never varies. Asserted at both service and API level: two identical requests
return byte-identical findings.

## Bugs found and fixed

1. **Window mismatch in the within-period fallback.** When the selection had no
   prior period, the summary was re-scoped to the later half but
   `product_performance` and `category_performance` were still computed over the
   *full* selection — so a 180-day product total was compared against a 90-day
   one, inventing a "+94.9%" riser. Caught by sanity-checking that number against
   the data (the true figure was −5.1%). The engine now keeps `current_window`
   and `baseline_window` explicit and passes matching windows to every trend
   analyser. A regression test locks it.
2. A test-harness UnicodeEncodeError on `₹` under Windows `cp1252` — an
   inspection-script issue, not a product one. API responses are UTF-8 JSON.

## Limitations

- **Findings explain *what* changed, not *why* it changed.** The engine can say
  Cold Coffee fell 25.7% and that Beverages fell with it; it cannot attribute
  cause, because the dataset holds no pricing experiments, marketing spend,
  weather or competitor data.
- **Inventory is inferred**, not a live feed — Stage 2 derives stock from sales
  history. Every inventory finding states this, and carries `inferred: true`.
- **No customer-level records**, so retention is visible only as the daily
  new/repeat split. Cohort analysis and churn are out of reach.
- **The unusual-day rule uses the period's own mean**, so it detects days unusual
  *within the selection*, not against the merchant's whole history.
- **Weekday effects are not separated.** A window containing more weekends will
  read as stronger, which matters most for the weekend-heavy merchants.
- **Concentration is measured on revenue share only** — a product can be a small
  revenue share yet strategically important, and the engine cannot know that.

## Stage 1–3 regression status

| Check | Result |
| --- | --- |
| Full backend suite | 185 passed |
| Frontend suite | 32 passed |
| `npm run build` | Succeeds |
| Backend startup | Clean; 7 routes registered |
| `/api/health`, `/api/merchants`, `/api/dataset/*`, `/api/dashboard` | All 200 |
| Stage 3 dashboard in browser | Renders with real data; no console errors |
| `/api/insights` through the Vite proxy | 200 from the browser |
| Dashboard and insights agree on the period | Asserted by test |

`routes/dashboard.py` was refactored onto the shared validator with no change in
behaviour — its 22 tests pass unmodified.

## Intentionally NOT implemented

❌ LLM or chatbot · ❌ recommendations and action plan (Stage 5) · ❌ forecasting
or prediction (Stage 6) · ❌ assistant (Stage 6) · ❌ auth, payments, database,
Docker, deployment · ❌ frontend insights UI (Stage 5/7 integration).

The engine only *describes* what happened. It never suggests what to do — that
line is where Stage 5 begins.

## Stage 5 handoff

Recommendations turn findings into actions. The findings are already the right
input: each carries a category, a severity, a scope and the supporting numbers.

1. Add `backend/app/services/recommendations.py`. Call
   `analysis.analyse(dataset, merchant_id, start, end)` and map findings to
   suggestions — **do not re-derive the analysis**. A `HIGH` inventory finding
   scoped to a product becomes a restock action; a negative repeat-rate finding
   becomes a retention action; a `product-faller` becomes a product action.
2. Add `backend/app/services/action_plan.py` to rank suggestions into
   High / Medium / Low. Finding severity is the natural starting rank.
3. Add `backend/app/routes/recommendations.py` and `action_plan.py`, both using
   `LoadedDataset` + `validate_query` and the same 404/400/503 shapes.
4. Register both in `main.py`.
5. Frontend (Stage 5 or 7): add `getInsights` / `getRecommendations` to
   `frontend/src/services/api.js` and render them under the charts in
   `DashboardPage.jsx`, reusing `StatusPanel` for loading/empty/error.

Useful anchors already proven on real data: M003 has a retention dip and a
failing product; M002 has a near stock-out; M001 has a star product and two
products with under 3 days of cover.
