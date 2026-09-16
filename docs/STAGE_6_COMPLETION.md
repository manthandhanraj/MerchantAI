# Stage 6 — Completion Report

**Status: complete and verified.** Short-term forecasting and the AI business
assistant are built, exposed and rendered on the dashboard.

The assistant runs **offline by default**. `LLM_ENABLED` is false, no key is
configured, and every test in this repository passes with no network access.

## 1. Files created

**Services**
- `backend/app/services/forecasting.py` — the projection
- `backend/app/services/assistant.py` — context assembly, offline answering,
  numeric grounding check
- `backend/app/services/llm.py` — the only module that talks to a provider

**Routes**
- `backend/app/routes/forecast.py`
- `backend/app/routes/assistant.py`

**Frontend**
- `frontend/src/components/ForecastPanel.jsx`
- `frontend/src/components/AssistantPanel.jsx`

**Tests**
- `tests/test_forecasting.py` (38)
- `tests/test_assistant.py` (46)
- `tests/test_api_stage6.py` (36)

## 2. Files modified

| File | Change |
| --- | --- |
| `backend/app/main.py` | Register the two new routers |
| `backend/app/routes/__init__.py`, `services/__init__.py` | Docstrings |
| `frontend/src/services/api.js` | `getForecast`, `getAssistantStatus`, `askAssistant`; `request()` gained POST support |
| `frontend/src/pages/DashboardPage.jsx` | **Additive only**: three new effects, two new sections |
| `frontend/src/pages/DashboardPage.test.jsx` | Mock the new calls; 11 new tests |
| `requirements.txt` | Corrected the optional-dependency comments |
| `.env.example`, `README.md`, `docs/ARCHITECTURE.md` | Status and wording |

No Stage 1–5 service, schema, metric, analysis rule or recommendation rule was
changed. No dataset file was touched.

## 3. Forecasting architecture

```
daily_metrics()  ->  forecasting.py  ->  /api/forecast  ->  ForecastPanel
```

It reuses `filter_dataset()` and `daily_metrics()` and computes no aggregate of
its own. A test asserts the reported history matches `daily_metrics()` exactly
in start, end, day count and mean.

## 4. Forecasting method

**Least-squares linear trend with multiplicative day-of-week factors.**

1. Fit a straight line through the daily series (`numpy.polyfit`, degree 1).
2. Divide each actual by its fitted value, average those ratios per weekday, and
   normalise to mean 1.
3. Project: `trend(future day) × weekday factor`, clamped at zero.

A plain trend or moving average would have been simpler, and the brief suggested
either. The weekly step was added because the dataset's rhythm is large and
measured — Saturday runs 1.37× an average day for the fashion merchant against
Tuesday's 0.77× — so a projection without it would misprice every weekend. The
seasonal step is two lines of arithmetic and no ML library is involved; a test
asserts a tripled-Saturday dataset produces a tripled Saturday forecast.

**scikit-learn is still commented out in `requirements.txt`**, with a note that
it is not needed unless this baseline is shown to be insufficient.

### Accuracy reporting — what is and is not claimed

**No confidence interval is produced.** A least-squares fit can generate one,
but only under assumptions daily retail revenue violates (independent,
evenly-scattered errors; this series is autocorrelated and seasonal). An
interval computed that way would look rigorous and mean nothing. The API returns
`confidence_interval: null` explicitly — stated rather than omitted — with a
limitation explaining why.

Instead the forecast reports a **measured** figure: a holdout backtest that
refits on the earlier history and scores the most recent 7 days, reporting mean
absolute error and MAPE. On the committed dataset with full history this comes
out at roughly 20% MAPE for M003 and M004; on a 30-day window for M001 it is
52.7%. Those numbers are reported as-is, including when they are poor. They
describe past accuracy on this data, not a guarantee.

`fit_r_squared` is returned as `null` for a constant series, because zero
variance leaves nothing for a fit to explain.

## 5. Minimum-data rule

**14 days** (`MIN_HISTORY_DAYS`) — two full weeks, so every weekday has at least
two observations before a seasonal factor is estimated from it. Below that the
forecast returns `available: false` with a reason naming both the days available
and the days required. It is a 200, not an error: too little history is an
answer the UI renders as an explained state.

