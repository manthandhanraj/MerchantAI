# Supabase setup checklist

**This is optional.** Without Supabase, MerchantAI uses its built-in accounts:
sign-up, sign-in, uploads, analyses and reports all work and are saved under
`data/local/`. Connect Supabase when you deploy publicly — it adds email
confirmation, reset emails and storage that survives serverless restarts.

Everything needed to connect a **new** Supabase project, in order. Nothing else
in the codebase has to be read to follow it.

---

## 1. Create the project

1. Go to <https://supabase.com/dashboard> and create a project.
2. Wait for it to finish provisioning.
3. Open **Project Settings → API** and copy:

| Value | Used as |
| --- | --- |
| Project URL | `SUPABASE_URL` and `VITE_SUPABASE_URL` |
| `anon` / publishable key | `SUPABASE_ANON_KEY` and `VITE_SUPABASE_ANON_KEY` |

4. Open **Project Settings → API → JWT Settings**.
   - If a **JWT Secret** is shown, copy it into `SUPABASE_JWT_SECRET`.
   - If the project uses **asymmetric keys** (no shared secret), leave
     `SUPABASE_JWT_SECRET` empty. The backend verifies through the project's
     published JWKS instead.

> **Never copy the `service_role` key into any `VITE_` variable or any file
> under `frontend/`.** It bypasses Row Level Security. This app does not need
> it; the variable exists only for future administrative use.

---

## 2. Apply the migrations

Three SQL files, applied in order:

```
supabase/migrations/0001_core_schema.sql
supabase/migrations/0002_row_level_security.sql
supabase/migrations/0003_storage.sql
```

**Option A — Supabase CLI** (preferred):

```bash
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

**Option B — SQL editor:** open **SQL Editor** in the dashboard, paste each
file's contents in order, and run them one at a time.

### What they create

| Migration | Creates |
| --- | --- |
| `0001` | `profiles`, `merchants`, `uploads`, `analysis_runs`, `reports`, indexes, foreign keys, `updated_at` triggers, a sign-up trigger that creates a profile, and a trigger that forces `owner_id` to match the merchant's real owner |
| `0002` | Row Level Security enabled and **forced** on all five tables, with per-operation policies; `anon` is revoked from every private table |
| `0003` | Private `merchant-data` and `merchant-reports` buckets, plus storage policies scoping every object to its owner's folder |

### Verify

In the SQL editor:

```sql
-- Every table must report rowsecurity = true
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in ('profiles','merchants','uploads','analysis_runs','reports');

-- Expect 17 policies across the five tables
select tablename, count(*) from pg_policies
where schemaname = 'public' group by tablename order by tablename;

-- Both buckets must be private
select id, public from storage.buckets
where id in ('merchant-data','merchant-reports');
```

If any bucket shows `public = true`, stop and re-run `0003`.

---

## 3. Configure authentication

**Authentication → Providers → Email**

- Enable **Email**.
- Decide on **Confirm email**. With it on, a new account must open the emailed
  link before it can sign in; the sign-up screen already handles that case.

**Authentication → URL Configuration**

- **Site URL**: your deployed origin, e.g. `https://merchant-growth-ai.vercel.app`
- **Redirect URLs**: add every origin the app is opened from —

```
http://localhost:5173/**
https://<your-production-domain>/**
https://<your-vercel-preview-domain>/**
```

The password-reset link returns to `/reset-password`, and the sign-up
confirmation link returns to `/app`. Both are covered by the wildcards above.

---

## 4. Local environment

**Backend** — copy `.env.example` to `.env` at the project root and fill in:

```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>
SUPABASE_JWT_SECRET=<jwt secret, or leave empty for asymmetric projects>
```

**Frontend** — copy `frontend/.env.example` to `frontend/.env.local`:

```
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon key>
```

Install the new backend dependencies and run:

```bash
pip install -r requirements.txt
python runner.py
```

Confirm the wiring:

```bash
curl http://127.0.0.1:8000/api/health
```

`workspace_enabled` must be `true`.

---

## 5. Vercel environment

**Project → Settings → Environment Variables.** The two columns matter: Vite
inlines `VITE_*` at build time, while the Python function reads the rest at
runtime.

| Variable | Needed at | Value |
| --- | --- | --- |
| `VITE_SUPABASE_URL` | **Build** | Project URL |
| `VITE_SUPABASE_ANON_KEY` | **Build** | anon key |
| `SUPABASE_URL` | **Runtime** | Project URL |
| `SUPABASE_ANON_KEY` | **Runtime** | anon key |
| `SUPABASE_JWT_SECRET` | **Runtime** | JWT secret, if the project has one |
| `APP_ENV` | Runtime | `production` |
| `DEMO_USER_ID` | Runtime | The id printed by the seeder |
| `VITE_DEMO_EMAIL` | **Build** | `demo@merchantai.app` |
| `VITE_DEMO_PASSWORD` | **Build** | The demo password |

