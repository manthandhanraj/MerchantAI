-- System metadata tables for the agentic data-engineering platform.
-- These are the platform's OWN tables. Watched "target" tables are created/
-- migrated at runtime by the Migration Executor (Phase 3).

CREATE TABLE IF NOT EXISTS dataset (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL UNIQUE,
    target_table  VARCHAR(200) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schema_version (
    id          BIGSERIAL PRIMARY KEY,
    dataset_id  BIGINT NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    version     INTEGER NOT NULL,
    columns     JSONB NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, version)
);
CREATE INDEX IF NOT EXISTS idx_schema_version_dataset ON schema_version(dataset_id);

CREATE TABLE IF NOT EXISTS ingest_batch (
    id                BIGSERIAL PRIMARY KEY,
    dataset_id        BIGINT NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    source_file       VARCHAR(400),
    row_count         INTEGER NOT NULL DEFAULT 0,
    detected_columns  JSONB NOT NULL,
    status            VARCHAR(40) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingest_batch_dataset ON ingest_batch(dataset_id);

-- Reserved for Phase 3 (Migration Executor + Rollback/Audit).
CREATE TABLE IF NOT EXISTS migration_log (
    id            BIGSERIAL PRIMARY KEY,
    dataset_id    BIGINT NOT NULL REFERENCES dataset(id) ON DELETE CASCADE,
    from_version  INTEGER,
    to_version    INTEGER,
    drift_type    VARCHAR(40),
    plan          JSONB,
    target_columns JSONB,
    applied_sql   TEXT,
    rollback_sql  TEXT,
    risk_level    VARCHAR(20),
    status        VARCHAR(40) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_migration_log_dataset ON migration_log(dataset_id);

-- Added in Phase 3 (safe for DBs created in Phase 2).
ALTER TABLE migration_log ADD COLUMN IF NOT EXISTS target_columns JSONB;
