# Setup & Development

Prerequisites: **Python 3.10+** and **Node.js 18+**.
Verified on Python 3.12.10 and Node 24.18.1 (Windows).

## First-time setup

### 1. Backend

From the project root:

```bash
python -m venv .venv
```

Activate it — Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux (and Git Bash on Windows):

```bash
source .venv/bin/activate
```

Then install:

```bash
pip install -r requirements.txt
```

### 2. Environment file

```bash
cp .env.example .env
```

On Windows PowerShell use `copy .env.example .env`.

The defaults work as-is. You do **not** need an LLM key until Stage 6 — the app
runs fully with `LLM_ENABLED=false`.

### 3. Dataset

The generated CSVs are committed, so this is only needed if you want to
regenerate them:

```bash
python data/generate_dataset.py --summary
```

Deterministic — the same seed reproduces the same files byte for byte. See
[DATA_PIPELINE.md](DATA_PIPELINE.md).

### 4. Frontend

```bash
cd frontend
npm install
```

## Running the app

Two terminals, both from the project root.

**Terminal 1 — API** (http://127.0.0.1:8000, docs at `/docs`):

```bash
uvicorn backend.app.main:app --reload
```

**Terminal 2 — frontend** (http://localhost:5173):

```bash
cd frontend && npm run dev
```

Open http://localhost:5173. You should see the MerchantAI card reporting
`API status: ok`. If it reports the API is unreachable, terminal 1 is not running.

The Vite dev server proxies `/api/*` to port 8000, so there is no CORS setup
and no frontend env file needed in development.

## Testing

From the project root, with the venv active:

```bash
pytest
```

This covers the API endpoints, the dataset contract, validation rules and the
metric computations.

Frontend tests (Vitest + Testing Library) run separately:

```bash
cd frontend && npm test
```

## Production build

```bash
cd frontend && npm run build
```

Outputs static files to `frontend/dist/`.

## Things that will confuse you otherwise

**Tailwind v4 has no config files.** There is deliberately no `tailwind.config.js`
and no `postcss.config.js`. Tailwind is wired in as a Vite plugin in
`vite.config.js`, and theme tokens live in `@theme { ... }` inside
`src/index.css`. If you follow a v3 tutorial and add those config files, you
will break the build. Content paths are auto-detected — there is nothing to configure.

**Run uvicorn from the project root**, not from `backend/`. The import path is
`backend.app.main:app` and it depends on the root being the working directory.

**npm may warn about esbuild install scripts.** npm 11 gates postinstall scripts.
The build works regardless; if it ever fails on a fresh machine, run
`npm approve-scripts esbuild`.

**`httpx2`, not `httpx`.** Starlette's TestClient now deprecates plain `httpx`.
`httpx2` is the same author's successor package and keeps the test run clean.

## Adding a dependency

Don't, unless you can state the reason in one line. If you can:

- Python → add to `requirements.txt` **with a trailing comment explaining why**
- Frontend → `npm install <pkg>` from `frontend/`

See the "Deliberately not used" list in [ARCHITECTURE.md](ARCHITECTURE.md) before
reaching for a state manager, a router, an HTTP client or a database.
