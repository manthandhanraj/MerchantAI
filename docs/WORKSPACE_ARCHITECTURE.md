# Private workspace — architecture

How MerchantAI serves a public synthetic demo and private per-user data from one
codebase, without duplicating a single line of the analytics.

For the step-by-step connection guide see [SUPABASE_SETUP.md](SUPABASE_SETUP.md).

---

## 1. Two modes, one engine

```
                      ┌──────────────────────────┐
  /demo  ────────────▶│  committed CSV dataset   │─┐
  (no account)        │  data/raw/*.csv          │ │
                      └──────────────────────────┘ │
                                                   ├──▶  dataset_from_frames()
                      ┌──────────────────────────┐ │           │
  /app   ────────────▶│  uploaded CSVs           │─┘           ▼
  (verified token)    │  Supabase Storage        │        Dataset (frozen)
                      └──────────────────────────┘             │
                                                               ▼
                       metrics → analysis → recommendations → action plan
                                    │                  │
                                 forecast          assistant
```

`Dataset` is the seam. `data_loader.dataset_from_frames()` is the **only** place
one is constructed, whichever source the rows came from, so every downstream
service is structurally unable to tell demo data from a merchant's own. Nothing
in `metrics.py`, `analysis.py`, `recommendations.py`, `action_plan.py`,
`forecasting.py` or `assistant.py` changed to support multi-user.

## 1a. Two account systems, one workspace

| | Built-in (default) | Supabase |
| --- | --- | --- |
| Chosen when | No Supabase keys, or `AUTH_MODE=local` | Keys set, or `AUTH_MODE=supabase` |
| Sign-up / sign-in | `POST /api/auth/signup`, `/api/auth/login` | Supabase Auth, from the browser |
| Passwords | scrypt (n=2^14, r=8, p=1), random 16-byte salt, constant-time compare | Supabase |
| Tokens | HS256, signed by the server; `iss=merchantai-local`, `aud=authenticated`, 7-day expiry | Supabase JWT (HS256 or JWKS) |
| Row storage | SQLite at `data/local/merchantai.db` | Postgres with Row Level Security |
| File storage | `data/local/storage/{bucket}/{user_id}/...` | Private Storage buckets |
| Signed downloads | `/api/files/{reference}` — HMAC-signed, 5-minute expiry | Storage signed URLs |
| Password reset | `scripts/reset_password.py` (no email service) | Reset email |

`services/local_store.py` implements the same seven methods as
`SupabaseClient`, so `services/workspace.py` — merchants, uploads, analyses,
reports — is identical code for both. What Supabase provides through RLS and
storage policies, `LocalStore` enforces itself:

- A store is built for **one verified user id** and every read, update and
  delete is confined to that user's rows. There is no method that reaches
  another owner's data.
- Inserts are refused unless the row belongs to the caller, and a child row
  (upload, analysis, report) is refused unless its merchant is the caller's —
  the equivalent of the `enforce_merchant_owner` trigger.
- Object paths must start with the caller's id, and are resolved and checked so
  `..` or a symlink cannot leave the owner's folder.

**Built-in accounts are not a mock.** Passwords never exist at rest, a failed
sign-in gives the same answer whether or not the email is registered (and takes
the same time — a dummy hash is checked for unknown emails), eight failures
inside fifteen minutes pause that email, and a token for a deleted account stops
working immediately rather than at expiry.

**Where they fall short of Supabase:** no email confirmation, no reset emails,
no refresh tokens (users sign in again after seven days), and one SQLite file
per server — fine for a single machine, not for many serverless instances. On
Vercel with no Supabase keys, data would live in `/tmp` and not survive a cold
start; `/api/health` then reports `persistent_storage: false` and every signed-in
page shows a warning. **Use Supabase for a public production deployment.**

### The demo account under built-in accounts

Created automatically the first time anyone signs in as the demo — no setup
step. It has a fixed id (`uuid5("merchantai:local-demo")`), so the backend
recognises it as read-only without configuration, and seeding is idempotent.
The login page asks `/api/auth/demo` for the credentials, so the password shown
is always the one that works.

