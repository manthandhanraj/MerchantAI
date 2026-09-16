# Stage 7 — Completion Report

**Status: complete and verified.** Everything built in Stages 1–6 now runs as one
coherent application, launched with a single command.

```bash
python runner.py
```

## 1. Files created

- `runner.py` — starts the backend and frontend together
- `frontend/src/components/InsightsPanel.jsx` — the Stage 4 engine, finally rendered
- `tests/test_runner.py` (25)
- `tests/test_integration.py` (62)

## 2. Files modified

| File | Change |
| --- | --- |
| `frontend/src/pages/DashboardPage.jsx` | Insights fetch + panel; sections reordered into the integrated flow |
| `frontend/src/services/api.js` | Added `getInsights` |
| `frontend/src/pages/DashboardPage.test.jsx` | Mock the new call; 11 Stage 7 tests |
| `README.md` | Rewritten Quick Start around `python runner.py` |

No backend service, schema, metric, analysis rule, recommendation rule or API
contract was changed. Stage 7 is integration, not reconstruction.

## 3. Full integration architecture

```
data/raw/*.csv
    -> data_loader (validate, normalise, cache once)
    -> metrics       summary_metrics / daily_metrics / product / category / inventory
         |
         +--> dashboard.py     -> /api/dashboard      -> KPI cards + trend charts
         +--> analysis.py      -> /api/insights       -> InsightsPanel
         |         |
         |         +--> recommendations.py -> /api/recommendations
         |                   |
         |                   +--> action_plan.py -> /api/action-plan -> ActionPlanPanel
         +--> forecasting.py   -> /api/forecast       -> ForecastPanel
                   |
                   +--> assistant.py -> /api/assistant/ask -> AssistantPanel
                            (context = summary + daily + findings +
                             recommendations + action plan + forecast)
```

Each layer consumes the one above it rather than recomputing. Integration tests
assert this is real, not just intended:

- every recommendation's `source_finding` exists in `/api/insights` for the same query;
- every action-plan item traces to a recommendation;
- the assistant's `context["summary"]` is byte-identical to `/api/dashboard`'s summary;
- the forecast's first projected day is the day after the last charted day;
- all five GET endpoints report the identical period object.

## 4. Dashboard integration

The page now follows the intended reading order, numbered in the source:

1. **Business overview** — five KPI cards
2. **Performance trends** — revenue/profit, orders, new vs repeat customers
3. **AI insights** — findings with severity and the threshold that flagged each *(new)*
4. **Growth recommendations** — the prioritised High/Medium/Low action plan
5. **Forecast** — actuals joining the projection
6. **AI assistant** — question box grounded in everything above

**The gap Stage 6 flagged is closed.** `/api/insights` had existed since Stage 4
but was never rendered; `InsightsPanel` now shows it. The forecast and action
plan were also swapped so recommendations sit next to the insights that produced
them, matching the flow this stage specified.

Each feature fetches independently, so one failure cannot blank the others.

**Deliberately not built:** USER_FLOW lists a "Business health" row. No composite
health score exists in the backend, and computing one in the browser would put
business logic in a component. The panel shows the severity counts the API
actually returns (`3 high, 7 medium, 7 low`) instead of inventing a score.

## 5. API integration

Nine endpoints, all sharing the `LoadedDataset` dependency and `validate_query`:

`/api/health` · `/api/merchants` · `/api/dataset/summary` · `/api/dataset/validation` ·
`/api/dashboard` · `/api/insights` · `/api/recommendations` · `/api/action-plan` ·
`/api/forecast` · `/api/assistant/ask` · `/api/assistant/status`

Parametrised tests assert consistent behaviour across the whole surface: 404 for
an unknown merchant, 400 for an inverted range, 422 for a missing parameter, 503
for a missing dataset, no tracebacks, and no `NaN`/`Infinity` in any response for
any merchant.

## 6. Forecast integration

`ForecastPanel` reuses `TrendChart`, so the projection shares the axes, tooltip
and spacing of every other chart. Recent actuals and the projection are separate
series joined at the last observed day. Insufficient history renders the reason
with no chart — verified in the browser, with KPIs, insights, action plan and
assistant all still rendered alongside it.

## 7. AI assistant integration

The assistant receives the complete current business context — summary, recent
daily series, findings, recommendations, action plan, forecast and top products —
all from the existing services. Verified by test: its summary equals the
dashboard's, and its findings are a subset of the insights endpoint's.

