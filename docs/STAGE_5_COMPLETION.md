# Stage 5 — Completion Report

**Status: complete and verified.** Findings from Stage 4 are mapped to
actionable, traceable recommendations and a short prioritised action plan,
exposed at `/api/recommendations` and `/api/action-plan`, and rendered on the
dashboard.

Stage 5 re-derives no analysis. It consumes `analyse()` and nothing else.

## 1. Files created

**Services**
- `backend/app/services/recommendations.py` — finding→action mapping,
  traceability, priority assignment
- `backend/app/services/action_plan.py` — bucketing, capping, ranking

**Routes**
- `backend/app/routes/recommendations.py`
- `backend/app/routes/action_plan.py`

**Frontend**
- `frontend/src/components/ActionPlanPanel.jsx`

**Tests**
- `tests/test_recommendations.py` (42)
- `tests/test_api_recommendations.py` (33)

## 2. Files modified

| File | Change |
| --- | --- |
| `backend/app/main.py` | Register the two new routers |
| `backend/app/routes/__init__.py`, `services/__init__.py` | Docstrings |
| `frontend/src/services/api.js` | Added `getActionPlan` |
| `frontend/src/pages/DashboardPage.jsx` | **Additive only**: one new effect and one new section |
| `frontend/src/pages/DashboardPage.test.jsx` | Mock the new call; 8 new tests; 2 assertions tightened |
| `README.md`, `docs/ARCHITECTURE.md` | Status |

No Stage 1–4 service, schema, metric or analysis rule was changed.

## 3. Recommendation engine architecture

```
analyse()  ->  findings  ->  recommendations.py  ->  action_plan.py  ->  API/UI
                               (map + trace)          (bucket + cap)
```

`recommendations_from_report()` takes an existing `AnalysisReport` so callers
that already ran the analysis — the action plan, and Stage 6's assistant — do
not pay for it twice. `recommend()` is the convenience wrapper that analyses
first.

**Classification.** Findings are matched by their stable id prefix
(`finding_kind()`), against 24 known kinds, longest-prefix-first so
`inventory-critical` is never shadowed. This treats the Stage 4 finding id as
the contract it was documented to be, rather than reaching into Stage 4 to add
a field.

**Traceability.** Every recommendation carries `source_finding` (the finding id)
and its `id` is `rec-{finding_id}`. The `reason` field is the finding's own
title plus the threshold it met, verbatim — nothing is added. `value`, `change`,
`unit`, `scope`, `category` and `evidence` are copied straight through, so
inventory keeps its `inferred: true` marker.

**Nothing is dropped silently.** A finding that yields no sensible action goes
to `unactioned` with a stated reason. Four kinds are deliberately
informational — `product-top`, `category-top`, `trend-peak-day`,
`trend-trough-day` — because a single unusual day is context, not an
instruction. An unrecognised kind is also reported rather than guessed at. A
test asserts that every finding is either actioned or explained.

## 4. Action mapping logic

20 templates, each business-specific and scope-aware:

| Finding | Action |
| --- | --- |
| `total-revenue-down` | Work through the product/category items, pick one recovery action, measure it |
| `total-revenue-up` | Identify what drove it; keep those lines stocked and visible |
| `total-orders-down` | Check whether fewer customers, or the same customers buying less often |
| `total-customers-down` | Re-engage recent buyers; review visibility to new ones |
| `total-profit-down` | Determine whether it came from volume or from margin |
| `profit-margin-down` | Review purchase cost and discounting on the highest-volume lines |
| `repeat-rate-down` | Run a re-engagement offer for recent buyers |
| `product-riser` | Keep in stock, improve visibility, widen variants |
| `product-faller` | Review price, placement, promotion; reposition or reallocate |
| `product-weak` | Give it a deliberate push or free the stock budget |
| `product-concentration` | Build up the next strongest products |
| `category-decline` | Review pricing and range for the category as a whole |
| `inventory-out_of_stock` | Restock now, ahead of everything else |
| `inventory-critical` | Reorder now, allowing for delivery time |
| `inventory-low` | Schedule a reorder in the next few days |

Plus the positive counterparts (`-up` variants) for revenue, orders, customers,
profit, margin and repeat rate.

**No invented causation.** The analysis establishes *what* changed, never *why* —
the dataset holds no pricing experiments, marketing spend or competitor data.
Actions therefore say "review", "check" and "investigate". A test scans every
recommendation across every merchant for causal phrases (`because`, `due to`,
`caused by`, `led to`, `resulted in`, …) and fails if one appears.

