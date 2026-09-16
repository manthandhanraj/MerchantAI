# Stage 8 — Completion Report

Testing, debugging, optimisation and cleanup. No features added, no redesign, no
dataset change. Every behavioural change below is a fixed defect with evidence.

## 1. Baseline (before any change)

| | |
| --- | --- |
| Backend | **467 passed**, 1 warning, 31.28s |
| Frontend | **62 passed**, 5.46s |
| Total | **529** |
| Build | 1.58s — JS 592.21 kB (174.81 kB gzip), CSS 18.88 kB (4.62 kB gzip) |
| Failures | none |
| Console errors | none |

## 2. Final results

| | Baseline | Final |
| --- | --- | --- |
| Backend | 467 | **507** |
| Frontend | 62 | **73** |
| **Total** | **529** | **580** |
| Unused imports (project-wide) | 3 | **0** |

```
backend   507 passed, 1 warning in 31.80s
frontend   73 passed (3 files)
```

## 3. Build results

| | Baseline | Final |
| --- | --- | --- |
| Total JS | 592,205 B | 592,180 B |
| Chunks | 1 | 2 (`charts` 557,652 B + app 35,328 B) |
| Gzip on a code-only redeploy | 174.81 kB | **9.35 kB** |
| Build time | 1.58s | 1.53s |

Total size is unchanged — the win is caching, not compression (see §10).

## 4. Edge cases tested

All 26 from the brief. Covered by the new `tests/test_edge_cases.py` (34 tests)
plus existing suites:

| | Case | Result |
| --- | --- | --- |
| A–C | 1, 2, 3-day ranges | 200 everywhere, finite, no trend noise (**bug 2 fixed**) |
| D, E | Dataset start/end boundary | 200; first-week selection correctly falls back to `within_period` |
| F | `MIN_DAYS_FOR_COMPARISON` boundary | 3 days → no comparison, 4 days → `previous_period`, asserted exactly |
| G, H | Narrow merchant / single category | Rate values stay within 0–1 |
| I, J | Thin history / insufficient forecast | `available: false` with a reason; rest of dashboard unaffected |
| K | Empty result | 200 with `has_data: false` and an explanation everywhere |
| L, M | Invalid / reversed dates | 422 / 400 consistently across all five endpoints |
| N, O | Missing / unknown merchant | 422 / 404; lowercase `m001`, SQL-ish and path-ish ids all refused, never fuzzy-matched |
| P | 10-year range | Clamps to the data that exists |
| Q–S | Merchant, preset and date switching | Verified in the browser; every feature moves together |
| T–W | Forecast / assistant / recommendation / insights failure | Isolated; other sections keep rendering |
| X | Backend unavailable | Error panel with working retry (Stage 3 coverage) |
| Y | **Malformed API response** | **3 crashes found and fixed (bug 3)** |
| Z | LLM disabled / no key | Default path; a test fails the suite if a provider is ever called |

## 5–7. Bugs discovered, fixed, and regression-covered

### Bug 1 — the assistant ran the analysis three times (performance)

**Reproduced:** instrumenting the services showed `POST /api/assistant/ask` at
**184.7 ms** with 16 `daily_metrics`, 12 `summary_metrics` and 9
`product_performance` calls.

**Cause:** `build_context()` called `analyse()`, then `recommend()` and
`build_action_plan()` — each of which re-derives `analyse()` internally. Three
full analyses for one answer.

**Fix:** chained through the composable entry points that already existed for
this purpose — `recommendations_from_report(report)` and
`plan_from_recommendations(suggestions)`. No caching introduced.

**Result:** **184.7 ms → 77.0 ms (−58%)**, `analyse()` 3× → 1×. Output verified
byte-identical for findings, recommendations and action plan.

**Regression test:** `test_context_runs_the_analysis_only_once` counts the calls.

### Bug 2 — short date ranges reported the weekly rhythm as business events

**Reproduced:** on M004 with single-day selections:

```
Sun 13 Sep vs Sat 12 Sep:  HIGH  "Revenue fell 26.2% versus the previous 1 days"
Mon 14 Sep vs Sun 13 Sep:  HIGH  "Revenue fell 20.1% versus the previous 1 days"
```