It remains **offline by default**. `LLM_ENABLED=false`, no key, no network. Tests
replace `complete()` with a function that raises, so any accidental provider call
fails the suite.

## 8. runner.py implementation

Standard library only — `subprocess`, `socket`, `signal`, `threading`, `re`,
`shutil`. A test parses its imports and asserts they are all stdlib.

| Behaviour | How |
| --- | --- |
| Finds the project | Paths derived from `__file__`; nothing hard-coded |
| Finds the interpreter | Prefers `.venv`, so plain `python runner.py` works without activating it |
| Finds npm | `shutil.which`, which resolves `npm.cmd` on Windows |
| Reads configuration | `API_PORT`/`API_HOST` from `.env`, frontend port from `vite.config.js` |
| Preflight | Checks both entry points, backend deps, `node_modules`, npm — reporting the exact fix command |
| Installs nothing | Reports problems only; never runs pip or npm install |
| No duplicates | Probes each port on IPv4 **and** IPv6 and leaves a running service alone |
| Clear startup | Prints the frontend URL, backend URL and API docs URL |
| Prefixed logs | `[backend]` / `[frontend]` on every line, via reader threads |
| Reports real port | Reads Vite's own banner back and corrects the URL if it moved |
| Surfaces failures | An unexpected child exit prints which one and its exit code, then stops the rest |
| Clean shutdown | SIGINT, SIGTERM and SIGBREAK all route through one flag; children stopped with `taskkill /T` on Windows, process group on POSIX |

`--check` runs the preflight and exits, which is how the setup is verified
without starting servers.

## 9. How runner.py was verified

Actually run, not assumed:

1. **`python runner.py --check`** → "Preflight passed", exit 0 — using the
   *system* Python, confirming the `.venv` discovery works.
2. **`python runner.py`** → both services started; log showed
   `[backend] Application startup complete` and `[frontend] VITE ready`.
3. **All nine endpoints through the Vite proxy** on `localhost:5173` → 200,
   including `POST /api/assistant/ask`.
4. **Shutdown**: a script started the runner in its own process group, waited for
   both ports, sent `CTRL_BREAK_EVENT`, and confirmed exit code 0 with **both
   ports released and no orphans**.
5. **Duplicate detection**: with a service already listening, the runner reported
   it and did not start a second one.

## 10. Test results

| | Before Stage 7 | After Stage 7 |
| --- | --- | --- |
| Backend | 380 | **467** |
| Frontend | 51 | **62** |
| **Total** | **431** | **529** |

```
backend   467 passed, 1 warning in 32.70s
frontend   62 passed (2 files)
```

New: `test_integration.py` (62), `test_runner.py` (25), 11 frontend integration
tests. The single warning is the pre-existing upstream starlette/anyio
deprecation from Stage 1.

## 11. Build result

`npm run build` succeeds.

## 12. Browser verification

Against the stack started by `python runner.py`, at 1280×900:

| Check | Result |
| --- | --- |
| Section order | Trends → AI insights → Action plan → Revenue forecast → Assistant ✓ |
| KPIs | 5 values rendered |
| Charts | Drawn, including the forecast's actual/projected join |
| Insights | 6 cards shown of 17, severity chips `3 high / 7 medium / 7 low` |
| Action plan | 8 cards, ranks 1–8 |
| Forecast | Trend badge, projected total, measured error, limitations |
| Assistant | Starter chips; answer rendered and labelled as composed from data |
| Horizontal overflow | None |
| **Console errors** | **None** |

**Merchant switching** M001 → M002: revenue ₹34,64,429 → ₹9,28,205 and the top
insight changed to *"Cooking Oil 1L has 0.8 days of stock cover"* — M002's
designed stock-out. **Date preset** → All: range widened and revenue became
₹53,67,658, matching the Stage 2 figure exactly. Forecast trend moved
Falling → Flat → Rising across those changes. Every feature moved together.

## 13. Bugs found and fixed

1. **Runner advertised a port Vite was not using.** Vite silently hops when its
   port is taken; the runner printed 5173 while Vite was on 5177. It now reads
   Vite's own banner back and prints a correction.