Set all of them for **Production**, **Preview** and **Development** so preview
deployments work too.

A change to a `VITE_*` variable only takes effect on the **next build** —
redeploy after editing one.

Optional, only if you enable model-phrased answers:

```
LLM_ENABLED=true
LLM_API_KEY=<secret>
```

---

## 6. Seed the demo account

The login page can show a working demo. It is a **real Supabase account** that
signs in through the normal flow and opens a seeded, synthetic, read-only
workspace.

Set the password you want in your **backend** `.env`:

```
DEMO_PASSWORD=<choose one, at least 8 characters>
```

Then run the seeder once:

```bash
python scripts/seed_demo.py
```

It creates the auth user, a merchant, two uploads taken from the committed
synthetic dataset, one completed analysis and one PDF report. Running it again
updates the same rows rather than creating a second demo — migration `0004`
enforces that with partial unique indexes.

Useful flags:

```bash
python scripts/seed_demo.py --reset-password   # if someone changed it
python scripts/seed_demo.py --force            # recompute analysis and report
```

The script prints the demo user's id when it finishes. Put it in the **backend**
environment so the workspace becomes read-only:

```
DEMO_USER_ID=<the id the script printed>
```

And put the credentials in the **frontend** environment so the login page shows
them:

```
VITE_DEMO_EMAIL=demo@merchantai.app
VITE_DEMO_PASSWORD=<the same password>
```

> `SUPABASE_SERVICE_ROLE_KEY` is required **only by this script** and only on
> your machine or a server. It bypasses Row Level Security. No route in the
> application uses it, and it must never appear in a `VITE_` variable.

Once `DEMO_USER_ID` is set, the backend returns **403** for every mutating call
from that account — creating or deleting a merchant, uploading, running an
analysis, deleting a report or changing the profile. Reads and report
generation stay available, because the demo journey needs them.

**Limitation worth knowing:** Supabase has no server-side way to stop an account
changing its own password. The demo's password form is hidden in the interface
and the account has nothing sensitive in it, but if someone changes it anyway,
`--reset-password` puts it back.

---

## 7. End-to-end check

**Demo journey**

1. Open the deployed URL. It redirects to `/login`.
2. The demo credentials appear below the form.
3. Click **Try demo account**. The fields fill and a real sign-in runs.
4. The workspace opens with a **Demo mode** banner and a populated dashboard.
5. Insights, forecast, recommendations and the action plan are all present.
6. **Generate report**, then download it from **Reports**.
7. Sign out.

**New-user journey**

1. From `/login`, click **Create new account**.
2. Register; confirm the email if confirmation is on.
3. Sign in. The workspace is empty — no demo data, no other user's data.
4. Create a business. You land straight on the upload wizard.
5. Download the sample template, or upload your own sales CSV.
6. Map the columns, review the preview, store it.
7. Upload a customer CSV.
8. Click **Analyse my business**. The dashboard fills.
9. Generate a PDF report and download it.
10. Sign out, sign back in — the merchant, analysis and reports are still there.
11. In the Supabase dashboard, check **Storage → merchant-data**: your file is
    under `<your-user-id>/<merchant-id>/<upload-id>/source.csv`.

### Prove the isolation

Create a **second** account in a private window, then:

```sql
-- Run as each user via the API, not the SQL editor (which bypasses RLS).
-- From account B, request account A's merchant id:
--   GET /api/my/merchants/<A's merchant id>
-- Expected: 404, not 403 and not the record.
```

---

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `/api/health` says `workspace_enabled: false` | `SUPABASE_URL` or `SUPABASE_ANON_KEY` missing from the **backend** environment |
| Sign-in works, API returns 401 | `SUPABASE_JWT_SECRET` missing or wrong for an HS256 project |
| API returns 503 mentioning PyJWT | `pip install -r requirements.txt` not run |
| Login screen says accounts are unavailable | `VITE_*` variables missing at **build** time; set them and redeploy |
| Upload succeeds, analysis 409s | Only one of the two files is uploaded; both are required |
| Reset link says it is invalid | The redirect URL is not in **Authentication → URL Configuration** |
| Login page shows no demo section | `VITE_DEMO_EMAIL` / `VITE_DEMO_PASSWORD` missing at **build** time |
| Demo sign-in fails | The seeder has not run, or the password does not match `VITE_DEMO_PASSWORD` |
| Demo visitor can delete things | `DEMO_USER_ID` is not set in the **backend** environment |
| Seeder says the service-role key is missing | `SUPABASE_SERVICE_ROLE_KEY` is not in your local `.env` |