## 2. Request path, private

```
Browser ──Authorization: Bearer <supabase access token>──▶ FastAPI
                                                             │
                                    services/auth.py ────────┤  verify signature,
                                    (PyJWT, HS256 or JWKS)   │  expiry, audience
                                                             ▼
                                                      AuthUser(id, token)
                                                             │
                              services/supabase_client.py ───┤  calls PostgREST and
                              (forwards the user's token)    │  Storage AS THAT USER
                                                             ▼
                                       Supabase evaluates that user's RLS policies
```

Two independent controls sit on every private path:

1. **The API's own ownership check** — `workspace.get_merchant()` and friends
   filter by `owner_id` and return 404 for anything else.
2. **Row Level Security** — the database refuses the row regardless.

The API never uses the service-role key on a user-facing path. Requests carry
the caller's own token, so if every check in the application were deleted, RLS
would still make cross-user access impossible.

### Why 404 and not 403

A merchant that belongs to someone else reads as *not found*. Answering 403
would confirm the id exists, which is information the caller should not have.

## 3. Authentication flow

| Step | Where | What happens |
| --- | --- | --- |
| Sign up | `supabase.auth.signUp` | Supabase stores the credential. A database trigger creates the `profiles` row, so the app never handles a "signed in but no profile" state. |
| Sign in | `supabase.auth.signInWithPassword` | Session persisted by the Supabase client and refreshed automatically. |
| Session | `AuthProvider` | Mirrors the client's session into React. Starts in a loading state so a signed-in user is never bounced to `/login` before the session is read. |
| API call | `services/privateApi.js` | Reads the **current** token at call time, so a background refresh is picked up immediately. |
| Forgot password | `resetPasswordForEmail` | Always reports the same thing, whether or not the address has an account. |
| Reset | `/reset-password` | The emailed link carries a recovery session in the URL fragment; the route sits outside both guards so it can consume it. |
| Sign out | `supabase.auth.signOut` | Clears the session and returns to `/login`. |

**No password is ever stored, hashed or transmitted by this application.** It
goes from the form to the Supabase client and nowhere else.

### Route guards

`RequireAuth` and `RequireAnon` are a convenience for the person using the app.
They are not a security control — the backend's token verification and the
database's RLS are. Deleting the guards would change what the UI shows, not what
data is reachable.

## 4. Database schema

Five tables. Every private one carries **both** `merchant_id` and `owner_id`.

```
auth.users
    │
    ├── profiles          (id = auth.users.id)
    │
    └── merchants         (owner_id)
            ├── uploads        (merchant_id, owner_id)
            ├── analysis_runs  (merchant_id, owner_id, upload_id)
            └── reports        (merchant_id, owner_id, analysis_run_id)
```

### Why `owner_id` is denormalised

Every RLS policy becomes a direct `auth.uid() = owner_id` comparison instead of
a sub-select through `merchants`. That is cheaper and much harder to get subtly
wrong. The redundancy is kept honest by a trigger — `enforce_merchant_owner()`
raises if `owner_id` does not match the merchant's real owner, so a bug in the
API cannot produce a row that RLS would then show to the wrong person.

### Key columns

| Table | Column | Purpose |
| --- | --- | --- |
| `merchants` | `archived_at` | Set instead of deleting when a merchant is archived |
| `uploads` | `status` | `pending` / `validating` / `ready` / `failed` |
| `uploads` | `validation_summary` | The accepted column mapping and row counts, reused when the file is read back |
| `uploads` | `idempotency_key` | Unique per merchant; a retried submission resolves to the same row |
| `analysis_runs` | `summary`, `daily`, `products`, `categories`, `inventory`, `insights`, `recommendations`, `action_plan`, `forecast` | The full computed result, stored once |
| `analysis_runs` | `idempotency_key` | Same protection against duplicate runs |
| `reports` | `storage_path` | Regenerated from verified ids before use, never trusted as stored |

