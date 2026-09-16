# Stage 9 — GitHub Push + Deployment

**GitHub push: complete and independently verified.**
**Vercel deployment: blocked on authentication that only the account owner can provide.**

No live URL is claimed below, because none was created. The deployment
configuration is written, committed and validated as far as it can be without
deploying.

## 1–3. Repository

| | |
| --- | --- |
| Repository | https://github.com/manthandhanraj/MerchantAI |
| Branch | `main` |
| Commit | `11667470995735204c36bed009d6a8e6b82ba17e` |
| Contents | 108 files, 27,047 insertions |
| Visibility | Public |

### Verified, not assumed

The push was confirmed four independent ways:

1. `git ls-remote origin refs/heads/main` returns the same SHA as local `HEAD`.
2. The GitHub REST API reports that commit on `main`, authored by
   `manthandhanraj`, 108 files, `pushed_at 2026-09-16T18:01:58Z`.
3. Raw fetches of `README.md`, `vercel.json`, `api/index.py`, `runner.py`,
   `backend/app/main.py`, `data/raw/merchant_sales.csv` and `.gitignore` all
   return HTTP 200 with non-zero size.
4. `data/raw/merchant_sales.csv` downloaded from GitHub is **byte-identical** to
   the local file (298,735 bytes, 0 CRLF, 4,815 LF).

### Pre-push safety

The target repository was empty (`git ls-remote --heads` returned **0 refs**,
API size 0 KB), so nothing was overwritten and **no force push was used or
needed**. History starts clean at this commit.

## 4–6. Deployment status

**Not deployed.** The Vercel CLI (v59.19.0) installs and runs, but reports:

```json
{ "loggedIn": false, "status": "action_required", "reason": "login_required",
  "userActionRequired": true, "retryable": false }
```

`vercel build` fails the same way. There is no `VERCEL_TOKEN`, no `~/.vercel`
config and no `.vercel/` directory on this machine — checked before attempting
anything. Authentication requires an interactive browser login or a token that
only the account owner can issue.

### To deploy

Either:

```bash
npx vercel login      # interactive browser auth
npx vercel --prod
```

Or import `manthandhanraj/MerchantAI` at vercel.com/new — `vercel.json` is
committed and will be picked up automatically.

**First check after deploying:** `GET /api/health`. It returns
`sales_data_present` and `llm_enabled`, which confirms in one request that the
function booted, found the dataset, and left the model disabled.

## 7. Deployment architecture

**One Vercel project, not two.** The Vite build is served as static assets and
the existing FastAPI app runs as a single Python serverless function under
`/api`.

This was chosen on evidence, not convention:

- **The Python dependencies fit.** Measured at **~114 MB** unzipped
  (pandas 68 MB, numpy 34 MB, the rest small) against Vercel's 250 MB function
  limit. Had this not fit, a separate backend host would have been necessary.
- **Cold start is acceptable.** Measured over three fresh processes:
  ~0.58 s import + ~0.05 s for the first request (which loads *and validates*
  the 4,814-row dataset), then ~12 ms warm.
- **Same origin removes a whole class of production bugs.** The frontend already
  used relative `/api/...` paths, so there is **no production API URL to
  configure and no CORS to arrange**. A two-deployment split would have
  introduced both for no benefit.

A second deployment was therefore deliberately *not* created.

## 8. Tests

| | |
| --- | --- |
| Backend | **507 passed** (1 upstream warning) |
| Frontend | **73 passed** |
| Total | **580** |
| Build | **PASS** — 1.59 s |
| `runner.py --check` | **PASS** |

No regression from Stage 8.

## 9. Live verification

**Not performed — there is no live deployment to verify.** Claiming otherwise
would be fabrication.

What *was* verified, locally and against the committed configuration:

| Check | Result | How |
| --- | --- | --- |
| API through the Vercel entry point | **11/11 endpoints 200** | `api/index.py` served via TestClient |
| API inside a **simulated serverless bundle** | **9/9 endpoints 200** | Copied only `api/` + `includeFiles` into a temp dir, booted there |
| Dataset resolves inside that bundle | PASS | `sales_data_present: true` |
| LLM disabled in that bundle | PASS | `llm_enabled: false` |
| Bundle excludes dev files | PASS | no `runner.py`, `tests/`, `.venv` present |
| `buildCommand` from `vercel.json` | PASS | run verbatim; produced `frontend/dist` |
| `includeFiles` globs | PASS | `backend/**` → 68 paths, `data/raw/**` → 3 |
| No production localhost dependency | PASS | **0 occurrences of `localhost` in the built bundle**; none anywhere in `frontend/src/` |