2. **Duplicate detection missed IPv6-only listeners.** `port_in_use` probed
   `127.0.0.1` only, but Node binds `[::1]` by default — so a busy Vite port read
   as free and the runner started a duplicate. Both families are now probed.
   Covered by a regression test.
3. **Ctrl+Break skipped all cleanup, orphaning both servers.** Python's default
   SIGBREAK action terminates the process outright, so the shutdown code never
   ran (exit code `0xC000013A`). SIGINT, SIGTERM and SIGBREAK now route through
   one flag. Verified: exit 0 and both ports released.
4. **Frontend test mock broke 32 existing tests** when `getInsights` was added —
   the existing suite catching new code, as it should.
5. **An integration test asserted the wrong thing.** It expected M001's forecast
   to read "rising" over the last 30 days, but that window sits after the
   festival peak where M001 genuinely falls. The designed trend holds over full
   history; the test was corrected and now asserts each claim over the window it
   actually applies to.
6. **Unused `time` import** left after switching to an event-based wait.

Orphaned Node processes from earlier stages were also cleared; they were holding
ports 5173–5176 and were an artefact of force-stopping dev servers — precisely
what the runner's `taskkill /T` now prevents.

## 14. Known limitations

- **A hard kill cannot be intercepted.** On Windows `Popen.terminate()` is
  `TerminateProcess`, which no program can catch — force-stopping the runner
  leaves the servers running. Ctrl+C and Ctrl+Break are both clean. The runner
  detects leftover ports on the next start and prints how to free them.
- **No composite business-health score** — see §4.
- **The bundle is ~575 KB** (171 KB gzipped), dominated by Recharts. Adding the
  insights panel did not materially change it. Code-splitting is a Stage 8 call.
- **The page is long** — seven sections on one scroll. Tabs or anchors were
  considered and deferred as a redesign beyond Stage 7's remit.
- **The runner does not check dependency *versions***, only that imports resolve.
- **No live LLM call has been made.** The model path is implemented and its
  failure and fabrication handling are tested with a substituted client, but
  nothing is claimed about real model output.
- Everything inherits the upstream data caveats: synthetic data, gross profit
  excludes overheads, customer counts are visits over multi-day windows,
  inventory is inferred, and the data shows what changed, not why.

## 15. Stage 1–6 regression verification

| Check | Result |
| --- | --- |
| Backend suite | 467 passed |
| Frontend suite | 62 passed |
| `npm run build` | Succeeds |
| All Stage 1–6 endpoints | 200 |
| Dataset, schema, validation rules | Untouched |
| Metric / analysis / recommendation logic | Untouched |
| API response shapes | Unchanged; the only new frontend call is to an endpoint that already existed |
| KPI cards, charts, selector, date controls | Intact |
| `.env` git-ignored, `LLM_ENABLED=false`, key blank | Confirmed |
| Secrets in tracked source | None |
| Unused imports in new files | None |

## 16. Exact command to run the project

```bash
python runner.py
```

From the project root. Opens the API on `http://127.0.0.1:8000` and the web app
on `http://localhost:5173`. Press **Ctrl+C** to stop both.

First time only:

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## 17. Stage 8 handoff

Stage 8 is deep analysis, debugging, performance and cleanup. Concrete starting
points, all observed during this stage:

1. **Bundle size.** 575 KB / 171 KB gzipped, almost entirely Recharts. Lazy-load
   the chart components or split the vendor chunk.
2. **Request count.** The dashboard fires five requests per merchant/date change
   (dashboard, insights, recommendations via action-plan, forecast, plus the
   assistant on demand). Each re-runs `analyse()` server-side. A short-lived
   cache keyed on `(merchant_id, start, end)` would remove repeated work —
   measure first.
3. **Page length.** Seven sections; consider tabs or in-page anchors.
4. **Edge cases worth hunting:** single-day ranges, a merchant with one product,
   a range covering a stock-out, and the `within_period` comparison basis at
   exactly `MIN_DAYS_FOR_COMPARISON`.
5. **Dead code sweep** across all stages — Stage 7 only removed what it
   introduced, as instructed.
6. **The starlette/anyio deprecation warning** has been present since Stage 1.
   Decide whether to pin around it or accept it.
7. **Frontend test coverage** is concentrated in `DashboardPage.test.jsx`.
   Individual panels have no direct unit tests.

Nothing is committed. The repository has 0 commits and the parent repository is
untouched — Stage 9 covers Git and deployment.