Inventory wording also avoids implying a live feed: a test asserts "warehouse",
"live stock" and "real-time" never appear.

## 5. Priority and ranking

**Priority is the finding's severity**, mapped directly:
`HIGH → High`, `MEDIUM → Medium`, `LOW → Low`. No second scoring scheme was
introduced — the severity thresholds are already documented in `analysis.py`,
and inventing a separate score would only add an unexplainable number.

**Ordering** is a total order, so the same input always yields the same sequence:

1. Priority (High → Medium → Low)
2. Magnitude of change, descending, by absolute value (a 40% fall and a 40% rise
   rank equally)
3. Recommendation id, as a stable tie-breaker

Recommendations with no `change` (inventory findings carry none) sort as 0.0 and
do not break the comparison.

**The plan is capped** at 3 High / 3 Medium / 2 Low. A merchant handed twenty
suggestions has no plan at all. Nothing is hidden silently: `total_available`,
`included` and `truncated` are always reported, plus a note pointing at
`/api/recommendations` for the full list. Ranks are contiguous across buckets.

## 6. API endpoints

`GET /api/recommendations?merchant_id=&start=&end=` — every recommendation with
its source finding, plus the `unactioned` list.

`GET /api/action-plan?merchant_id=&start=&end=` — the capped High/Medium/Low
buckets.

Both use the existing `LoadedDataset` dependency and `validate_query()`, so
error behaviour is identical to Stage 3 and 4:

| Case | Response |
| --- | --- |
| Valid merchant | 200 |
| Unknown merchant | 404, listing available ids |
| Missing `merchant_id` | 422 |
| Malformed date | 422 |
| `start` after `end` | 400 |
| Range with no data | 200, `has_data: false`, empty lists |
| Dataset missing/invalid | 503 with the regeneration command |

## 7. Frontend changes

The locked `docs/USER_FLOW.md` places "Action plan — High / Medium / Low action
cards" at **Stage 5**, so this was required by the existing contract rather than
optional.

Added `ActionPlanPanel.jsx` and one section below the charts. Each card shows the
priority badge, category, scope, rank, title, the action, and a "Why:" line
carrying the finding that justifies it.

The change to `DashboardPage.jsx` is strictly additive — one new `useEffect` and
one new block. The action plan is fetched in **its own request**, so if the plan
fails the KPIs and charts above it still render; a test asserts exactly that.
No KPI card, chart, merchant selector or date control was modified, and all 32
pre-existing frontend tests still pass.

## 8. Tests before Stage 5

**185 backend + 32 frontend = 217.**

## 9. Tests after Stage 5

**260 backend + 40 frontend = 300.**

| Suite | Tests |
| --- | --- |
| `test_recommendations.py` | 42 |
| `test_api_recommendations.py` | 33 |
| `DashboardPage.test.jsx` (action plan block) | 8 |
| Stage 1–4 backend | 185 (unchanged) |
| Stage 3 frontend | 32 (unchanged) |

Every lettered requirement A–P is covered: each severity produces a
recommendation (A/B/C); informational findings are explicitly unactioned (D);
traceability (E); determinism of generation and ordering (F/G); High before
Medium before Low (H); same-severity secondary ordering (I); `inferred=true`
preserved (J); no causal claims (K); API contract (L); unknown merchant (M);
invalid dates (N); empty periods (O); and the full Stage 1–4 suite (P).

## 10. Full test result

```
backend   260 passed, 1 warning in 39.42s
frontend   40 passed (2 files)
```

The single warning is the pre-existing upstream starlette/anyio deprecation,
present since Stage 1 and not caused by this work.

## 11. Build result

`npm run build` succeeds. The bundle-size advisory for Recharts is unchanged
from Stage 3.

## 12. Bugs found and fixed

1. **Frontend test mock did not know the new call.** Adding `getActionPlan` to
   `DashboardPage` broke 14 Stage 3 tests, because the module mock returned
   `undefined` for it. Fixed by adding it to the mock with a default resolved
   value. Caused by new code, caught by the existing suite — which is the suite
   doing its job.
