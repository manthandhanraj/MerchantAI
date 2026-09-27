"""Durable workspace storage for built-in accounts.

`LocalStore` implements the same small interface as `SupabaseClient` — select,
insert, update, delete, and four storage calls — so `services/workspace.py`
runs unchanged against either. Every merchant, upload, analysis and report
path in the product is therefore the same code whichever account system is
behind it.

Two responsibilities Supabase normally carries are taken on here:

* **Row Level Security.** A store is constructed for one verified user, and
  every read, write and delete is confined to rows that user owns. There is no
  method that reaches another owner's rows, which is the property RLS provides.
* **Private storage.** Files live under the data directory, and an object path
  must begin with the owner's id — the same rule the Supabase storage policies
  enforce. Paths are resolved and checked so nothing can escape that folder.

Data is written to SQLite and to disk, so it survives a restart.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.services import local_auth
from backend.app.services.supabase_client import SupabaseError

OWNED_TABLES = ("merchants", "uploads", "analysis_runs", "reports")
CHILD_TABLES = ("uploads", "analysis_runs", "reports")

# What the Postgres schema fills in when a column is omitted, mirrored so a row
# read back from either store has the same shape.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "merchants": {
        "business_type": None,
        "description": None,
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "archived_at": None,
        "is_demo": False,
    },
    "uploads": {
        "status": "pending",
        "row_count": 0,
        "validation_summary": {},
        "idempotency_key": None,
        "processed_at": None,
    },
    "analysis_runs": {
        "status": "pending",
        "upload_id": None,
        "customers_upload_id": None,
        "error_message": None,
        "idempotency_key": None,
        "completed_at": None,
    },
    "reports": {"format": "pdf", "analysis_run_id": None, "byte_size": None},
    "profiles": {"full_name": None},
}

# Uniqueness the database enforces with partial unique indexes.
_UNIQUE: dict[str, tuple[str, ...]] = {
    "uploads": ("merchant_id", "idempotency_key"),
    "analysis_runs": ("merchant_id", "idempotency_key"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches(row: dict, filters: dict[str, str]) -> bool:
    """Interpret the PostgREST filter forms the workspace uses."""
    for column, expression in (filters or {}).items():
        value = row.get(column)
        if expression == "is.null":
            if value is not None:
                return False
        elif expression.startswith("eq."):
            wanted = expression[3:]
            if isinstance(value, bool):
                if str(value).lower() != wanted.lower():
                    return False
            elif value is None or str(value) != wanted:
                return False
        else:
            raise SupabaseError(f"Unsupported filter on {column}.", 400)
    return True


@dataclass(frozen=True)
class LocalStore:
    """Scoped to one verified user for the lifetime of one request."""

    user_id: str

    # ------------------------------------------------------------ ownership
    def _owner_of(self, table: str, row: dict) -> str:
        return str(row.get("id") if table == "profiles" else row.get("owner_id"))

    def _load(self, connection, table: str) -> list[dict]:
        """Every row of `table` this user owns — the RLS boundary."""
        rows = connection.execute(
            "SELECT data FROM records WHERE tbl = ? AND owner_id = ? ORDER BY created_at",
            (table, self.user_id),
        ).fetchall()
        return [json.loads(r["data"]) for r in rows]

    # ------------------------------------------------------------ tables
    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, str] | None = None,
        order: str | None = None,
        limit: int | None = None,
        single: bool = False,
    ) -> Any:
        with local_auth.connect() as connection:
            rows = [r for r in self._load(connection, table) if _matches(r, filters or {})]

        if order:
            column, _, direction = order.partition(".")
            rows.sort(key=lambda r: str(r.get(column) or ""), reverse=direction.startswith("desc"))
        if limit:
            rows = rows[:limit]
        if columns and columns != "*":
            wanted = [c.strip() for c in columns.split(",")]
            rows = [{c: r.get(c) for c in wanted} for r in rows]

        if single:
            return rows[0] if rows else None
        return rows

    def insert(self, table: str, row: dict, *, upsert_on: str | None = None) -> dict:
        record = {**_DEFAULTS.get(table, {}), **row}
        record.setdefault("id", str(uuid.uuid4()))
        now = _now()
        record.setdefault("created_at", now)
        if table in ("merchants", "profiles"):
            record.setdefault("updated_at", now)

        owner = self._owner_of(table, record)
        # A caller can only ever create rows for themselves.
        if owner != self.user_id:
            raise SupabaseError("new row violates row-level security policy", 403)

        with local_auth._lock, local_auth.connect() as connection:
            # The Postgres trigger that pins owner_id to the merchant's real
            # owner, so no row can hang off someone else's merchant.
            if table in CHILD_TABLES:
                merchant = connection.execute(
                    "SELECT owner_id FROM records WHERE tbl = 'merchants' AND id = ?",
                    (str(record.get("merchant_id")),),
                ).fetchone()
                if merchant is None or merchant["owner_id"] != self.user_id:
                    raise SupabaseError("new row violates row-level security policy", 403)

            unique = _UNIQUE.get(table)
            if unique and all(record.get(c) is not None for c in unique):
                for existing in self._load(connection, table):
                    if all(existing.get(c) == record.get(c) for c in unique):
                        raise SupabaseError("duplicate key value violates unique constraint", 409)

            clash = connection.execute(
                "SELECT 1 FROM records WHERE tbl = ? AND id = ?", (table, record["id"])
            ).fetchone()
            if clash:
                raise SupabaseError("duplicate key value violates unique constraint", 409)

            connection.execute(
                "INSERT INTO records (tbl, id, owner_id, created_at, data) VALUES (?, ?, ?, ?, ?)",
                (table, record["id"], owner, record["created_at"], json.dumps(record)),
            )
        return dict(record)

    def update(self, table: str, filters: dict[str, str], patch: dict) -> dict | None:
        with local_auth._lock, local_auth.connect() as connection:
            for row in self._load(connection, table):
                if not _matches(row, filters):
                    continue
                updated = {**row, **patch}
                # Ownership cannot be reassigned by an update.
                updated["id"] = row["id"]
                if "owner_id" in row:
                    updated["owner_id"] = row["owner_id"]
                if table in ("merchants", "profiles"):
                    updated["updated_at"] = _now()
                connection.execute(
                    "UPDATE records SET data = ? WHERE tbl = ? AND id = ? AND owner_id = ?",
                    (json.dumps(updated), table, row["id"], self.user_id),
                )
                return dict(updated)
        return None

    def delete(self, table: str, filters: dict[str, str]) -> None:
        with local_auth._lock, local_auth.connect() as connection:
            doomed = [r for r in self._load(connection, table) if _matches(r, filters)]
            for row in doomed:
                connection.execute(
                    "DELETE FROM records WHERE tbl = ? AND id = ? AND owner_id = ?",
                    (table, row["id"], self.user_id),
                )
                # ON DELETE CASCADE from merchants.
                if table == "merchants":
                    for child in CHILD_TABLES:
                        for dependant in self._load(connection, child):
                            if dependant.get("merchant_id") == row["id"]:
                                connection.execute(
                                    "DELETE FROM records WHERE tbl = ? AND id = ? AND owner_id = ?",
                                    (child, dependant["id"], self.user_id),
                                )

    # ------------------------------------------------------------ storage
    def _object_path(self, bucket: str, path: str) -> Path:
        """Resolve an object path, refusing anything outside the owner's folder.

        Mirrors the storage policies: the first segment must be the caller's
        id. Resolution then guards against '..' or symlinks walking out of it.
        """
        if not path.startswith(f"{self.user_id}/"):
            raise SupabaseError("storage policy denied this path", 403)
        if bucket not in ("merchant-data", "merchant-reports") and not bucket.replace("-", "").isalnum():
            raise SupabaseError("Unknown storage bucket.", 400)

        root = (local_auth.data_dir() / "storage" / bucket).resolve()
        target = (root / path).resolve()
        if root not in target.parents:
            raise SupabaseError("storage policy denied this path", 403)
        return target

    def upload_object(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        target = self._object_path(bucket, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(data)
        # Atomic replace: a crash mid-write never leaves a half-written file
        # where a complete one is expected.
        temporary.replace(target)

    def download_object(self, bucket: str, path: str) -> bytes:
        target = self._object_path(bucket, path)
        if not target.exists():
            raise SupabaseError("The stored file is missing.", 404)
        return target.read_bytes()

    def create_signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        target = self._object_path(bucket, path)
        if not target.exists():
            raise SupabaseError("Could not create a download link.", 404)
        reference = local_auth.sign_file_reference(bucket, path, expires_in)
        return f"/api/files/{reference}"

    def delete_object(self, bucket: str, path: str) -> None:
        try:
            target = self._object_path(bucket, path)
        except SupabaseError:
            return
        if target.exists():
            target.unlink()
        # Tidy empty folders up to the bucket root.
        root = (local_auth.data_dir() / "storage" / bucket).resolve()
        parent = target.parent
        while parent != root and root in parent.parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def storage_file_for(bucket: str, path: str) -> Path:
    """Resolve a signed reference's target. Used only by the download route."""
    owner = path.split("/", 1)[0]
    return LocalStore(user_id=owner)._object_path(bucket, path)
