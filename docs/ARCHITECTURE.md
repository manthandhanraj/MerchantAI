# Architecture

Status: **locked in Stage 1**.

## Principle

One frontend, one backend, one dataset. Layers are separated by *responsibility*,
not by deployment — everything runs as a single FastAPI process. The layering
exists so the AI Assistant can reuse the same analysis the dashboard shows,
which is what stops it becoming a generic chatbot.

## Logical architecture

```
                    Merchant
                       |
            Frontend Dashboard (React)
                       |  HTTP / JSON
            ┌──────────▼──────────┐
            │   FastAPI Backend   │   routes/  - thin HTTP layer
            └──────────┬──────────┘
                       |
            Analytics / Data Layer      services/data_loader.py
            (load, validate, cache,     services/metrics.py
             aggregate, derive metrics)
                       |
            ┌──────────▼──────────┐
            │ AI Intelligence     │
            │  - Business analysis│   services/analysis.py
            │  - Recommendations  │   services/recommendations.py
            │  - Forecasting      │   services/forecasting.py + ml/
            └──────────┬──────────┘
                       |
                 Action Plan             services/action_plan.py
                       |
                 AI Assistant            services/assistant.py
```

**The arrows matter.** The Assistant sits at the bottom on purpose: it consumes
the outputs of every layer above it as context. It never queries the LLM about
raw data, and it never invents numbers.

## Layer responsibilities

| Layer | Location | Responsibility | Must not |
| --- | --- | --- | --- |
| Frontend | `frontend/src/` | Render data, capture questions | Contain business logic or compute metrics |
| Routes | `backend/app/routes/` | Parse input, call one service, return | Contain analysis logic |
| Services | `backend/app/services/` | All business logic and analysis | Import FastAPI objects |
| Data layer | `services/data_loader.py`, `metrics.py` | Load/validate CSVs, aggregate, derive metrics | Make recommendations |
| Intelligence | `analysis.py`, `recommendations.py`, `forecasting.py` | Interpret metrics, produce findings | Re-read CSVs directly |
| ML | `ml/` | Model code and offline experiments | Depend on FastAPI |
| Assistant | `services/assistant.py` | Ground LLM answers in computed analytics | Answer from raw data or from memory |

The rule that keeps this honest: **numbers are computed in Python, never by the
LLM.** The LLM explains and phrases; it does not calculate.

## How the AI Assistant stays grounded

1. A question arrives at `POST /api/assistant/ask`.
2. The Assistant calls the *same* services the dashboard uses to build a compact
   context object: current metrics, recent trends, top/bottom products, customer
   position, forecast, and the active action plan.
3. That context is injected into the prompt with an instruction to answer only
   from it, and to say so when the data does not support an answer.
4. The LLM returns prose; the numbers in it came from step 2.

This is why the layering is worth having in an MVP — it is what makes the
Assistant trustworthy rather than decorative.

## Data flow

```
data/raw/*.csv
   -> data_loader   (read once, validate against models/schemas.py, cache in memory)
   -> metrics       (revenue, orders, customers, profit, AOV, trends)
   -> analysis / recommendations / forecasting
   -> action_plan
   -> API responses -> React
```

The dataset is small, read-only and loaded once into pandas at startup. That is
the entire reason no database is required.

## Planned API surface

Endpoints marked ✅ are implemented. The rest is the agreed contract for later
stages — documented here so the frontend and backend can be built against the
same shape.

| Endpoint | Method | Stage | Purpose |
| --- | --- | --- | --- |
| `/api/health` | GET | 1 ✅ | Service + data readiness |
| `/api/merchants` | GET | 2 ✅ | List merchant ids for the selector |
| `/api/dataset/summary` | GET | 2 ✅ | Dataset shape + portfolio totals |
| `/api/dataset/validation` | GET | 2 ✅ | Dataset validation report |
| `/api/dashboard` | GET | 3 ✅ | Headline metrics + trend series |
| `/api/insights` | GET | 4 ✅ | Explainable business findings with severity |
| `/api/recommendations` | GET | 5 ✅ | Growth, product, retention, inventory suggestions |
| `/api/action-plan` | GET | 5 ✅ | Actions bucketed High/Medium/Low |
| `/api/forecast` | GET | 6 ✅ | Short-term revenue forecast |
| `/api/assistant/ask` | POST | 6 ✅ | Grounded natural-language Q&A |
| `/api/assistant/status` | GET | 6 ✅ | Assistant configuration (never the API key) |

Convention: every GET above takes `merchant_id` and an optional date range.

## Technology stack and why

| Choice | Used for | Reason |
| --- | --- | --- |
| React + Vite | Frontend | Fast dev server; required by the stack spec |
| Tailwind CSS v4 | Styling | Utility CSS, no design system to build under deadline |
| Recharts | Charts | React-native charting; minimal glue for trend lines |
| FastAPI | API | Typed, auto-documented (`/docs`), minimal boilerplate |
| Uvicorn | Server | Standard ASGI server for FastAPI |
| Pydantic + pydantic-settings | Validation + config | Enforces the data contract; keeps secrets in env |
| pandas / numpy | Analytics | Aggregation and trend maths over CSV |
| pytest + httpx2 | Tests | Validates the API and the data contract |

### Deliberately not used

**PostgreSQL / MongoDB / Redis** — dataset is small and read-only; in-memory
pandas is faster to build and to deploy.
**Docker / Kubernetes** — two processes; a platform build command is enough.
**Celery / queues** — all computation is sub-second and synchronous.
**Redux / Zustand** — server data plus local state; no global store needed.
**React Router** — MVP is a single page with sections. Add only if navigation
genuinely appears.
**Axios** — native `fetch` covers it.
**scikit-learn** — deferred to Stage 6, and only if a moving-average/linear-trend
baseline proves insufficient. Listed but commented in `requirements.txt`.

## Deployment shape (Stage 9)

Static frontend build (`frontend/dist`) on any static host; FastAPI on any
Python host, started with `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`.
The committed CSVs ship with the repo, so there is no data provisioning step.
Set `VITE_API_BASE_URL` at build time to point the frontend at the deployed API.
