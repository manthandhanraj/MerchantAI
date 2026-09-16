# Stage 1 — Completion Report

**Status: complete.** Planning and project foundation are locked; Stage 2 can
begin immediately.

## What was completed

The project directory was empty at the start of Stage 1, so everything below is
new. No existing work was modified or removed.

1. **Scope locked** — problem statement, target user, MVP boundaries, explicit
   exclusions → [MVP_SCOPE.md](MVP_SCOPE.md)
2. **Architecture locked** — layers, responsibilities, data flow, full API
   contract, stack rationale → [ARCHITECTURE.md](ARCHITECTURE.md)
3. **Data schema locked** — two CSVs, columns, types, invariants, derived
   metrics → [DATA_SCHEMA.md](DATA_SCHEMA.md) + `backend/app/models/schemas.py`
4. **User flow locked** → [USER_FLOW.md](USER_FLOW.md)
5. **Conventions locked** → [CONVENTIONS.md](CONVENTIONS.md)
6. **Runnable skeleton built** — FastAPI app with a health endpoint, React app
   that calls it, both verified running together
7. **Config foundation** — `.env.example`, env-driven `Settings`, no secrets in code
8. **Test harness** — 7 passing tests covering the API and the data contract
9. **Git repository initialised** with a `.gitignore` covering secrets, venvs,
   `node_modules/` and build output

## Final architecture

```
Merchant -> React frontend -> FastAPI routes (thin)
                                   |
                         Analytics / data layer     (load, validate, aggregate)
                                   |
                         AI intelligence layer
                          - business analysis
                          - recommendations
                          - forecasting
                                   |
                            Action plan
                                   |
                            AI assistant   (consumes all of the above as context)
```

The assistant sits at the bottom deliberately: it consumes computed analytics as
context rather than reasoning over raw data. **Numbers are computed in Python;
the LLM explains them and never calculates them.** That single rule is what
makes the assistant a business partner instead of a chatbot.

## Final tech stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Frontend | React 18 + Vite 6 | Required stack; fast dev loop |
| Styling | Tailwind CSS v4 | Utility CSS via Vite plugin — no config files to break |
| Charts | Recharts 3 | React-native charting for trend lines |
| API | FastAPI + Uvicorn | Typed, auto-documented, minimal boilerplate |
| Validation/config | Pydantic 2 + pydantic-settings | Enforces the data contract; keeps secrets in env |
| Analytics | pandas + NumPy | Aggregation and trend maths over CSV |
| Tests | pytest + httpx2 | API and data-contract coverage |
| Storage | CSV files | Small, read-only dataset — a database would add ops cost for no gain |

Deferred on purpose: **scikit-learn** (Stage 6, only if a moving-average/linear
baseline proves insufficient) and the **LLM client** (Stage 6). Both are listed
as commented entries in `requirements.txt`.

## Final MVP scope

**In:** dashboard (revenue, orders, customers, profit, AOV, trends) · business
intelligence (revenue, trends, product performance, customer insights, health) ·
growth intelligence (growth, product, retention, inventory recommendations,
priority actions) · short-term forecasting · grounded AI assistant · High/Medium/Low
action plan.

**Out:** authentication, real/private payment data, live ingestion, databases,
Docker/K8s, microservices, multi-tenancy, billing, notifications, mobile app,
long-horizon forecasting, write-backs to the merchant's business.

## Dataset schema

Two flat CSVs joined on `(date, merchant_id)`.

**`merchant_sales.csv`** — grain `(date, merchant_id, product)`:
`date`, `merchant_id`, `product`, `category`, `orders`, `units_sold`, `revenue`,
`expenses`, `inventory`

**`merchant_customers_daily.csv`** — grain `(date, merchant_id)`:
`date`, `merchant_id`, `customers`, `new_customers`, `repeat_customers`

**Derived at request time, never stored:** `profit`, `profit_margin`,
`average_order_value`, `growth_rate`, `repeat_customer_rate`, `new_customer_rate`,
`revenue_per_customer`, `days_of_inventory_cover`.

Full column types, invariants and formulas: [DATA_SCHEMA.md](DATA_SCHEMA.md).

## Folder structure

```
MerchantAI/
├── backend/app/{main,config}.py, routes/, services/, models/, utils/
├── frontend/src/{App.jsx,main.jsx,index.css}, components/, pages/, services/
├── data/{raw,processed,sample}/
├── ml/
├── tests/
├── docs/
├── .env.example, .gitignore, requirements.txt, pytest.ini, README.md
```

## Decisions made

1. **Two CSVs instead of one.** Customer counts sit at daily grain because a
   customer buying two products in a day would be double-counted in a
   product-grain table — and `.sum()` is the instinctive thing to reach for in
   pandas. Splitting the grain makes the correct thing the easy thing, at the
   cost of one `pd.merge`.

