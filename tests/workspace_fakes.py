"""In-memory doubles for Supabase, so the workspace can be tested offline.

`FakeSupabase` implements the small surface `SupabaseClient` exposes and, more
importantly, **enforces ownership the way Row Level Security does**: every read
and write is filtered by the access token's user. A test that tries to reach
another user's row gets nothing back, exactly as the database would do.

This is what lets the cross-user tests be meaningful without a live project:
they exercise the API's own ownership checks against a store that is itself
scoping by owner.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.app.services.supabase_client import SupabaseError

# Tokens in these tests are opaque strings of the form "token:<user-id>".
TOKEN_PREFIX = "token:"


def token_for(user_id: str) -> str:
    return f"{TOKEN_PREFIX}{user_id}"


def user_of(token: str) -> str:
    if not token.startswith(TOKEN_PREFIX):
        raise SupabaseError("Invalid token.", 403)
    return token[len(TOKEN_PREFIX) :]


@dataclass
class Store:
    """The shared "database" and "storage" behind every FakeSupabase client."""

    tables: dict[str, list[dict]] = field(default_factory=dict)
    objects: dict[str, bytes] = field(default_factory=dict)

    def rows(self, table: str) -> list[dict]:
        return self.tables.setdefault(table, [])

    def reset(self) -> None:
        self.tables.clear()
        self.objects.clear()


def _matches(row: dict, filters: dict[str, str]) -> bool:
    """Interpret the PostgREST filter forms this app actually uses."""
    for column, expression in filters.items():
        if column in ("select", "order", "limit", "on_conflict"):
            continue
        if expression == "is.null":
            if row.get(column) is not None:
                return False
        elif expression.startswith("eq."):
            if str(row.get(column)) != expression[3:]:
                return False
        else:  # pragma: no cover - guards a filter form the app does not use
            raise AssertionError(f"Unsupported filter: {column}={expression}")
    return True


@dataclass
class FakeSupabase:
    """Stands in for `SupabaseClient`, scoped to one user's token."""

    access_token: str
    store: Store

    @property
    def user_id(self) -> str:
        return user_of(self.access_token)

    # ------------------------------------------------------------ tables
    def _visible(self, table: str) -> list[dict]:
        """Only rows this user owns. This is the RLS stand-in."""
        rows = self.store.rows(table)
        if table == "profiles":
            return [r for r in rows if r.get("id") == self.user_id]
        return [r for r in rows if r.get("owner_id") == self.user_id]

    def select(self, table, *, columns="*", filters=None, order=None, limit=None, single=False):
        matched = [r for r in self._visible(table) if _matches(r, filters or {})]

        if order:
            column, _, direction = order.partition(".")
            matched.sort(key=lambda r: str(r.get(column) or ""), reverse=direction.startswith("desc"))
        if limit:
            matched = matched[:limit]

        if single:
            return dict(matched[0]) if matched else None
        return [dict(row) for row in matched]

    def insert(self, table, row, *, upsert_on=None):
        record = dict(row)
        record.setdefault("id", str(uuid.uuid4()))
        record.setdefault("created_at", "2026-09-20T10:00:00+00:00")

        # The database enforces that owner_id matches the merchant's real owner
        # (0001_core_schema.sql). Mirrored here so a test cannot pass by
        # writing a row the real schema would reject.
        if table in ("uploads", "analysis_runs", "reports"):
            merchant = next(
                (m for m in self.store.rows("merchants") if m["id"] == record.get("merchant_id")),
                None,
            )
            if merchant is None:
                raise SupabaseError("merchant does not exist", 400)
            if merchant["owner_id"] != record.get("owner_id"):
                raise SupabaseError("owner_id does not match the merchant owner", 403)

        self.store.rows(table).append(record)
        return dict(record)

    def update(self, table, filters, patch):
        for row in self._visible(table):
            if _matches(row, filters):
                row.update(patch)
                return dict(row)
        return None

    def delete(self, table, filters):
        rows = self.store.rows(table)
        doomed = [r for r in self._visible(table) if _matches(r, filters)]
        for row in doomed:
            rows.remove(row)
            # Stand in for ON DELETE CASCADE.
            if table == "merchants":
                for child in ("uploads", "analysis_runs", "reports"):
                    self.store.tables[child] = [
                        r for r in self.store.rows(child) if r.get("merchant_id") != row["id"]
                    ]

    # ------------------------------------------------------------ storage
    def _key(self, bucket: str, path: str) -> str:
        return f"{bucket}/{path}"

    def upload_object(self, bucket, path, data, content_type):
        if not path.startswith(f"{self.user_id}/"):
            raise SupabaseError("storage policy denied this path", 403)
        self.store.objects[self._key(bucket, path)] = data

    def download_object(self, bucket, path):
        if not path.startswith(f"{self.user_id}/"):
            raise SupabaseError("storage policy denied this path", 403)
        data = self.store.objects.get(self._key(bucket, path))
        if data is None:
            raise SupabaseError("The stored file is empty.", 404)
        return data

    def create_signed_url(self, bucket, path, expires_in):
        if not path.startswith(f"{self.user_id}/"):
            raise SupabaseError("storage policy denied this path", 403)
        if self._key(bucket, path) not in self.store.objects:
            raise SupabaseError("Could not create a download link.", 404)
        return f"https://storage.test/{bucket}/{path}?token=signed&expires={expires_in}"

    def delete_object(self, bucket, path):
        self.store.objects.pop(self._key(bucket, path), None)
