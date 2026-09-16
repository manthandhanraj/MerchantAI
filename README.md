# MerchantAI

An AI business copilot for merchants — built for the **Merchant Growth AI** track.

MerchantAI reads a merchant's business data and answers the three questions a
small merchant actually has: *what is happening*, *why*, and *what should I do
today*. It is a business partner, not a dashboard.

> **All data is synthetic.** MerchantAI uses generated demo data only. It does
> not use, and does not claim access to, private Paytm data or APIs.

## What it does

| | Capability |
| --- | --- |
| **Dashboard** | Revenue, orders, customers, profit, average order value, sales trends |
| **Business intelligence** | Revenue analysis, trends, product performance, customer insights, business health |
| **Growth intelligence** | Growth, product, retention and inventory recommendations |
| **Forecasting** | Short-term revenue/sales forecast |
| **AI assistant** | Plain-language Q&A grounded in the merchant's own numbers |
| **Action plan** | A prioritised High / Medium / Low list of what to do next |

The assistant is grounded by design: every number it quotes is computed in
Python by the same analytics layer that feeds the dashboard. The LLM explains
and phrases — it never calculates. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Tech stack

**Frontend** — React, Vite, Tailwind CSS v4, Recharts
**Backend** — Python, FastAPI, Uvicorn, Pydantic
**Analytics** — pandas, NumPy
**Storage** — CSV (no database; the dataset is small and read-only)

Every dependency has a stated reason, and the notable *exclusions* are justified
too, in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quick start

Prerequisites: Python 3.10+, Node.js 18+.

**1. Install once**

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

**2. Run everything with one command**

```bash
python runner.py
```

That starts the API and the web app together, streams both logs to the terminal,
and stops both cleanly on **Ctrl+C**.

| | |
| --- | --- |
| **Web app** | http://localhost:5173 — open this |
| **API** | http://127.0.0.1:8000 |
| **API docs** | http://127.0.0.1:8000/docs |

`python runner.py --check` verifies your setup without starting anything.

The runner finds the project's `.venv` itself, so plain `python runner.py` works
even when the virtualenv is not active. It never installs anything: if something
is missing it tells you the exact command to run. If a port is already in use it
leaves that service alone rather than starting a duplicate.

### Environment

Copy `.env.example` to `.env` if you want to change anything — the defaults work
as they are:

```bash
cp .env.example .env
```

The synthetic dataset is committed, so there is nothing to generate. To rebuild
it (deterministic, identical every time):

```bash
python data/generate_dataset.py --summary
```

**No API key is needed.** The AI assistant answers from the merchant's own
computed analytics, offline. `LLM_ENABLED` defaults to `false`; set it to `true`
with an `LLM_API_KEY` only if you want a language model to phrase those answers
instead. Either way every figure comes from the data, never from the model.

### Running the two services separately

Useful when you want them in their own terminals:

```bash
uvicorn backend.app.main:app --reload
```

```bash
cd frontend && npm run dev
```

## Project structure

```
MerchantAI/
├── backend/
│   └── app/
│       ├── main.py          # FastAPI entrypoint
│       ├── config.py        # env-based settings
│       ├── routes/          # thin HTTP layer
│       ├── services/        # data loading, validation, metrics
│       ├── models/          # dataset contract + API models
│       └── utils/           # small shared helpers
├── frontend/
│   └── src/
│       ├── App.jsx
│       ├── components/      # KPI cards, charts, selectors, states
│       ├── pages/           # DashboardPage
│       ├── utils/           # currency/date/percent formatting
│       └── services/api.js  # every API call lives here
├── data/
│   ├── generate_dataset.py  # deterministic synthetic data generator
│   ├── raw/                 # generated synthetic dataset
│   ├── processed/           # derived outputs, if needed
│   └── sample/              # tiny schema-validation extract
├── ml/                      # modelling workspace
├── tests/
├── docs/
├── runner.py                # starts the whole app: python runner.py
├── .env.example
├── requirements.txt
└── README.md
```

## Deployment

The project deploys to **Vercel as a single project**: the Vite build is served
as static assets, and the FastAPI app runs as one Python serverless function
under `/api`. Because both live on the same origin, the frontend keeps using
relative `/api/...` paths — there is no production API URL to configure.