The backtest additionally needs 7 more days (21 total) and is simply omitted
below that rather than computed on too little data.

## 6. Horizon limitation

`horizon = min(requested, 14, history_days ÷ 2)`.

- Hard cap of **14 days**. The dataset covers months, not years, and carries no
  yearly seasonality to learn from.
- Never more than **half the fitted history**, so a three-week history cannot
  project three weeks.
- The request itself is bounded (`ge=1, le=14`), so an out-of-range horizon is a
  422 rather than being silently reinterpreted.

Both `requested_horizon_days` and the granted `horizon_days` are returned, and
the limitation text ships in every response — including unavailable ones.

## 7. Assistant architecture

```
summary_metrics / daily_metrics / product_performance   (Stage 2)
analyse                                                 (Stage 4)
recommend / build_action_plan                           (Stage 5)
forecast                                                (Stage 6)
        |
        v
    context  ->  answer  ->  /api/assistant/ask  ->  AssistantPanel
```

The assistant recomputes nothing. A test asserts `context["summary"]` is
byte-identical to `summary_metrics()` for the same query, so the assistant
cannot hold a second, divergent set of numbers.

## 8. Context assembled from existing services

| Section | Source |
| --- | --- |
| `summary` | `summary_metrics()` |
| `daily_recent` (last 14 days) | `daily_metrics()` |
| `findings` (top 8) | `analyse()` |
| `recommendations` (top 6) | `recommend()` |
| `action_plan` | `build_action_plan()` |
| `forecast` | `forecast()` |
| `top_products` (top 5) | `product_performance()` |
| `limitations` | standing data caveats + the forecast's own |

## 9. LLM_ENABLED behaviour

**Default false.** A blank `LLM_API_KEY` also counts as disabled, so
`LLM_ENABLED=true` with no key falls back cleanly instead of failing every
request.

**Disabled** — the assistant answers from templates built directly off the
context. Eight intents (summary, decline, best product, focus, improve,
forecast, inventory, customers) are matched by keyword and answered with real
figures. No provider package is imported, no network call is made, no key is
needed. Tests enforce this: an autouse fixture replaces `complete()` with a
function that raises, so any accidental call fails the suite.

**Enabled** — `llm.py` calls the configured provider through one function. The
`anthropic` package is imported lazily inside it, so it is not a runtime
dependency while the feature is off. Every failure — disabled, unsupported
provider, missing package, network, API error, empty reply — becomes an
`LLMError`, and the assistant degrades to the offline answer with a warning. The
request still returns 200.

### The model cannot invent numbers

Two mechanisms:

1. The system prompt states every figure must come from the context, that it
   must never estimate or extrapolate, and that it must never assert a cause.
2. **Enforcement.** Every number in the reply is checked against the context.
   Any figure that cannot be traced causes the reply to be **discarded** in
   favour of the deterministic answer, with a warning naming the untraceable
   values. Tests cover both directions: a fabricated reply is rejected, a
   grounded one is accepted.

The check accepts a value in any form the context supports it: raw, rounded,
×100 for a rate written as a percentage, and absolute value for a change written
as a magnitude ("fell 16.7%" against a stored `-0.167`). Integers of 31 or less
pass as calendar or ordinal references.

## 10. API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/forecast` | Projection, with `metric` and `horizon_days` |
| `POST /api/assistant/ask` | Grounded answer to a question |
| `GET /api/assistant/status` | Whether the model is on — never the key itself |

All use the existing `LoadedDataset` dependency and `validate_query()`, so error
behaviour matches Stages 3–5: 404 unknown merchant, 422 missing or malformed,
400 inverted range, 503 broken pipeline, no tracebacks.

Insufficient data and an unknown metric are **200 with a reason**, not errors.

## 11. Frontend changes

`docs/USER_FLOW.md` places both the forecast and the assistant at Stage 6.

**ForecastPanel** — projected total, recent daily average, measured error, a
trend badge, a chart of recent actuals joining the projection, and every
limitation listed. When unavailable it shows the reason and draws no chart.

