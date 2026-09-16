# Stage 9 — GitHub Push + Production Deployment

**Complete and verified.** The production URL serves the MerchantAI dashboard,
the API works from the same origin, and every result below was checked against
the live site.

| | |
| --- | --- |
| **Production URL** | https://merchant-growth-ai.vercel.app |
| **Repository** | https://github.com/manthandhanraj/MerchantAI |
| **Branch** | `main` |
| **Vercel project** | `merchant-growth-ai` (`prj_NJUJTobUto8GyqbRurBNNHh09YQ9`) |
| **Deployment ID** | `dpl_H6LwzzLHmVLbnTAMV5UWKHn3hguF` |
| **Deployment URL** | https://merchant-growth-mj95jvtjc-personal-9b7b.vercel.app |

## The problem

The previous deployment returned FastAPI JSON at the root:

```
GET /             200  application/json   {"app":"MerchantAI","docs":"/docs",...}
GET /api/health   404                     <- the API was broken too
GET /index.html   404                     <- no frontend deployed at all
```

## Root causes — two, not one

Diagnosed from `vercel project inspect` and the live responses, not guessed.

**1. The project's Framework Preset was `FastAPI`.**
Vercel auto-detected the preset from `api/index.py` + `requirements.txt`. That
preset makes the Python function a **catch-all at `/`** and ignores the static
output directory entirely — which is why `/` returned JSON and `/index.html`
404'd. The `buildCommand` and `outputDirectory` in `vercel.json` were being
overridden by the preset.

**2. The `rewrites` rule was destroying the API path.**
`{"source": "/api/(.*)", "destination": "/api/index"}` **replaces** the path, so
FastAPI received `/api/index` — a route that does not exist — and returned 404
for every real endpoint. This was the risk flagged as unverifiable in the
previous Stage 9 report; deploying confirmed it.

**3. (found during the fix) `@vercel/static-build` prefixes its output.**
After switching to an explicit build config, the frontend built correctly but
landed at `/frontend/index.html` and `/frontend/assets/…`, while Vite's HTML
references absolute `/assets/…`. Root was 404 until the asset route was mapped.

## The fix

`vercel.json` now uses an explicit build + route configuration:

```json
{
  "version": 2,
  "builds": [
    { "src": "frontend/package.json", "use": "@vercel/static-build",
      "config": { "distDir": "dist" } },
    { "src": "api/index.py", "use": "@vercel/python",
      "config": { "includeFiles": "{backend/**,data/raw/**}" } }
  ],
  "routes": [
    { "src": "/api/(.*)",    "dest": "/api/index.py" },
    { "src": "/assets/(.*)", "dest": "/frontend/assets/$1" },
    { "handle": "filesystem" },
    { "src": "/(.*)",        "dest": "/frontend/index.html" }
  ]
}
```

Why each part matters:

- **`builds` overrides the framework preset.** The build log confirms it:
  *"Due to `builds` existing in your configuration file, the Build and
  Development Settings defined in your Project Settings will not apply."*
  That is what stops FastAPI being a catch-all at `/`.
- **`routes` preserve the request path.** Unlike `rewrites`, a legacy route's
  `dest` passes the original URL to the function, so `/api/health` reaches
  FastAPI's `/api/health`.
- **`/assets/(.*)` → `/frontend/assets/$1`** bridges Vite's absolute asset
  paths to where `@vercel/static-build` actually placed them.
- **`handle: filesystem` then a catch-all to `index.html`** serves real files
  first and sends anything else to the SPA.

**No application code was changed.** No route, service, metric, business rule,
schema or component was touched. `api/index.py` still re-exports the existing
app unmodified.

## Deployment architecture

One Vercel project, two build outputs, one origin:

```
merchant-growth-ai.vercel.app
  ├── /            -> frontend/index.html   (static, Vite build)
  ├── /assets/*    -> frontend/assets/*     (static)
  └── /api/*       -> api/index.py          (Python serverless, FastAPI)
```

Same origin means the frontend keeps its relative `/api/...` paths: **no
production API URL to configure and no CORS to arrange.**

## Verification — all performed against the live site

### Root and assets

| Request | Result |
| --- | --- |
| `GET /` | **200 `text/html`** — the React document, `<title>MerchantAI</title>` |
| `GET /assets/index-CTe2j2zB.js` | 200, 35,328 bytes |
| `GET /assets/index-Bu2OAkqt.css` | 200, 18,900 bytes |
| `GET /assets/charts-Ccr9vapa.js` | 200, 557,652 bytes |

The root no longer returns `{"app":"MerchantAI",...}`.

### API — every existing endpoint, live

All returned **200**:

`/api/health` · `/api/merchants` · `/api/dataset/summary` ·
`/api/dataset/validation` · `/api/dashboard` · `/api/insights` ·
`/api/recommendations` · `/api/action-plan` · `/api/forecast` ·
`/api/assistant/status` · `POST /api/assistant/ask`

No endpoint was invented; this list was taken from the application's own router.

### Browser verification (1280×900)

| Check | Result |
| --- | --- |
| Dashboard renders | **PASS** — `#root` populated, `<h1>MerchantAI</h1>` |
| Sections | Trends → AI insights → Action plan → Revenue forecast → Assistant |
| KPI cards | ₹34,64,429 · 2,362 · 2,111 · ₹10,41,631 · ₹1,467 |
| Merchant selector | Populated from the API: M001–M004 with product counts |
| Charts | 10 Recharts surfaces drawn |
| Insights | 6 finding cards |
| Action plan | 8 ranked action cards |
| Forecast | "Falling trend" badge, chart rendered |
| Assistant | Panel present; answered a starter question |
| Blank screen / JSON at root | **None** |
| Panel error boundaries triggered | **0** |
| Horizontal overflow | **None** |
| **Console errors** | **None** |

### Network — no localhost, no CORS

Every request the page made, captured live:

```
GET https://merchant-growth-ai.vercel.app/                     200
GET https://merchant-growth-ai.vercel.app/assets/*.js|.css     200 (x3)
GET https://merchant-growth-ai.vercel.app/api/merchants        200
GET https://merchant-growth-ai.vercel.app/api/assistant/status 200
GET https://merchant-growth-ai.vercel.app/api/dashboard?...    200
GET https://merchant-growth-ai.vercel.app/api/action-plan?...  200
GET https://merchant-growth-ai.vercel.app/api/insights?...     200
GET https://merchant-growth-ai.vercel.app/api/forecast?...     200
```

**All same-origin. Zero `localhost`, zero `127.0.0.1`, zero CORS errors.**

### Interaction, live

| Action | Result |
| --- | --- |
| Initial (M001, 30d) | ₹34,64,429 · "Smart Watch grew 34.7%" · "Give Smart Watch more room to grow" |
| Switch to M003 | ₹1,78,893 · "Cold Coffee declined 25.7% versus the previous 30 days" |
| "All" preset (180d) | ₹13,35,231 · "Cold Coffee declined 30.4% versus the first half of the period" |
| Ask the assistant | Answered from the action plan |
| Error boundaries during all of it | 0 |

**₹13,35,231 matches the M003 total documented in Stage 2 exactly**, confirming
the deployed function is reading the real committed dataset — and the
`within_period` comparison fallback works in production.

## Tests

| | |
| --- | --- |
| Backend | **507 passed** (1 upstream warning) |
| Frontend | **73 passed** |
| Build | **PASS** — 1.55 s |

No regression from Stage 8.

## Files changed for Stage 9

**Modified**
- `vercel.json` — the routing fix described above
- `.gitignore` — `.vercel` (added by the Vercel CLI) and deck build artifacts

**Created earlier in Stage 9 and unchanged**
- `api/index.py`, `api/requirements.txt`, `.vercelignore`, `.gitattributes`

**Not committed, not deleted:** `.codex-build/`, `.codex-finalizer/`,
`.chart-data-*/` and `output/` appeared in the working tree from separate
slide-deck tooling (~28 MB of PPTX files, rendered slides and Chrome profiles).
They are not part of this application, so they were added to `.gitignore` and
**left untouched on disk** rather than committed or removed.

## Limitations

- **Cold starts reload the dataset.** ~0.65 s per cold serverless instance
  (measured locally: 0.58 s import + 0.05 s load and validate). The in-memory
  cache is per-instance, so concurrent instances each hold a copy. Fine at this
  data size; it would not suit a large dataset.
- **The assistant is offline by default.** `LLM_ENABLED=false` in production and
  no key is set, so answers are composed from the merchant's own computed data.
  **No live LLM call has ever been made**, so nothing is claimed about model
  output quality.
- **GitHub→Vercel auto-deploy is not wired up.** Deployments are currently made
  with `vercel --prod`. Connecting the repository is a one-time action in the
  Vercel dashboard (Settings → Git) or `vercel git connect`.
- All Stage 1–8 data caveats carry over: synthetic data, gross profit excludes
  overheads, customer counts are visits over multi-day windows, inventory is
  inferred, the data shows what changed rather than why, and the forecast
  reports measured error (~20–53% MAPE) with no confidence interval.

## Status

**STAGE 9 COMPLETE** — the production URL opens the MerchantAI dashboard, and
the API works.
