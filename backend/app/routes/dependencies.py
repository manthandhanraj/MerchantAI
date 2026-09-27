"""Shared FastAPI dependencies.

Loading the dataset is the one thing every data route does, and every route
needs to fail the same way when the pipeline is not ready. Keeping that in one
dependency stops each router growing its own copy of the error handling.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from backend.app.config import settings

from backend.app.services.auth import AuthError, AuthUser, user_from_header
from backend.app.services.data_loader import Dataset, DatasetNotFoundError, get_dataset
from backend.app.services.supabase_client import SupabaseClient
from backend.app.services.validation import DatasetValidationError
from backend.app.services.workspace import WorkspaceError


def load_dataset() -> Dataset:
    """Load the dataset, turning pipeline failures into an honest 503.

    A missing or invalid dataset is a service-not-ready condition rather than a
    bad request, and the detail carries the exact command to fix it.
    """
    try:
        return get_dataset()
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DatasetValidationError as exc:
        raise HTTPException(status_code=503, detail=f"Dataset failed validation.\n{exc}") from exc


LoadedDataset = Annotated[Dataset, Depends(load_dataset)]


def validate_query(dataset: Dataset, merchant_id: str, start: date | None, end: date | None) -> None:
    """Reject an unknown merchant or an inverted date range.

    Shared by every per-merchant route so they fail identically: a client
    should not have to learn a different error shape per endpoint.
    """
    known = dataset.merchant_ids
    if merchant_id not in known:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown merchant '{merchant_id}'. Available merchants: {', '.join(known)}.",
        )

    if start is not None and end is not None and start > end:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date range: start ({start}) is after end ({end}).",
        )


# --------------------------------------------------------------------------
# Private workspace
# --------------------------------------------------------------------------
def current_user(authorization: str | None = Header(default=None)) -> AuthUser:
    """The verified caller, or a 401.

    The user is derived from the token's signature, never from a header, body
    field or query parameter the client controls. `WWW-Authenticate` is set so
    a browser client can tell an expired session from a permissions problem.
    """
    try:
        return user_from_header(authorization)
    except AuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
        ) from exc


CurrentUser = Annotated[AuthUser, Depends(current_user)]


def supabase_for(user: CurrentUser) -> SupabaseClient:
    """A data client scoped to the caller.

    With Supabase, requests carry the caller's own token, so PostgREST and
    Storage evaluate that user's Row Level Security policies. With built-in
    accounts, the store is constructed for the verified user id and confines
    every operation to that user's rows. Either way the API never acts with
    elevated privileges on a user-facing path.
    """
    if settings.resolved_auth_mode == "local":
        from backend.app.services.local_store import LocalStore

        return LocalStore(user_id=user.id)  # type: ignore[return-value]
    return SupabaseClient(access_token=user.token)


UserClient = Annotated[SupabaseClient, Depends(supabase_for)]


def workspace_http_error(exc: WorkspaceError) -> HTTPException:
    """Translate a workspace failure into its HTTP form, message intact."""
    return HTTPException(status_code=exc.status_code, detail=str(exc))
