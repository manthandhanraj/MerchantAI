-- MerchantAI — the shared read-only demo workspace
--
-- The demo is a real account authenticating through Supabase like any other.
-- What makes it a demo is this flag plus the backend's refusal to mutate
-- anything owned by the configured demo user.
--
-- Additive and safe to re-run. No existing policy is relaxed: the demo account
-- is still bound by exactly the same Row Level Security as every other user,
-- so it can only ever see its own seeded synthetic data.

alter table public.merchants
  add column if not exists is_demo boolean not null default false;

comment on column public.merchants.is_demo is
  'True for the seeded public demonstration workspace. Its data is synthetic '
  'and is never presented as a real business.';

-- The demo dashboard is opened far more often than it is written to, and it is
-- always fetched by this flag.
create index if not exists merchants_is_demo_idx
  on public.merchants (is_demo)
  where is_demo = true;

-- Seeding is idempotent: one demo merchant per owner, enforced here rather
-- than trusted to the script, so a second run cannot create a duplicate.
create unique index if not exists merchants_one_demo_per_owner_idx
  on public.merchants (owner_id)
  where is_demo = true;

-- Uploads and analyses are seeded once per merchant per type. Without this a
-- re-run would stack duplicate rows behind the same dashboard.
create unique index if not exists uploads_one_seed_per_type_idx
  on public.uploads (merchant_id, upload_type)
  where idempotency_key like 'seed-%';

create unique index if not exists analysis_runs_one_seed_idx
  on public.analysis_runs (merchant_id)
  where idempotency_key like 'seed-%';