### Why the analysis is stored, not recomputed

A dashboard read serves the stored `analysis_runs` row. The figures a merchant
sees are therefore exactly the figures that were computed and recorded, and a
report generated from that run weeks later cannot disagree with the screen.

## 5. Row Level Security

Enabled **and forced** on all five tables, so even the table owner cannot bypass
a policy during a later migration.

| Table | select | insert | update | delete |
| --- | --- | --- | --- | --- |
| `profiles` | own | own | own | — (cascades with the account) |
| `merchants` | own | own | own | own |
| `uploads` | own | own **and** the merchant is yours | own | own |
| `analysis_runs` | own | own **and** the merchant is yours | own | own |
| `reports` | own | own **and** the merchant is yours | — | own |

The insert policies check the merchant too, so supplying your own `owner_id`
alongside someone else's `merchant_id` is rejected.

`anon` is revoked from every private table. The public demo never touches them —
it reads the committed CSVs.

## 6. Storage

Two private buckets. Nothing is ever served from a public URL.

```
merchant-data/{user_id}/{merchant_id}/{upload_id}/source.csv
merchant-reports/{user_id}/{merchant_id}/{report_id}/report.pdf
```

Policies compare `(storage.foldername(name))[1]` against `auth.uid()`, so the
first path segment is the boundary.

**Path traversal is structurally impossible.** Every id in a path is validated
as a UUID before use (`workspace.require_uuid`), and a value containing `..`,
`/` or a null byte cannot parse as one. Before a download, the stored path is
**regenerated from verified ids and compared** with what the row holds; a
tampered row is refused with 409.

Downloads use a signed URL with a 300-second lifetime, issued only after
ownership is confirmed.

## 7. Upload contract

### Sales file — one row per product per day

| Column | Type | Meaning |
| --- | --- | --- |
| `date` | date | Business date |
| `product` | text | Product name |
| `category` | text | Category |
| `orders` | integer | Orders containing this product |
| `units_sold` | integer | Units sold (≥ `orders`) |
| `revenue` | number | Gross revenue |
| `expenses` | number | **Cost of goods sold**, not overheads |
| `inventory` | integer | Closing stock after the day's sales |

### Customer file — one row per day

| Column | Type | Meaning |
| --- | --- | --- |
| `date` | date | Business date |
| `customers` | integer | Distinct customers |
| `new_customers` | integer | First-time customers |
| `repeat_customers` | integer | Returning customers (`new + repeat == customers`) |

`merchant_id` is **not** a column. A merchant should not have to paste an
internal identifier into every row of their own spreadsheet, so it is injected
from the selected workspace during canonical conversion.

### Both files are required

Customer counts are held at daily grain precisely so they cannot be double
counted when a range spans several days. There is no honest way to derive them
from a product-level sales file, so an analysis with only one of the two is
refused with 409 rather than fabricating the other.

### Column mapping

1. A header that already **is** the canonical name wins.
2. Then a known synonym — `Qty`, `Total Sales`, `COGS`, `Bill Count`, `Footfall`
   and around 70 others, matched on a squashed form so `Units Sold`,
   `units-sold` and `UNITS_SOLD` all resolve identically.
3. Anything unmatched is left for the user to map by hand in the wizard.

A header is never used for two fields.

### Validation

Per cell: required-but-empty, unparseable date, non-numeric, negative,
fractional where a whole number is required.
Across rows: duplicate keys, `orders > units_sold`, units sold with zero orders,
`new + repeat != customers`.
Then the canonical frames go through the **same 13-rule validator the demo data
passes**, so an uploaded dataset is held to the identical standard.

**Nothing is ever repaired.** Currency symbols, thousands separators and
parenthesised negatives are stripped — that is presentation, and the magnitude
and sign are preserved exactly — but a value that still cannot be read is
reported with its row number, and the file is refused. A file is stored only
after it passes, so storage never holds something the product would then decline
to analyse.

## 8. Analysis pipeline

