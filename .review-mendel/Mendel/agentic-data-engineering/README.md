# Mendel — Agentic Data Engineering & Self-Healing Schema Evolution

**Code:** TCMAJA1346 · **Stack:** Java 21 · Spring Boot 3.3 · PostgreSQL · Gemini · Docker

An agentic platform that monitors a data pipeline, detects schema drift, uses an
LLM (Gemini) to plan a safe migration, applies it under guardrails, and can roll
it back — with a full audit trail.

## Modules

| Module | Status |
|---|---|
| Metadata registry (versioned schema source of truth) | ✅ Phase 1 |
| Pipeline monitor (CSV ingest + schema extraction) | ✅ Phase 1 |
| Schema detector (drift diff + classification) | ✅ Phase 2 |
| LLM planner (Gemini → plan JSON, rule-based fallback) | ✅ Phase 2 |
| Migration executor (guardrails + atomic apply) | ✅ Phase 3 |
| Rollback / audit | ✅ Phase 3 |
| Dashboard wired to live API | ✅ Phase 4 |

## Run

```bash
cp .env.example .env        # set ADE_API_KEY; GEMINI_API_KEY is optional
docker compose up --build   # Postgres + app on :8080
```

**Dashboard:** open <http://localhost:8080/> — the neon dashboard is served by the
app itself and pulls live numbers from `/api/dashboard/summary` (auto-refreshes
every 20s). If the backend is down it falls back to demo data, so it never breaks.

## Full loop demo (Phases 1–3)

Set `API_KEY` to the `ADE_API_KEY` value from `.env`, then include
`-H "X-API-Key: $API_KEY"` on each `POST` request below.

```bash
# 1. Register + baseline
curl -s -X POST localhost:8080/api/datasets -H 'Content-Type: application/json' \
  -d '{"name":"customers","targetTable":"customers"}'
curl -s -X POST localhost:8080/api/datasets/1/ingest -F 'file=@sample/customers_v1.csv'

# 2. Drifted CSV -> engine detects ADDITIVE drift and PLANS a migration
curl -s -X POST localhost:8080/api/datasets/1/ingest -F 'file=@sample/customers_v2.csv'
curl -s localhost:8080/api/datasets/1/migrations        # see the plan (migration 1)

# 3. APPLY it — runs the DDL + bumps the active schema atomically
curl -s -X POST localhost:8080/api/migrations/1/apply
curl -s localhost:8080/api/datasets/1/schema            # now v2, with phone + loyalty_points

# 4. ROLL BACK — reverses the DDL + restores the previous schema version
curl -s -X POST localhost:8080/api/migrations/1/rollback
curl -s localhost:8080/api/datasets/1/schema            # back to v1
```

High-risk migrations (breaking / rename / risk=high) are refused unless you pass
`?confirm=true`:

```bash
curl -s -X POST 'localhost:8080/api/migrations/2/apply?confirm=true'
```

## Safety model (Phase 3)

- **Atomic:** DDL + metadata update run in one transaction. Any failure rolls the
  whole thing back and marks the migration `FAILED` — the DB and the registry
  never disagree.
- **Guardrails (before any SQL):**
  - only `ALTER TABLE` / `CREATE TABLE` statements that target the dataset's own
    table are allowed;
  - `DROP TABLE`, `TRUNCATE`, `DELETE FROM`, `GRANT`, statement chaining, etc. are
    blocked outright;
  - `DROP COLUMN` is allowed only on a `BREAKING` change;
  - high-risk migrations require `confirm=true`.
- **Reversible:** every plan carries `rollbackSql`; rollback replays it and
  reactivates the prior schema version.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/datasets` | Register a dataset |
| GET | `/api/datasets` / `/api/datasets/{id}` | List / get datasets |
| POST | `/api/datasets/{id}/ingest` | Ingest a CSV → drift + plan |
| GET | `/api/datasets/{id}/schema` · `/schema/history` | Active schema · history |
| GET | `/api/datasets/{id}/batches` | Ingested batches |
| GET | `/api/datasets/{id}/migrations` | Planned/applied migrations |
| GET | `/api/migrations/{id}` | One migration + full plan |
| POST | `/api/migrations/{id}/apply?confirm=` | Apply a migration |
| POST | `/api/migrations/{id}/rollback` | Roll a migration back |
| GET | `/api/dashboard/summary` | Aggregated stats + health + activity (for the UI) |

## Notes

- Gemini key optional — rule-based fallback plans additive/type/rename drift and
  refuses to auto-drop on breaking changes, so it demos fully offline.
- Type inference is conservative (unknown → `TEXT`).
- Lombok is used — enable the Lombok plugin in your IDE.
- Detector unit tests: `mvn test`.