**AssistantPanel** — question box, one-tap starter questions, the answer, where
the answer came from, any warnings, and a collapsible "what this answer cannot
tell you".

It reuses `TrendChart` rather than introducing a second chart component, so axes
and tooltips match the rest of the dashboard.

**Isolation.** Forecast, action plan and assistant are three separate requests.
Tests assert that a failing forecast still leaves KPIs, charts and action plan
rendered, and that a failing assistant leaves the forecast and KPIs rendered.
No KPI card, chart, merchant selector or date control was modified.

## 12. Tests added

**131 new** — 120 backend, 11 frontend.

| Suite | Tests |
| --- | --- |
| `test_forecasting.py` | 38 |
| `test_assistant.py` | 46 |
| `test_api_stage6.py` | 36 |
| `DashboardPage.test.jsx` (forecast + assistant) | 11 |

All 28 numbered requirements are covered, including: deterministic output,
identical repeat calls, too-few-points refusal, horizon enforcement, no
current-date dependency (asserted by source inspection *and* by checking the
forecast starts the day after the history), reuse of `daily_metrics`, every
context section, `LLM_ENABLED=false` never calling out, provider-failure
containment, and fabricated-number rejection.

## 13. Complete test counts

| | Before Stage 6 | After Stage 6 |
| --- | --- | --- |
| Backend | 260 | **380** |
| Frontend | 40 | **51** |
| **Total** | **300** | **431** |

```
backend   380 passed, 1 warning in 22.29s
frontend   51 passed (2 files)
build      ✓ succeeds
```

The single warning is the pre-existing upstream starlette/anyio deprecation,
present since Stage 1.

## 14. Real-data verification

**Merchant with meaningful trends (M003, declining café):** forecast available,
trend `falling`, 7-day horizon, ₹41,101 projected, 20.6% measured MAPE.

**Merchant with insufficient data (M001 over a 7-day window):** `available:
false`, reason *"Only 7 day(s) of history in this period. At least 14 are
needed…"*. Verified in the browser: the panel shows the explanation, draws no
chart, and the KPIs, action plan and assistant all remain rendered.

Trend direction matches the Stage 2 design for every merchant — M001 rising,
M003 falling, M004 rising.

Browser verification at 1280×900: all seven sections render, no horizontal
overflow, **no console errors**. The rendered forecast total matched the API to
the rupee (₹6,99,995). Clicking a starter question produced a grounded answer
labelled "Composed directly from this merchant's data".

## 15. Bugs found and fixed

1. **Trend direction called a growing merchant "flat".** The threshold compared
   the daily slope to the daily mean, so +₹146/day — 0.15% of an average day but
   27% across six months — fell under it. M001, the deliberately growing
   merchant, read as flat. Now judged on the line's total movement across the
   history. Caught by comparing output against the Stage 2 design.
2. **The grounding check rejected correct answers.** The context stores signed
   changes (`-0.167`) while prose writes magnitudes ("fell 16.7%"), so every
   accurate statement about a decline was flagged as fabricated. Absolute-value
   variants are now accepted.
3. **The grounding check flagged years.** "2026" appears inside ISO date
   strings, which were not scanned for numbers. Numbers inside context *strings*
   are now collected too — anything already written in the context is by
   definition traceable to it.
4. **Assistant intent misrouted an improvement question.** *"How can I improve
   next week's revenue?"* matched "next week" and returned a projection instead
   of actions. "next week" was removed from the forecast keywords and `improve`
   now precedes `forecast`.
5. **Unused `pandas` import** in `forecasting.py`, found by the quality audit.
6. **Frontend mock did not know the new calls**, breaking 26 Stage 3–5 tests —
   the existing suite doing its job. Fixed by extending the mock.

## 16. Determinism verification

No `date.today`, `datetime.now` or `time.time()` anywhere in `backend/` — grepped
and asserted by a test that inspects the forecasting module's source. No
randomness. The forecast always begins the day after the last observed date, and
a test asserts that date is not today's.

Repeated calls are asserted identical at three levels: the forecast dataclass,
the assistant answer, and the HTTP responses.

## 17. Regression verification