```
1. Validate the upload            (nothing stored yet)
2. Store the original file        (private bucket, owner's folder)
3. Create the upload record       (status: ready)
4. Download both stored files
5. Convert to the canonical schema, injecting merchant_id
6. dataset_from_frames() → validate → Dataset
7. metrics → analyse → recommendations → action_plan → forecast
8. Store the whole result as one analysis_runs row (status: completed)
9. The dashboard reads that row
```

Processing is synchronous. The analytics are milliseconds on a dataset this
size, so the request stays well inside the serverless limit. The work is
already isolated in `workspace.run_analysis()`, so moving it to a queue later
means changing the caller, not the logic.

Duplicate submissions are handled by `idempotency_key` on both uploads and
analysis runs — a retried request resolves to the existing row instead of
creating a second one.

## 9. Assistant

The private endpoint confirms ownership, builds a context from **that merchant's
dataset alone**, and calls the same `assistant.ask()` the demo uses. There is no
path by which another merchant's numbers could enter the context.

Grounding is unchanged and still enforced at runtime: with the optional model
enabled, any figure in its reply that cannot be traced to the computed context
causes the reply to be discarded in favour of the verified one. The internal
merchant id is stripped from the response — the caller already knows which
merchant they asked about.

## 10. Reports

A PDF is written directly as bytes with no third-party renderer, which keeps
tens of megabytes out of a serverless bundle already carrying pandas and NumPy.

It is built from a stored `analysis_runs` row, so it cannot disagree with the
dashboard. **Deliberately excluded:** access tokens, API keys, storage paths,
user ids and merchant ids. A test asserts none of them appear in the output.

## 10a. The demo workspace

The demo is a real Supabase account, seeded by `scripts/seed_demo.py`. It signs
in through the same flow as everyone else and is bound by exactly the same Row
Level Security, so it can only ever see its own synthetic data.

What makes it a demo is read-only enforcement in the API. With `DEMO_USER_ID`
set, every mutating route refuses that caller with **403**:

| Refused | Allowed |
| --- | --- |
| Create, update or delete a merchant | Every read |
| Upload a file | Generate a report |
| Run an analysis | Download a report |
| Delete a report | Ask the assistant |
| Change the profile | |

Report generation stays open because downloading one is part of the demo
journey. Everything else would let one visitor break the workspace for the next.

The seeder is idempotent — partial unique indexes in migration `0004` allow one
demo merchant per owner, one seeded upload per type and one seeded analysis per
merchant, so a second run updates rather than duplicates.

**Known gap:** Supabase provides no server-side way to prevent an account
changing its own password, so the demo's password form is hidden in the UI
rather than blocked by the API. The account holds nothing sensitive, and
`seed_demo.py --reset-password` restores it.

## 11. Data deletion

| Action | Effect |
| --- | --- |
| Delete a report | Row removed, stored PDF removed |
| Delete a merchant | Stored files removed first, then the row; `uploads`, `analysis_runs` and `reports` cascade |
| Delete the account | Removing the `auth.users` row cascades to `profiles` and `merchants`, and onward to everything below |

Stored objects are removed **before** their rows, so a failure cannot leave a
file behind that still holds the merchant's data with no record pointing at it.

Account deletion is not exposed in the UI: it is done from the Supabase
dashboard. The cascade behaviour above is what makes that safe.

## 12. Known limitations

- **Analysis is synchronous.** A very large upload could approach the function
  timeout. The structure supports moving it to a background worker.
- **Both files are required** before any analysis. Honest, but more friction
  than a single upload.
- **No rate limiting** on the API. Supabase applies its own limits to auth.
- **No audit log** of who read what.
- **Account deletion is manual**, via the Supabase dashboard.
- **Cold starts reload the demo dataset** (~0.65 s per instance); the cache is
  per-instance.
- **One currency per merchant**, applied as a formatting choice. Multi-currency
  data in one file is not reconciled.
- The analysis still reports **what changed, not why** — the uploaded schema
  carries no marketing, weather or competitor data, so no cause can be
  established from it.