| File | Purpose |
| --- | --- |
| `vercel.json` | Build command, static output directory, `/api/(.*)` rewrite, function limits |
| `api/index.py` | Serverless entry point; re-exports the existing FastAPI app unchanged |
| `api/requirements.txt` | Runtime-only dependencies (no pytest in the function bundle) |
| `.vercelignore` | Keeps tests, docs and virtualenvs out of the bundle |

**To deploy** (requires a Vercel account — the CLI needs an interactive login):

```bash
npm i -g vercel
vercel login
vercel --prod
```

Or import `manthandhanraj/MerchantAI` at vercel.com/new, which picks up
`vercel.json` automatically.

After deploying, check `/api/health` first — it confirms the function booted and
found the dataset.

### Production environment variables

None are required. The committed synthetic dataset ships with the function, and
the assistant answers from that data offline. Optional:

| Variable | Default | Effect |
| --- | --- | --- |
| `LLM_ENABLED` | `false` | Leave as-is unless you want a model to phrase answers |
| `LLM_API_KEY` | empty | Only read when `LLM_ENABLED=true`; set it as a Vercel secret, never in the repo |
| `LLM_MODEL`, `LLM_PROVIDER` | `claude-sonnet-5`, `anthropic` | Provider selection |
| `CORS_ORIGINS` | localhost | Only needed if the API is ever hosted on a different origin from the frontend |

`runner.py` is a development convenience, not a production process manager —
Vercel runs the function directly.

## Documentation

| Document | Contents |
| --- | --- |
| [MVP_SCOPE.md](docs/MVP_SCOPE.md) | Problem, target user, locked scope, what's excluded |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, data flow, API surface, stack rationale |
| [DATA_SCHEMA.md](docs/DATA_SCHEMA.md) | Dataset columns, invariants, derived metrics |
| [DATA_PIPELINE.md](docs/DATA_PIPELINE.md) | Generation, validation, loading and metrics |
| [USER_FLOW.md](docs/USER_FLOW.md) | Screen flow and states to handle |
| [SETUP.md](docs/SETUP.md) | Setup, running, testing, pitfalls |
| [CONVENTIONS.md](docs/CONVENTIONS.md) | Naming and code conventions |
| [STAGE_1_COMPLETION.md](docs/STAGE_1_COMPLETION.md) | Stage 1 decisions and sign-off |
| [STAGE_2_COMPLETION.md](docs/STAGE_2_COMPLETION.md) | Stage 2 decisions and sign-off |
| [STAGE_3_COMPLETION.md](docs/STAGE_3_COMPLETION.md) | Stage 3 decisions and sign-off |
| [STAGE_4_COMPLETION.md](docs/STAGE_4_COMPLETION.md) | Stage 4 decisions and sign-off |
| [STAGE_5_COMPLETION.md](docs/STAGE_5_COMPLETION.md) | Stage 5 decisions and sign-off |
| [STAGE_6_COMPLETION.md](docs/STAGE_6_COMPLETION.md) | Stage 6 decisions and sign-off |
| [STAGE_7_COMPLETION.md](docs/STAGE_7_COMPLETION.md) | Stage 7 decisions and sign-off |
| [STAGE_8_COMPLETION.md](docs/STAGE_8_COMPLETION.md) | Stage 8 audit, fixes and sign-off |

## Development roadmap

| Stage | Scope | Status |
| --- | --- | --- |
| 1 | Planning & project foundation | ✅ Complete |
| 2 | Dataset & data processing | ✅ Complete |
| 3 | Merchant dashboard | ✅ Complete |
| 4 | AI business analysis | ✅ Complete |
| 5 | Growth recommendation engine | ✅ Complete |
| 6 | Forecasting + AI assistant | ✅ Complete |
| 7 | Full integration → working MVP | ✅ Complete |
| 8 | Testing, debugging, optimisation, cleanup | ✅ Complete |
| 9 | GitHub + deployment | Next |
| 10 | Report + presentation | |

## Testing

```bash
pytest
```

```bash
cd frontend && npm test
```

## Stopping the app

Press **Ctrl+C** in the terminal running `python runner.py`. It stops the API and
the web app, including the Node process the dev server spawns.

## Security

Secrets are read from the environment and never hard-coded. `.env` is
git-ignored; `.env.example` holds placeholders only. Do not commit API keys.