| Check | Result |
| --- | --- |
| Backend suite | 380 passed |
| Frontend suite | 51 passed |
| `npm run build` | Succeeds |
| Backend startup | Clean; 12 routes |
| All Stage 1–5 endpoints | 200 |
| Stage 3 dashboard in browser | 5 KPIs, 3 charts, selector, date controls — intact |
| Browser console | No errors |
| Assistant failure vs other endpoints | Dashboard, insights, action-plan all still 200 |
| Forecast unavailable vs dashboard | Dashboard still `has_data: true` |
| Stage 6 period vs dashboard period | Asserted identical |
| Unused imports / dead code / duplicated aggregation | None |
| Network calls outside `llm.py` | None |
| Secrets or build artifacts staged | None |

## 18. Limitations

**Forecasting**
- **No confidence interval**, by design. The reported error is a backtest of past
  performance, not a bound on future error.
- **Measured accuracy is modest and varies.** ~20% MAPE on full history, 52.7%
  on a 30-day window for M001. It is reported honestly rather than hidden.
- The projection continues the observed trend and weekly pattern only. It cannot
  anticipate festivals, promotions, stock-outs or price changes — which is
  material for M004, whose festival days run ~3× its median.
- A linear trend will drift wrong over longer spans; hence the 14-day cap.
- Only weekly seasonality is modelled. 180 days cannot support yearly patterns.

**Assistant**
- **With the model disabled — the default — answers are templated.** They are
  accurate and grounded, but they are composed from a fixed set of eight intents,
  not generated. A question outside those intents falls back to a summary.
- Intent matching is keyword-based and will misroute unusual phrasings.
- **No LLM accuracy has been measured.** The model path is implemented and its
  failure and fabrication behaviour are tested with a substituted `complete()`,
  but no live provider call was made during this stage, so nothing is claimed
  about real model output quality.
- The grounding check allows integers ≤ 31 unchecked, so a fabricated small
  number could pass. It targets the figures that matter — revenue, orders,
  customers, forecasts.
- It does not hold conversation state; each question is answered independently.
- It inherits every upstream caveat: gross profit excludes overheads, customer
  counts are visits over multi-day windows, inventory is inferred, and the data
  shows what changed, not why.

## 19. Deliberately deferred

- **scikit-learn and any heavier model.** The transparent baseline has not been
  shown insufficient, so adding one would be unjustified weight.
- **Prediction intervals via bootstrap or residual simulation.** Defensible, but
  more machinery than a days-to-weeks projection warrants here.
- **Forecasting anything but the daily series** — no per-product or per-category
  projection.
- **Conversation memory and follow-up questions** in the assistant.
- **A live provider call.** Enabling it needs a key, which belongs to the user,
  not to this repository.
- **Streaming responses** and **caching of assistant answers.**

## 20. Stage 7 handoff

Stage 7 is full integration into a demonstrable MVP. The parts all exist and are
individually verified; the work is making them one coherent product.

1. **Walk the whole user flow against `docs/USER_FLOW.md`.** One gap is known and
   deliberate: the **Insights** and **Business health** rows are marked Stage 4
   in that document but were never rendered — `/api/insights` is API-only. Either
   add an insights section to `DashboardPage.jsx` (the data is already there, and
   `StatusPanel` handles its states) or amend USER_FLOW to record the decision.
2. **Review page length.** The dashboard is now seven sections. Consider whether
   the trend charts and the forecast should sit together, and whether the
   assistant belongs higher.
3. **Check the bundle.** It is ~575 KB (171 KB gzipped), dominated by Recharts.
   Code-splitting is the obvious lever if it matters for the demo.
4. **Rehearse the demo path end to end**: M003 tells the strongest story —
   declining revenue, a retention dip, a failing product, a falling forecast, and
   an action plan that addresses all of it.
5. **Decide on the LLM for the demo.** It runs fully without a key. If it is to be
   enabled, uncomment `anthropic` in `requirements.txt`, set `LLM_ENABLED=true`
   and `LLM_API_KEY` in `.env` (never committed), and test a live call — none has
   been made yet.
6. **Nothing is committed.** Stage 9 covers GitHub and deployment; the repository
   has 0 commits and the parent repository is untouched.
