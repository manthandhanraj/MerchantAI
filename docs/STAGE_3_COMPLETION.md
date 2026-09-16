# Stage 3 — Completion Report

**Status: complete.** The merchant dashboard is built, wired to real Stage 2
data, and verified in a browser.

Stage 1 and Stage 2 contracts are unchanged. No schema was touched, no metric
was redefined, and no aggregation logic was duplicated.

## What was built

```
React dashboard  ->  GET /api/dashboard  ->  filter_dataset -> summary_metrics
                                                            -> daily_metrics
```

The endpoint is an orchestrator, not a second analytics engine. Every number on
the screen is computed by `services/metrics.py` — the same functions Stage 4–6
will use, so the dashboard and the future assistant cannot disagree.

## Files created

**Backend**
- `backend/app/routes/dashboard.py` — the endpoint, its response models, and the
  daily-series serialisation
- `backend/app/routes/dependencies.py` — shared `LoadedDataset` dependency

**Frontend**
- `frontend/src/pages/DashboardPage.jsx` — data fetching and page layout
- `frontend/src/components/KpiCard.jsx` — metric card + skeleton
- `frontend/src/components/TrendChart.jsx` — reusable Recharts panel
- `frontend/src/components/MerchantSelector.jsx`
- `frontend/src/components/DateRangeControls.jsx`
- `frontend/src/components/StatusPanel.jsx` — loading / empty / error
- `frontend/src/utils/format.js` — currency, number, percent, date formatting
- `frontend/vitest.setup.js`

**Tests**
- `tests/test_api_dashboard.py` (22)
- `frontend/src/pages/DashboardPage.test.jsx` (18)
- `frontend/src/utils/format.test.js` (14)

## Files modified

| File | Change |
| --- | --- |
| `backend/app/main.py` | Register the dashboard router; add a JSON handler for unhandled errors |
| `backend/app/routes/dataset.py` | Use the shared dependency instead of its own `_load()` |
| `backend/app/routes/__init__.py` | Docstring |
| `frontend/src/App.jsx` | Renders `DashboardPage` instead of the Stage 1 placeholder |
| `frontend/src/services/api.js` | `getMerchants`, `getDashboard`, abort support, FastAPI error-detail extraction |
| `frontend/src/index.css` | `tabular-nums` helper |
| `frontend/package.json`, `vite.config.js` | Vitest setup and `npm test` |
| `README.md`, `docs/ARCHITECTURE.md`, `docs/SETUP.md` | Status and instructions |

Deleted: the `.gitkeep` placeholders in `frontend/src/components/` and
`frontend/src/pages/`, now that both hold real files.

## Backend endpoint

`GET /api/dashboard?merchant_id=&start=&end=`

```json
{
  "merchant_id": "M001",
  "requested_start": null,
  "requested_end": null,
  "has_data": true,
  "summary": { "total_revenue": 17518564.5, "...": "18 fields from summary_metrics()" },
  "daily":   [ { "date": "2026-03-20", "revenue": 114400.0, "...": "12 fields" } ]
}
```

| Case | Response |
| --- | --- |
| Valid merchant | 200 |
| Unknown merchant | 404, listing the available ids |
| Missing `merchant_id` | 422 |
| Malformed date | 422 |
| `start` after `end` | 400 with both values named |
| Range outside the data | **200** with `has_data: false` and a zeroed summary |
| Dataset missing/invalid | 503 with the regeneration command |
| Unhandled error | 500 as JSON; the traceback goes to the log, never the browser |

A range that matches nothing is a valid question with an empty answer, so it
returns 200 and the UI shows an empty state rather than an error state.

## Existing services reused

`filter_dataset` · `summary_metrics` · `daily_metrics` · `merchant_directory`
(via `/api/merchants`) · `round_money` / `round_rate` from `utils/calculations`.

Nothing was reimplemented. The only new backend computation is converting the
daily frame into JSON rows, and a test asserts the daily series sums back to the
summary totals so the two can never drift.

## Dashboard features

- **Merchant selector** populated entirely from `GET /api/merchants`; no ids are
  hardcoded in the frontend.
- **Date range**: 7D / 30D / 90D / All presets plus explicit From/To inputs,
  bounded by the selected merchant's own `first_date` / `last_date`. Editing a
  date switches to a custom range. Changing merchant re-derives the range from
  the new merchant's bounds.
- **Five KPI cards**: Revenue (with change badge), Orders, Customer Visits,
  Gross Profit, Avg Order Value — each with a supporting figure.
- **Three trend charts**: revenue + gross profit (area/line), orders (line),
  and new vs repeat customers (stacked area), all from the daily series.
- **States**: skeleton loading, informative empty state with a "Show all data"
  action, and an error state carrying the API's real message plus a working
  retry.

### Two labelling decisions

**"Customer Visits", not "Customers".** `DATA_SCHEMA.md` states that summing
daily customers over a window gives visits, not distinct people, and instructs
the UI to label it accordingly. The card uses the Stage 2 metric unchanged and
names it honestly; a footnote under the KPI grid explains it.

**"Gross Profit", not "Profit".** Stage 2 models `expenses` as cost of goods
sold only, so overheads are excluded. The footnote says so.

The revenue change badge is hidden when the period is under 14 days: below that,
`period_growth` shrinks its comparison window and the label "vs previous 7 days"
would be wrong.

## Tests

**154 passing** — 122 backend (pytest), 32 frontend (Vitest).

| Suite | Tests |
| --- | --- |
| `test_api_dashboard.py` | 22 |
| `DashboardPage.test.jsx` | 18 |
| `format.test.js` | 14 |
| Stage 1 + 2 backend suites | 100 (unchanged, all still pass) |

