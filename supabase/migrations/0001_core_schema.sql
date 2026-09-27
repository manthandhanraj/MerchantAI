-- MerchantAI — core application schema
--
-- Every private table carries BOTH merchant_id and owner_id. The owner column
-- is redundant with a join through merchants, and that redundancy is the point:
-- it lets every Row Level Security policy be a direct comparison against
-- auth.uid() instead of a sub-select, which is cheaper and much harder to get
-- subtly wrong. Triggers keep the denormalised owner honest.
--
-- Apply with:  supabase db push      (or paste into the SQL editor in order)

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------- helpers

-- Keeps updated_at truthful without the application having to remember.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------- profiles

create table if not exists public.profiles (
  id          uuid primary key references auth.users (id) on delete cascade,
  full_name   text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),

  constraint profiles_full_name_length check (
    full_name is null or char_length(full_name) between 1 and 120
  )
);

comment on table public.profiles is
  'One row per authenticated user. Created automatically on sign-up.';

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();

-- A profile row should exist from the moment the account does, so the app
-- never has to handle "authenticated but no profile".
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, nullif(new.raw_user_meta_data ->> 'full_name', ''))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- merchants

create table if not exists public.merchants (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null references auth.users (id) on delete cascade,
  name           text not null,
  business_type  text,
  description    text,
  currency       text not null default 'INR',
  timezone       text not null default 'Asia/Kolkata',
  archived_at    timestamptz,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),

  constraint merchants_name_length check (char_length(name) between 1 and 120),
  constraint merchants_currency_format check (currency ~ '^[A-Z]{3}$'),
  constraint merchants_description_length check (
    description is null or char_length(description) <= 500
  )
);

comment on column public.merchants.archived_at is
  'Set instead of deleting when the owner archives a merchant. Null means active.';

create index if not exists merchants_owner_id_idx on public.merchants (owner_id);
create index if not exists merchants_owner_active_idx
  on public.merchants (owner_id, created_at desc)
  where archived_at is null;

drop trigger if exists merchants_set_updated_at on public.merchants;
create trigger merchants_set_updated_at
  before update on public.merchants
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- uploads

create table if not exists public.uploads (
  id                 uuid primary key default gen_random_uuid(),
  merchant_id        uuid not null references public.merchants (id) on delete cascade,
  owner_id           uuid not null references auth.users (id) on delete cascade,
  upload_type        text not null,
  original_filename  text not null,
  storage_path       text not null,
  status             text not null default 'pending',
  row_count          integer not null default 0,
  validation_summary jsonb not null default '{}'::jsonb,
  -- Set by the client so a retried submission cannot create a second upload.
  idempotency_key    text,
  created_at         timestamptz not null default now(),
  processed_at       timestamptz,

  constraint uploads_type_valid check (upload_type in ('sales', 'customers')),
  constraint uploads_status_valid check (
    status in ('pending', 'validating', 'ready', 'failed')
  ),
  constraint uploads_row_count_non_negative check (row_count >= 0),
  constraint uploads_filename_length check (char_length(original_filename) between 1 and 255)
);

create index if not exists uploads_merchant_idx on public.uploads (merchant_id, created_at desc);
create index if not exists uploads_owner_idx on public.uploads (owner_id);
create unique index if not exists uploads_idempotency_idx
  on public.uploads (merchant_id, idempotency_key)
  where idempotency_key is not null;

-- ---------------------------------------------------------- analysis_runs

create table if not exists public.analysis_runs (
  id              uuid primary key default gen_random_uuid(),
  merchant_id     uuid not null references public.merchants (id) on delete cascade,
  owner_id        uuid not null references auth.users (id) on delete cascade,
  -- The sales upload this run was computed from. Kept when the upload is
  -- removed so a historical analysis does not silently lose its provenance.
  upload_id       uuid references public.uploads (id) on delete set null,
  customers_upload_id uuid references public.uploads (id) on delete set null,
  status          text not null default 'pending',
  date_start      date,
  date_end        date,
  summary         jsonb,
  insights        jsonb,
  recommendations jsonb,
  action_plan     jsonb,
  forecast        jsonb,
  daily           jsonb,
  products        jsonb,
  categories      jsonb,
  inventory       jsonb,
  error_message   text,
  idempotency_key text,
  created_at      timestamptz not null default now(),
  completed_at    timestamptz,

  constraint analysis_status_valid check (
    status in ('pending', 'running', 'completed', 'failed')
  ),
  constraint analysis_period_ordered check (
    date_start is null or date_end is null or date_start <= date_end
  )
);

create index if not exists analysis_runs_merchant_idx
  on public.analysis_runs (merchant_id, created_at desc);
create index if not exists analysis_runs_owner_idx on public.analysis_runs (owner_id);
create unique index if not exists analysis_runs_idempotency_idx
  on public.analysis_runs (merchant_id, idempotency_key)
  where idempotency_key is not null;

-- ---------------------------------------------------------------- reports

create table if not exists public.reports (
  id              uuid primary key default gen_random_uuid(),
  merchant_id     uuid not null references public.merchants (id) on delete cascade,
  owner_id        uuid not null references auth.users (id) on delete cascade,
  analysis_run_id uuid references public.analysis_runs (id) on delete set null,
  format          text not null default 'pdf',
  storage_path    text not null,
  byte_size       integer,
  created_at      timestamptz not null default now(),

  constraint reports_format_valid check (format in ('pdf')),
  constraint reports_size_non_negative check (byte_size is null or byte_size >= 0)
);

create index if not exists reports_merchant_idx on public.reports (merchant_id, created_at desc);
create index if not exists reports_owner_idx on public.reports (owner_id);

-- ------------------------------------------------- owner_id integrity

-- The denormalised owner_id must always equal the merchant's real owner.
-- Enforced in the database so a bug in the API cannot produce a row that RLS
-- would then happily show to the wrong person.
create or replace function public.enforce_merchant_owner()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  real_owner uuid;
begin
  select owner_id into real_owner from public.merchants where id = new.merchant_id;

  if real_owner is null then
    raise exception 'merchant % does not exist', new.merchant_id;
  end if;

  if new.owner_id is distinct from real_owner then
    raise exception 'owner_id does not match the merchant owner';
  end if;

  return new;
end;
$$;

drop trigger if exists uploads_enforce_owner on public.uploads;
create trigger uploads_enforce_owner
  before insert or update on public.uploads
  for each row execute function public.enforce_merchant_owner();

drop trigger if exists analysis_runs_enforce_owner on public.analysis_runs;
create trigger analysis_runs_enforce_owner
  before insert or update on public.analysis_runs
  for each row execute function public.enforce_merchant_owner();

drop trigger if exists reports_enforce_owner on public.reports;
create trigger reports_enforce_owner
  before insert or update on public.reports
  for each row execute function public.enforce_merchant_owner();