M004's *measured* weekday factors are Saturday 1.37×, Sunday 1.23×, Monday
0.74×. Those "collapses" are the normal week, not a business change.

**Cause — an inconsistency in applying an already-documented rule.**
`analysis.py` documents `MIN_DAYS_FOR_COMPARISON = 4`, but the gate was applied
only to the `within_period` branch. The `previous_period` branch had none, so a
comparison could run on a single day. This was a defect in applying the existing
contract, not a disagreement with it: **the threshold value is unchanged at 4.**

**Fix:** the minimum now gates both comparison paths. Below it, no trend
findings and a note naming the actual length and the requirement.

**Also fixed:** `"the previous 1 days"` → `"the previous 1 day"`.

**Regression tests:** `test_short_selections_produce_no_trend_findings`
(parametrised 1/2/3 days), `test_the_minimum_length_is_honoured_exactly`,
`test_day_counts_read_naturally_in_finding_text`, plus
`test_short_ranges_explain_why_there_are_no_trends` at API level.

### Bug 3 — a malformed forecast payload blanked the entire dashboard

**Reproduced:** feeding `ForecastPanel` a response with `method: null`,
`forecast_period: null` or a missing `limitations` threw
`TypeError: Cannot read properties of null` during render. With no error
boundary, that unmounted the **whole page** — KPIs, charts and all — not just
the forecast panel.

**Cause:** three unguarded dereferences (`method.replaceAll`,
`forecast_period.days`, `limitations.map`), plus `points`/`daily` in
`buildSeries`.

**Fix:** null-safe access in `ForecastPanel`, and a new `PanelBoundary`
component wrapping each of the four data panels so a render failure in one is
contained and labelled rather than fatal.

**Regression tests:** four parametrised malformed-payload tests asserting the
rest of the dashboard still renders, plus `PanelBoundary.test.jsx` (4 tests).

### Weak test strengthened

`test_rows_pass_row_level_validation` asserted nothing — it would have passed if
`validate_rows` became a no-op. It now also feeds a corrupted row and requires
rejection.

## 8. Performance measurements

Median of 10 runs per endpoint, warm dataset cache:

| Endpoint | Before | After |
| --- | --- | --- |
| `/api/dashboard` | 11.7 ms | 11.7 ms |
| `/api/insights` | 57.1 ms | 57.1 ms |
| `/api/recommendations` | 57.8 ms | 57.8 ms |
| `/api/action-plan` | 58.1 ms | 58.1 ms |
| `/api/forecast` | 7.9 ms | 7.9 ms |
| `POST /api/assistant/ask` | **184.7 ms** | **77.0 ms** |

A dashboard page load is five parallel GETs summing to ~193 ms of server time.

**Deliberately not optimised:** the three analysis endpoints each run `analyse()`
exactly once per request, which is correct. Caching across requests was
considered and rejected — 57 ms is not expensive, the requests run in parallel,
and a cache would add an invalidation problem for no measured benefit. The brief
is explicit that caching must not be added for its own sake.

## 9. Optimisations performed

1. **Assistant call chain** (bug 1) — −58% latency, no behaviour change.
2. **Vendor chunk split** — see §10.

That is all. Everything else measured fast enough to leave alone.

## 10. Bundle-size findings

Composition probe: Recharts/d3 markers appear **90×** in the bundle against 3
for React. Recharts is ~94% of the JS.

Splitting it into its own chunk leaves the total unchanged but changes what a
returning user downloads after a deploy:

| | Before | After |
| --- | --- | --- |
| Whole bundle | 592.21 kB / 174.81 kB gzip | 592.18 kB total |
| App chunk | — | 35.3 kB / **9.35 kB gzip** |
| Charts chunk | — | 557.7 kB / 165.31 kB gzip (cached across deploys) |

**A first attempt also split React into its own chunk and produced an empty
1-byte file** — Recharts imports React, so Rollup had already placed it there.
That entry was removed rather than left as a meaningless artefact.

**Not done:** lazy-loading the charts. They are the primary content of the page,
so deferring them would trade a real loading flash for no measured gain. The
>500 kB Vite warning remains and is honest — it cannot be resolved without
dropping Recharts.

## 11. Backend performance findings