2. **Two Stage 3 assertions became ambiguous.** The new section introduced a
   second "Revenue" (an action's category chip) and a second "30 days" (inside an
   action's reason), so `getByText` matched multiple elements. The *tests* were
   too loose, not the product: they now assert on the KPI value and on the
   "Showing …" paragraph specifically.
3. **Test-harness path bug** — a test passed `tmp_path / "a"` without creating
   the directory. Fixed in the test.

No defect was found in the recommendation or action-plan logic itself.

## 13. Regression verification

| Check | Result |
| --- | --- |
| Backend suite | 260 passed |
| Frontend suite | 40 passed |
| `npm run build` | Succeeds |
| Backend startup | Clean; 9 routes |
| Stage 1–4 endpoints (`/api/health`, `/merchants`, `/dataset/*`, `/dashboard`, `/insights`) | All 200 |
| Stage 3 dashboard in browser | 5 KPI values, 3 charts, 4 selector options, 2 date inputs, 4 presets — all intact |
| Browser console | No errors |
| Action plan in browser | 8 cards, ranks 1–8 contiguous, High×3/Medium×3/Low×2, every card has an action and a "Why" |
| UI vs API | Rendered action titles match the API response exactly, in order; revenue matches to the rupee |
| Merchant switch | Plan and KPIs update together and stay consistent |
| Unused imports / dead code | None |
| Secrets, build artifacts staged | None |

`test_recommendations_trace_back_to_real_findings` additionally asserts that
every `source_finding` returned by `/api/recommendations` exists in the
`/api/insights` response for the same query — the two endpoints cannot disagree.

## 14. Limitations

- **Advice is generic to the situation, not to the merchant's context.** The
  engine knows revenue fell and which product fell with it; it does not know the
  merchant's supplier lead times, local competition, staffing or cash position,
  so it cannot say which recovery action is cheapest or most feasible.
- **No causal attribution**, by design — see §4. A merchant asking "why did this
  happen?" gets "here is what to investigate", not an answer.
- **No effect estimates.** Recommendations carry no predicted uplift, because
  nothing in the dataset supports one. Ranking is by size of the observed change,
  not by expected return.
- **Inventory advice inherits Stage 2's inference.** Cover is derived from sales
  history, not a live feed, and restock quantities are not suggested — only that
  a reorder is due.
- **One action per finding.** A single finding cannot produce several
  alternatives, and two related findings are not merged into one combined action.
- **The cap is fixed** at 3/3/2 rather than adapting to how much is actually
  wrong.
- **Positive findings compete with problems** on the same severity scale, so
  "Reinvest the profit gain" can outrank a genuine issue with a smaller change.

## 15. Stage 6 handoff

Stage 6 adds forecasting and the AI assistant.

**Forecasting** — add `backend/app/services/forecasting.py` and `ml/`:

1. Build on `daily_metrics()`; do not re-aggregate. The series already carries
   revenue, orders, units and customers per day.
2. Start with a moving-average or linear-trend baseline. `requirements.txt` keeps
   scikit-learn commented out precisely so it is only enabled if that baseline
   proves insufficient.
3. Respect the Stage 2 limitation: 180 days supports a days-to-weeks horizon and
   weekly seasonality, not year-over-year. Say so in the response.
4. Handle short series explicitly — refuse to project from two points, the same
   way `analyse()` refuses a comparison under 4 days.
5. Add `routes/forecast.py` using `LoadedDataset` + `validate_query`.

**Assistant** — add `backend/app/services/assistant.py`:

1. Build the context from the services that already exist:
   `summary_metrics()`, `daily_metrics()`, `analyse()`, `recommend()`,
   `build_action_plan()`, and the new forecast. This is the whole reason the
   layering exists.
2. **The LLM explains; it never calculates.** Every number in an answer must come
   from that context object, and the prompt must instruct the model to say when
   the data does not support an answer.
3. Configuration is already in place: `LLM_ENABLED`, `LLM_PROVIDER`, `LLM_MODEL`,
   `LLM_API_KEY` in `config.py` and `.env.example`. With `LLM_ENABLED=false`
   everything else must keep working — the app has to stay demoable without a key.
4. Add the `anthropic` client to `requirements.txt` (currently commented) and
   `routes/assistant.py` with `POST /api/assistant/ask`.
5. Frontend: the assistant question box and the forecast are both Stage 6 rows in
   `docs/USER_FLOW.md`.

Useful anchors already proven on real data: M003 has a revenue decline, a
retention dip and a failing product; M002 has a near stock-out; M001 has a star
product and two products under three days of cover; M004 is festival-driven.
