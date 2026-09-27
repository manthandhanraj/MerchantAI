"""The only place the backend talks to Supabase.

Two deliberate choices:

1. **Requests carry the caller's own access token**, not the service-role key.
   PostgREST and Storage therefore evaluate that user's RLS policies on every
   read and write. The API's own ownership checks sit on top of that, so a bug
   in one layer is caught by the other.

2. **Plain REST over httpx**, not the `supabase` SDK. The surface needed here is
   small, the calls are explicit and auditable, and the serverless bundle stays
   well inside its size limit.

The service-role key is used for exactly one thing — deleting a user's account —
and that path is opt-in and clearly marked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from backend.app.config import settings

try:  # pragma: no cover - depends on the installed environment
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]
    _HTTPX_AVAILABLE = False


TIMEOUT_SECONDS = 20.0


class SupabaseError(Exception):
    """A failed Supabase call, carrying a status code the route can reuse."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SupabaseClient:
    """Scoped to one authenticated user for the lifetime of one request."""

    access_token: str
    # Set only by `service_role_client()`. No request-handling path constructs
    # a client this way, so a user-facing route can never bypass RLS.
    privileged: bool = False

    # ---------------------------------------------------------------- plumbing
    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        api_key = (
            settings.supabase_service_role_key if self.privileged else settings.supabase_anon_key
        )
        headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if not _HTTPX_AVAILABLE:
            raise SupabaseError(
                "httpx is not installed, so the private workspace cannot reach "
                "Supabase. Install it with: pip install httpx",
                status_code=503,
            )
        if not settings.supabase_configured:
            raise SupabaseError(
                "The private workspace is not configured on this server.",
                status_code=503,
            )

        request_headers = self._headers(headers)
        if content is not None:
            request_headers.pop("Content-Type", None)

        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
                response = client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    content=content,
                    headers=request_headers,
                )
        except Exception as exc:  # noqa: BLE001 - network failures of any kind
            # The exception text can contain the full URL; the message returned
            # to the caller deliberately does not.
            raise SupabaseError("Could not reach the data service.") from exc

        if response.status_code >= 400:
            raise SupabaseError(_readable_error(response), _client_status(response.status_code))

        if not response.content:
            return None
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.content

    # ---------------------------------------------------------------- tables
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
        params: dict[str, Any] = {"select": columns}
        params.update(filters or {})
        if order:
            params["order"] = order
        if limit:
            params["limit"] = limit

        headers = {"Accept": "application/vnd.pgrst.object+json"} if single else None
        try:
            return self._request(
                "GET", f"{settings.supabase_rest_url}/{table}", params=params, headers=headers
            )
        except SupabaseError as exc:
            # PostgREST answers "exactly one row expected, zero found" with 406.
            if single and exc.status_code in (404, 406):
                return None
            raise

    def insert(self, table: str, row: dict[str, Any], *, upsert_on: str | None = None) -> dict:
        prefer = "return=representation"
        if upsert_on:
            prefer += f",resolution=merge-duplicates"
        headers = {"Prefer": prefer}
        if upsert_on:
            headers["on_conflict"] = upsert_on

        params = {"on_conflict": upsert_on} if upsert_on else None
        body = self._request(
            "POST",
            f"{settings.supabase_rest_url}/{table}",
            json_body=[row],
            params=params,
            headers=headers,
        )
        rows = body or []
        if not rows:
            raise SupabaseError("The record was not created.", 502)
        return rows[0]

    def update(self, table: str, filters: dict[str, str], patch: dict[str, Any]) -> dict | None:
        body = self._request(
            "PATCH",
            f"{settings.supabase_rest_url}/{table}",
            params=filters,
            json_body=patch,
            headers={"Prefer": "return=representation"},
        )
        rows = body or []
        return rows[0] if rows else None

    def delete(self, table: str, filters: dict[str, str]) -> None:
        self._request("DELETE", f"{settings.supabase_rest_url}/{table}", params=filters)

    # ---------------------------------------------------------------- storage
    def upload_object(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        """Write an object. `x-upsert` makes a retried request idempotent."""
        self._request(
            "POST",
            f"{settings.supabase_storage_url}/object/{bucket}/{path}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )

    def download_object(self, bucket: str, path: str) -> bytes:
        body = self._request("GET", f"{settings.supabase_storage_url}/object/{bucket}/{path}")
        if isinstance(body, bytes):
            return body
        if body is None:
            raise SupabaseError("The stored file is empty.", 404)
        return json.dumps(body).encode()

    def create_signed_url(self, bucket: str, path: str, expires_in: int) -> str:
        """Mint a short-lived download URL. Callers must confirm ownership first."""
        body = self._request(
            "POST",
            f"{settings.supabase_storage_url}/object/sign/{bucket}/{path}",
            json_body={"expiresIn": expires_in},
        )
        signed = (body or {}).get("signedURL") or (body or {}).get("signedUrl")
        if not signed:
            raise SupabaseError("Could not create a download link.", 502)
        # Supabase returns a path relative to /storage/v1.
        if signed.startswith("http"):
            return signed
        return f"{settings.supabase_storage_url}{signed if signed.startswith('/') else '/' + signed}"

    def delete_object(self, bucket: str, path: str) -> None:
        try:
            self._request("DELETE", f"{settings.supabase_storage_url}/object/{bucket}/{path}")
        except SupabaseError:
            # A missing object is not a failure when the goal is "it is gone".
            pass


def service_role_client() -> SupabaseClient:
    """A client that bypasses Row Level Security.

    **For offline administrative scripts only** — currently just the demo
    seeder. It is never constructed while handling a request, and the key it
    uses is read from the server environment, never sent to a browser.
    """
    if not settings.supabase_service_role_key:
        raise SupabaseError(
            "SUPABASE_SERVICE_ROLE_KEY is not set, so privileged operations "
            "cannot run. It belongs in the server environment only.",
            503,
        )
    return SupabaseClient(access_token=settings.supabase_service_role_key, privileged=True)


def admin_request(method: str, path: str, json_body: Any = None) -> Any:
    """Call a Supabase Admin API endpoint with the service-role key.

    Separate from `SupabaseClient` because the Admin API is not PostgREST and
    has no RLS to respect. Same restriction applies: scripts only.
    """
    client = service_role_client()
    return client._request(  # noqa: SLF001 - deliberate, one module, one purpose
        method, f"{settings.supabase_auth_url}{path}", json_body=json_body
    )


def _client_status(status: int) -> int:
    """Map an upstream status onto one that makes sense to our caller."""
    if status in (401, 403):
        return 403
    if status == 404:
        return 404
    if status == 409:
        return 409
    if 400 <= status < 500:
        return 400
    return 502


def _readable_error(response: Any) -> str:
    """Extract a safe message. Never returns a raw upstream body verbatim."""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        return "The data service rejected the request."

    for key in ("message", "msg", "error_description", "error", "hint"):
        value = body.get(key) if isinstance(body, dict) else None
        if isinstance(value, str) and value:
            return value
    return "The data service rejected the request."