The simulated bundle is the strongest evidence available without deploying: it
proves the function can boot, find its data and serve every endpoint using only
the files `vercel.json` ships.

## 10. Environment variables

**None are required.** The synthetic dataset ships with the function, and the
assistant answers from it offline.

Optional, names only:

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_ENABLED` | `false` | Production-safe default, preserved |
| `LLM_API_KEY` | empty | Only read when `LLM_ENABLED=true`; set as a Vercel secret, never committed |
| `LLM_PROVIDER` | `anthropic` | |
| `LLM_MODEL` | `claude-sonnet-5` | |
| `CORS_ORIGINS` | localhost | Only needed if the API is ever split to another origin |
| `API_HOST`, `API_PORT` | `127.0.0.1`, `8000` | Local only; Vercel manages the function's address |

No secret value appears in this document, the repository, or any log.

## 11. Files changed for Stage 9

**Created**

- `vercel.json` — build command, static output, `/api/(.*)` rewrite, function limits
- `api/index.py` — serverless entry; re-exports the existing app unchanged
- `api/requirements.txt` — runtime-only deps (no pytest in the function bundle)
- `.vercelignore` — keeps tests, docs, virtualenvs out of the bundle
- `.gitattributes` — forces LF (see §12)
- `docs/STAGE_9_COMPLETION.md`

**Modified**

- `.gitignore` — added `.env.*` with `!.env.example`, `build/`, `.vercel/`, `*.p12`, `*.pfx`, `credentials.json`
- `README.md` — Deployment section: architecture, deploy steps, production variables

**No application code was changed.** No route, service, metric, business rule or
component was touched. The deployed API is the same one `runner.py` serves.

## 12. Problems encountered

**1. Line endings would have broken dataset reproducibility.**
Staging produced CRLF warnings on all 80+ text files. Stage 2 specifies LF-only
CSVs and byte-identical regeneration; a Windows clone would have received CRLF,
and `python data/generate_dataset.py` would then have reported every one of
4,814 lines as changed. Fixed with `.gitattributes` (`* text=auto eol=lf`).
Verified: the CSV on GitHub has **0 CRLF, 4,815 LF, byte-identical to local**.

**2. `npm install` reintroduced CRLF into `package-lock.json`.**
Running the build command to validate it left the working tree dirty. `git diff`
showed **no content change** — purely line endings. Resolved with
`git add --renormalize`; the tree is now clean with no staged difference.

**3. Vercel authentication is unavailable.**
Established before attempting anything: no `VERCEL_TOKEN`, no `~/.vercel`, no
`.vercel/`. The CLI confirms `retryable: false, userActionRequired: true`. This
is not a bug and there is no workaround available to an automated session — a
Vercel login is a human action.

No application bugs were found. Nothing was hidden.

## 13. Remaining limitations

- **The deployment is unverified because it does not exist.** The configuration
  is reasoned and locally simulated, but Vercel's routing of
  `/api/(.*)` → `/api/index` into the ASGI scope is the one aspect that cannot
  be proven without deploying. If the first `/api/health` request 404s after
  deploying, that rewrite is the place to look.
- **Serverless cold starts reload the dataset.** ~0.65 s per cold instance. The
  in-memory cache is per-instance, so concurrent instances each hold their own
  copy. Fine at this data size; it would not scale to a large dataset.
- **`runner.py` is a development tool**, not a production process manager.
  Vercel invokes the function directly and ignores it.
- All Stage 1–8 limitations carry over unchanged: synthetic data, gross profit
  excludes overheads, customer counts are visits over multi-day windows,
  inventory is inferred, the data shows what changed rather than why, forecast
  MAPE ~20–53% with no confidence interval, and **no live LLM call has ever been
  made** — nothing is claimed about real model output.

## 14. Status

**Stage 9 is partially complete.**

- ✅ GitHub push — done and independently verified
- ✅ Deployment configuration — written, committed, locally validated
- ⏸️ Vercel deployment — **blocked on a login only the account owner can perform**

Stage 9 will be complete once `vercel login && vercel --prod` has been run and
the resulting URL verified.