Backend coverage: success and structure, summary/daily reconciliation, merchant
filtering, start-only/end-only/both date filtering, unknown merchant, missing
parameter, malformed date, inverted range, empty range, no NaN/Infinity, no
traceback leakage, 503 on a missing dataset, and that M001 still reads as
growing and M003 as declining through the endpoint.

Frontend coverage: loading state, selector populated from the API, KPI values
rendered from the response, rates shown as percentages, change badge hidden on
short periods, no `NaN`/`undefined` in the DOM, default range derived from
merchant bounds rather than `today()`, refetch on merchant change, refetch on
preset change, refetch on direct date edit, empty state, both error states, and
recovery via retry.

One frontend dependency group was added — `vitest`, `@testing-library/react`,
`@testing-library/user-event`, `@testing-library/jest-dom`, `jsdom` — all dev-only.
Vitest reuses the existing Vite config, so this adds a test runner and no
runtime weight.

## Verification performed

| Check | Result |
| --- | --- |
| Backend suite | 122 passed |
| Frontend suite | 32 passed |
| `npm run build` | Succeeds; test code not bundled |
| Backend startup | Clean; routes: `/`, `/api/health`, `/api/merchants`, `/api/dataset/summary`, `/api/dataset/validation`, `/api/dashboard` |
| API smoke tests | 200 / 404 / 400 / 200-empty all as specified |
| Browser — desktop 1280 & 1440 | KPIs and all three charts render, no overlap or clipping |
| Browser — mobile 375 | Controls and cards stack; no horizontal overflow; charts legible |
| Browser console | No errors |
| Merchant switch M001 → M003 | KPIs and charts update; values match the API exactly |
| Date preset 30D → All | Range, KPIs and charts all update |
| Error state | Backend stopped → error panel; **"Try again" recovered the full dashboard** |
| Doc links | All resolve |
| Secrets / junk staged | None |

### M001 vs M003 in the UI

Both were checked on screen against the API.

- **M001 (growing)** — 30D: ₹34,64,429 revenue, 2,362 orders, 30.1% margin,
  ₹1,467 AOV. Revenue trend rises across the window.
- **M003 (declining)** — All (180 days): ₹13,35,231 revenue, 16,425 orders,
  63.2% margin, ₹81 AOV. Revenue visibly declines from March to September, with
  the café's strong weekend oscillation and the retention dip showing in the new
  vs repeat chart.

The dataset was not modified to flatter the UI.

## Bugs found and fixed

1. **React `key` spread into JSX** in `TrendChart` — the series props object
   carried `key`, which React rejects, producing four console errors per render.
   Keys are now passed explicitly. Console is clean.
2. **`relative_to` crash and `safe_divide` broadcasting** were Stage 2 bugs
   already fixed in that stage; nothing new surfaced in Stage 2 code here.

One non-bug worth recording: after changing the emulated viewport, Recharts'
`ResponsiveContainer` kept a stale width until reload. It does not reproduce on
a normal page load or on a real window resize.

## Limitations

- **Merchants are identified by id, not name.** The generator knows the trading
  names, but they are not in the dataset and the API is the source of truth.
  Hardcoding a mapping in either layer was rejected; a `merchants.csv` would be
  a schema change, which Stage 1/2 lock.
- **The empty state is not reachable through the UI.** The date inputs are
  clamped to the merchant's own bounds, so a user cannot select an empty range.
  It is still implemented and tested, since the API can return it.
- **JS bundle is 575 KB (171 KB gzipped)**, dominated by Recharts. Acceptable
  for the MVP; code-splitting is a Stage 8 optimisation if it matters.
- **Customer counts across multi-day ranges are visits, not distinct people** —
  a Stage 2 data limitation, surfaced honestly in the label rather than hidden.
- The dashboard is read-only; there is no export.

## Stage 1 and Stage 2 contracts

Intact. `DATA_SCHEMA.md`, the CSVs, the generator, the validation rules and
every function in `services/metrics.py` are unchanged. All 100 pre-existing
backend tests still pass. The only Stage 2 file touched was
`routes/dataset.py`, refactored onto the shared dependency with no change to its
responses — its 6 tests pass unmodified.

## Intentionally NOT implemented

❌ Business analysis / insights (Stage 4) · ❌ recommendations and action plan
(Stage 5) · ❌ forecasting (Stage 6) — `ml/` is still empty · ❌ LLM or assistant
(Stage 6) — config placeholders only, no client · ❌ auth, payments, database,
Docker, deployment, write-back.

## Stage 4 starting point

The dashboard answers "what is happening". Stage 4 answers "why".

1. Add `backend/app/services/analysis.py`. It consumes `daily_metrics`,
   `product_performance`, `category_performance` and `inventory_position` —
   all of which already exist and are tested — and returns findings, not raw
   numbers. Do not re-aggregate.
2. Add `backend/app/routes/insights.py` with
   `GET /api/insights?merchant_id=&start=&end=`, using the same `LoadedDataset`
   dependency and the same 404/400 validation shape as `dashboard.py`.
3. Register it in `main.py`.
4. Frontend: add `getInsights` to `services/api.js` and render the findings as a
   section below the charts in `DashboardPage.jsx`, reusing `StatusPanel` for
   loading/empty/error.

Useful signals already present in the data for Stage 4 to find: M003's ~33%
decline with a retention dip (72% → 60%), M001's Smart Watch growing +101% while
Power Bank falls 18%, M002's near stock-out on Cooking Oil, and M004's
festival-driven spikes at roughly 3× its median day.