`LoadedDataset` is loaded once per process and cached; no endpoint re-reads the
CSVs. `daily_metrics` / `summary_metrics` / `product_performance` are called
several times *within* a single `analyse()` (for the current and baseline
windows) — that is inherent to comparing two periods, not duplication.

The one genuine redundancy was the assistant's triple analysis (bug 1).

## 12. Runner verification

Re-tested after all changes:

| Check | Result |
| --- | --- |
| `.venv` detection | ✓ resolves `.venv/Scripts/python.exe` from system Python |
| npm resolution | ✓ `npm.CMD` on Windows |
| Ports from config | ✓ 8000 from `.env` handling, 5173 from `vite.config.js` |
| Preflight | PASS |
| Missing dependencies | Reports the exact install command; installs nothing |
| Missing `.env` | Falls back to defaults, no crash |
| Duplicate detection | Detects busy IPv4 **and** IPv6 ports |
| Startup | Both services up, logs prefixed |
| **Ctrl+C shutdown** | **exit 0, both ports released, no orphans** |

## 13. Security / configuration audit

| Check | Result |
| --- | --- |
| Secret-pattern scan across **102 tracked files** | **0 matches** |
| `.env` on disk | Not present; git-ignored |
| `LLM_ENABLED` default | `false` in both `.env.example` and `config.py` |
| `LLM_API_KEY` in `.env.example` | Empty |
| Key exposure | With a key deliberately configured, **no endpoint leaked it**; `/api/assistant/status` returns `key_present: true`, a boolean |
| Key in logs | `llm_api_key` appears only in the enabled check, the boolean, and the client constructor |
| `runner.py` subprocess safety | No `shell=True`, `os.system`, `eval` or `exec`; all `Popen` calls use argument lists |
| Debug/dev flags | None |
| Network calls outside `llm.py` | None |

## 14. Dead-code cleanup

**Removed:** 3 unused imports (`CATEGORY_CUSTOMERS`, `CATEGORY_PRODUCT` in
`test_analysis.py`; `numpy` in `test_validation.py`), the now-unused `time`
import left in `runner.py` from Stage 7, and one throwaway probe test file.

**Investigated and deliberately kept:** a scan flagged 8 "unreferenced"
functions — `unhandled_exception_handler`, two Pydantic `model_validator`
methods, and five FastAPI route handlers. Inspecting their decorators confirmed
all are framework-registered. **None were removed.** This is exactly the case
the brief warns about, and the reason the scan output was verified rather than
acted on.

**Duplicate business logic:** none found. All aggregation remains in
`metrics.py`; no `groupby` exists in any other service.

## 15. Dependency audit

Every backend dependency is used: `fastapi` (21 references), `pydantic` (10),
`pandas` (10), `numpy` (5), `pytest` (17), `pydantic-settings` (1), plus
`uvicorn` (invoked by `runner.py`) and `httpx2` (the transport starlette's
TestClient imports). Frontend: `react`, `react-dom`, `recharts` all used.

**Nothing removed** — no unnecessary dependency exists. `scikit-learn` and
`anthropic` remain correctly commented out.

## 16. Warning / deprecation investigation

The single warning is:

```
starlette/testclient.py:53: DeprecationWarning:
  The anyio.abc.BlockingPortal alias is deprecated
```

**Verdict: upstream, test-only, not ours.**

- It fires at a module-level type alias inside `starlette` itself.
- No project file references `anyio` or `BlockingPortal` at all.
- Importing the app under `-W error::DeprecationWarning` produces **no warning** —
  it only appears via starlette's `TestClient`, so it never affects production.
- Cause: starlette 1.6.0 uses an alias that anyio 4.15.1 deprecated.

**Action: none.** Fixing it would mean pinning anyio backwards or upgrading
starlette speculatively — dependency churn for a test-only warning from code we
do not own. It is deliberately **left visible rather than suppressed**, so it
disappears on its own when starlette catches up.

## 17. Browser verification

Against the stack started by `python runner.py`, at 1280×900:

| Check | Result |
| --- | --- |
| Section order | Trends → AI insights → Action plan → Forecast → Assistant ✓ |
| KPIs / charts / insights / actions | 5 values, 10 chart surfaces, 6 insight cards, 8 action cards |
| Forecast, assistant | Trend badge rendered; assistant answered |
| **Panel boundary alerts** | **0** — nothing crashed |
| Horizontal overflow | None |
| **Console errors** | **None** |
| Merchant switch M001 → M003 | ₹34,64,429 → ₹1,78,893; top insight changed to Cold Coffee |
| 7D preset | Range narrowed; forecast reported insufficient history; insights still correct |
| Assistant | Answered from the action plan |

## 18. Remaining limitations

**Unchanged and intentional** — all documented in earlier stages:

- Synthetic data; gross profit excludes overheads; customer counts are visits
  over multi-day windows; inventory is inferred, not live; the data shows what
  changed, never why.
- Forecast: no confidence interval by design; measured MAPE ~20% on full history
  and 52.7% on a 30-day window; cannot anticipate festivals or promotions.
- Assistant with the model off answers from eight keyword-matched intents;
  unusual phrasings fall back to a summary. **No live LLM call has ever been
  made**, so no claim is made about real model output quality.
- Bundle remains ~592 kB total; the >500 kB Vite warning stands.
- The page is seven sections long.

**New, accepted:**

- The numeric grounding guard still allows integers ≤ 31 unchecked.
- `PanelBoundary` catches render errors, not errors thrown inside event handlers
  or async callbacks — React boundaries cannot.
- On Windows a hard kill (`TerminateProcess`) still cannot be intercepted, so
  force-stopping the runner leaves servers running. Ctrl+C and Ctrl+Break are clean.

## 19. Files created

- `frontend/src/components/PanelBoundary.jsx`
- `frontend/src/components/PanelBoundary.test.jsx` (4 tests)
- `tests/test_edge_cases.py` (34 tests)

## 20. Files modified

| File | Change |
| --- | --- |
| `backend/app/services/assistant.py` | Chained the analysis (bug 1); import update; docstring |
| `backend/app/services/analysis.py` | Comparison minimum applied to both paths (bug 2); `_days_phrase` pluralisation |
| `frontend/src/components/ForecastPanel.jsx` | Null-safety on `method`, `forecast_period`, `limitations`, `points`, `daily` (bug 3) |
| `frontend/src/pages/DashboardPage.jsx` | Wrapped four panels in `PanelBoundary` |
| `frontend/vite.config.js` | `manualChunks` vendor split |
| `frontend/src/pages/DashboardPage.test.jsx` | 7 malformed-payload tests |
| `tests/test_analysis.py` | 5 regression tests; 2 unused imports removed |
| `tests/test_assistant.py` | `analyse()`-call-count regression test |
| `tests/test_generator.py` | Strengthened a weak test |
| `tests/test_validation.py` | Unused import removed |
| `runner.py` | Unused `time` import removed |

## 21. Files deleted

`frontend/src/pages/__probe.test.jsx` — a throwaway crash probe, replaced by
permanent tests once it had found bug 3.

## 22. Stage 9 handoff

Stage 9 is Git/GitHub finalisation and deployment. The repository is ready:

1. **Nothing is committed** — 0 commits, and the parent `C:\VS CODE` repository
   is untouched (0 tracked files under this project). The first commit is yours.
2. **Before the first commit**, decide on the nested-repo question raised in
   Stage 1: MerchantAI has its own `.git` inside a parent repo. Adding this path
   to the parent's `.gitignore` avoids it being recorded as an embedded repo.
3. **What ships:** ~102 tracked files. `.env`, `.venv/`, `node_modules/`,
   `dist/` and `__pycache__/` are all correctly ignored; the synthetic CSVs are
   committed on purpose so deployment needs no data step.
4. **Deployment shape** (from `ARCHITECTURE.md`): static `frontend/dist` on any
   static host; `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` for
   the API. Set `VITE_API_BASE_URL` at build time to point the frontend at the
   deployed API.
5. **Production config:** keep `LLM_ENABLED=false` unless a key is deliberately
   provisioned as a platform secret — never committed. `CORS_ORIGINS` will need
   the deployed frontend origin.
6. **`runner.py` is a development convenience**, not a production process
   manager. Do not use it to serve the deployed app.
7. Stage 10 covers the report and presentation; M003 remains the strongest demo
   path (declining revenue, retention dip, failing product, falling forecast, and
   an action plan addressing all of it).
