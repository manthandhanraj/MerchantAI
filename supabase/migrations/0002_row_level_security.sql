-- MerchantAI — Row Level Security
--
-- RLS is the real access boundary. The API performs its own ownership checks
-- as well, but those are defence in depth: if every check in the application
-- were removed, these policies would still make it impossible for one user to
-- read another user's merchant, upload, analysis or report.
--
-- Every policy compares auth.uid() against the row's own owner_id. That is why
-- 0001 denormalises owner_id onto each table and enforces it with a trigger —
-- a policy that had to join through merchants would be slower and easier to
-- write incorrectly.

alter table public.profiles      enable row level security;
alter table public.merchants     enable row level security;
alter table public.uploads       enable row level security;
alter table public.analysis_runs enable row level security;
alter table public.reports       enable row level security;

-- Force RLS for the table owner too, so a future migration run as the owning
-- role cannot accidentally bypass these policies.
alter table public.profiles      force row level security;
alter table public.merchants     force row level security;
alter table public.uploads       force row level security;
alter table public.analysis_runs force row level security;
alter table public.reports       force row level security;

-- ---------------------------------------------------------------- profiles
-- A user may read and update their own profile. Rows are created by the
-- on_auth_user_created trigger, and there is deliberately no delete policy:
-- account deletion removes the auth user, which cascades.

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
  for select to authenticated
  using (auth.uid() = id);

drop policy if exists profiles_insert_own on public.profiles;
create policy profiles_insert_own on public.profiles
  for insert to authenticated
  with check (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own on public.profiles
  for update to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- ---------------------------------------------------------------- merchants

drop policy if exists merchants_select_own on public.merchants;
create policy merchants_select_own on public.merchants
  for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists merchants_insert_own on public.merchants;
create policy merchants_insert_own on public.merchants
  for insert to authenticated
  with check (auth.uid() = owner_id);

drop policy if exists merchants_update_own on public.merchants;
create policy merchants_update_own on public.merchants
  for update to authenticated
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists merchants_delete_own on public.merchants;
create policy merchants_delete_own on public.merchants
  for delete to authenticated
  using (auth.uid() = owner_id);

-- ---------------------------------------------------------------- uploads
-- The insert check also confirms the merchant is really the caller's, so a
-- caller cannot attach an upload to someone else's merchant by supplying their
-- own owner_id alongside a foreign merchant_id.

drop policy if exists uploads_select_own on public.uploads;
create policy uploads_select_own on public.uploads
  for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists uploads_insert_own on public.uploads;
create policy uploads_insert_own on public.uploads
  for insert to authenticated
  with check (
    auth.uid() = owner_id
    and exists (
      select 1 from public.merchants m
      where m.id = merchant_id and m.owner_id = auth.uid()
    )
  );

drop policy if exists uploads_update_own on public.uploads;
create policy uploads_update_own on public.uploads
  for update to authenticated
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists uploads_delete_own on public.uploads;
create policy uploads_delete_own on public.uploads
  for delete to authenticated
  using (auth.uid() = owner_id);

-- ---------------------------------------------------------- analysis_runs

drop policy if exists analysis_runs_select_own on public.analysis_runs;
create policy analysis_runs_select_own on public.analysis_runs
  for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists analysis_runs_insert_own on public.analysis_runs;
create policy analysis_runs_insert_own on public.analysis_runs
  for insert to authenticated
  with check (
    auth.uid() = owner_id
    and exists (
      select 1 from public.merchants m
      where m.id = merchant_id and m.owner_id = auth.uid()
    )
  );

drop policy if exists analysis_runs_update_own on public.analysis_runs;
create policy analysis_runs_update_own on public.analysis_runs
  for update to authenticated
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists analysis_runs_delete_own on public.analysis_runs;
create policy analysis_runs_delete_own on public.analysis_runs
  for delete to authenticated
  using (auth.uid() = owner_id);

-- ---------------------------------------------------------------- reports

drop policy if exists reports_select_own on public.reports;
create policy reports_select_own on public.reports
  for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists reports_insert_own on public.reports;
create policy reports_insert_own on public.reports
  for insert to authenticated
  with check (
    auth.uid() = owner_id
    and exists (
      select 1 from public.merchants m
      where m.id = merchant_id and m.owner_id = auth.uid()
    )
  );

drop policy if exists reports_delete_own on public.reports;
create policy reports_delete_own on public.reports
  for delete to authenticated
  using (auth.uid() = owner_id);

-- ------------------------------------------------------- anonymous access
-- No policy above grants anything to the `anon` role, so an unauthenticated
-- request reads nothing from these tables. The public demo does not touch them:
-- it is served from the committed synthetic CSVs instead.

revoke all on public.profiles      from anon;
revoke all on public.merchants     from anon;
revoke all on public.uploads       from anon;
revoke all on public.analysis_runs from anon;
revoke all on public.reports       from anon;