2. **One product per order in the synthetic data.** Makes `orders` fully additive
   across products, so `AOV = revenue / orders` is correct at every level. A
   simplification, and the reason the arithmetic is trustworthy.

3. **`units_sold` added beyond the specified fields.** Inventory advice needs
   sales velocity in units against stock on hand; without it, days-of-cover is
   wrong whenever an order carries more than one unit. Inventory suggestions are
   in locked scope, so the column earns its place.

4. **Derived metrics are computed, never stored.** Stored derivations drift out
   of sync with their inputs.

5. **No database.** The dataset is small, synthetic and read-only. Loading once
   into pandas is faster to build, faster to run and trivial to deploy.

6. **Tailwind v4 via the Vite plugin**, with no `tailwind.config.js` or
   `postcss.config.js`. Fewer moving parts and no content-glob misconfiguration —
   the most common way Tailwind silently fails. Flagged in SETUP.md so nobody
   "fixes" it by adding v3 config files.

7. **React 18 + Recharts 3.** Recharts 2.x is deprecated upstream; v3 is current
   and supports React 18 and 19.

8. **`httpx2` over `httpx`.** Starlette's TestClient deprecates plain `httpx`;
   `httpx2` is the same author's successor (verified: Tom Christie, pydantic org)
   and keeps the test run warning-free.

9. **Dedicated git repository.** See "Requires your attention" below.

10. **App runs with no LLM key.** With `LLM_ENABLED=false` everything except the
    assistant works, so the project is always demoable.

## Requires your attention

**The project now has its own git repository.** The parent folder `C:\VS CODE`
is itself a git repo holding unrelated work (portfolio, coursework, other
projects). Committing MerchantAI into it would have made the Stage 9 GitHub push
messy, so MerchantAI was initialised as a self-contained repo at the project root.

Two consequences:
- The parent repo will show `Hackathon Projects/Merchant Growth AI/` as an
  untracked embedded repository. Adding it to the parent's `.gitignore` avoids
  that noise — not done here, since it means editing a repo outside this project.
- Nothing has been committed yet. The first commit is yours to make.

If you would rather MerchantAI live inside the parent repo, delete the nested
`.git` directory and it will be tracked by the parent again.

## Intentionally NOT implemented

No Stage 2–7 work exists. Specifically absent, by design:

- ❌ Dataset generation (Stage 2) — `data/raw/` holds only `.gitkeep`
- ❌ Data loading, metrics, aggregation (Stages 2–3)
- ❌ Dashboard UI, metric cards, charts (Stage 3) — `App.jsx` is a connectivity check only
- ❌ Business analysis and insights (Stage 4)
- ❌ Recommendation engine and action plan (Stage 5)
- ❌ Forecasting (Stage 6) — `ml/` is empty
- ❌ LLM integration and assistant (Stage 6) — config placeholders only, no client, no key
- ❌ Endpoint stubs for future stages — the API contract is documented, not stubbed

The only non-placeholder code is `/api/health`, `/`, the config layer and the
schema models. Routes, services, utils and ml packages contain documentation
docstrings and no logic.

## Validation performed

| Check | Result |
| --- | --- |
| Backend dependencies install cleanly | ✅ |
| `pytest` | ✅ 7 passed |
| `uvicorn backend.app.main:app` boots | ✅ |
| `GET /api/health` and `GET /` return 200 | ✅ |
| `npm install` | ✅ 118 packages, no deprecation warnings (Recharts 3.10.1) |
| `npm run build` | ✅ production build succeeds |
| Frontend ↔ backend wired via Vite proxy | ✅ verified live in browser |
| Browser console errors | ✅ none |
| Sample data validates against the schema | ✅ |
| Schema invariants reject bad rows | ✅ covered by tests |
| No secrets committed | ✅ `.env` git-ignored, `.env.example` has placeholders only |
| Docs match the real structure | ✅ |
| No Stage 2–7 implementation present | ✅ |

## Exact next step for Stage 2

Write `data/generate_dataset.py` to produce `data/raw/merchant_sales.csv` and
`data/raw/merchant_customers_daily.csv`, conforming exactly to
[DATA_SCHEMA.md](DATA_SCHEMA.md).

1. Generate 3–6 months of daily history for 3–5 merchants, 5–10 products each.
2. Preserve the **one product per order** rule and every documented invariant.
3. Build in realistic, *explainable* signal — weekly seasonality, a category
   trending up, one product declining, a stock-out risk, a retention dip. Stages
   4–6 need genuine patterns to find, and the demo needs findings that survive
   being questioned.
4. Validate output with `SalesRecord` / `CustomerDailyRecord` before writing.
5. Extend `tests/test_data_schema.py` to run the same checks against `data/raw/`.
6. Add `backend/app/services/data_loader.py` to load and cache both CSVs.
7. Commit the generated CSVs — small, synthetic, and it keeps deployment free of
   a data-provisioning step.

`GET /api/health` will report `sales_data_present: true` once step 1 lands. That
is the Stage 2 smoke test.
