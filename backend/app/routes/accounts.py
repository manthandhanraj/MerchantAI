"""Built-in account endpoints: sign up, sign in, password, deletion, downloads.

Used when no Supabase project is configured. With Supabase these routes refuse
politely, because sign-up and sign-in then happen in the browser against
Supabase Auth directly and must not be duplicated here.

Responses never include a password or a password hash, and error messages never
reveal whether an email address is registered — except on sign-up, where
"already exists" is the only honest answer and every account system gives it.
"""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from backend.app.config import settings
from backend.app.routes.dependencies import CurrentUser
from backend.app.services import demo_seed, local_auth
from backend.app.services import workspace as ws
from backend.app.services.local_store import LocalStore, storage_file_for

router = APIRouter(prefix="/api", tags=["accounts"])


def _require_local() -> None:
    if settings.resolved_auth_mode != "local":
        raise HTTPException(
            status_code=409,
            detail=(
                "This server uses Supabase accounts, so sign-up and sign-in happen "
                "through Supabase rather than this endpoint."
            ),
        )


def _translate(exc: local_auth.LocalAuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/auth/config")
def auth_config() -> dict:
    """Which account system is live, so the browser can confirm its own view."""
    local = settings.resolved_auth_mode == "local"
    return {
        "mode": settings.resolved_auth_mode,
        "signup_enabled": True,
        "email_password_reset": not local,
        "persistent_storage": settings.local_storage_persistent if local else True,
    }


@router.get("/auth/demo")
def demo_credentials() -> dict:
    """The public demo login, shown on the sign-in page.

    Public by design: it opens a seeded, synthetic, read-only workspace and
    nothing else. Served from the backend so the displayed password is always
    the one the demo account actually has.
    """
    if settings.resolved_auth_mode != "local":
        return {"available": False}
    return {
        "available": bool(settings.demo_user_email and settings.demo_password),
        "email": settings.demo_user_email,
        "password": settings.demo_password,
    }


@router.post("/auth/signup", status_code=201)
def signup(payload: dict = Body(...)) -> dict:
    """Create an account and sign it in immediately."""
    _require_local()

    email = str(payload.get("email") or "")
    if email.strip().lower() == settings.demo_user_email.lower():
        raise HTTPException(
            status_code=409,
            detail="That address belongs to the shared demo. Use your own email to sign up.",
        )

    try:
        user = local_auth.create_user(
            email,
            str(payload.get("password") or ""),
            payload.get("full_name"),
        )
        return local_auth.issue_token(user)
    except local_auth.LocalAuthError as exc:
        raise _translate(exc) from exc


@router.post("/auth/login")
def login(payload: dict = Body(...)) -> dict:
    _require_local()
    email = str(payload.get("email") or "")
    password = str(payload.get("password") or "")

    # The demo is created on first use, so a fresh installation's demo button
    # works without anyone having run a setup step.
    if email.strip().lower() == settings.demo_user_email.lower():
        try:
            demo_seed.ensure_local_demo()
        except demo_seed.SeedError as exc:
            raise HTTPException(status_code=503, detail=f"The demo could not be prepared. {exc}") from exc

    try:
        user = local_auth.authenticate(email, password)
        return local_auth.issue_token(user)
    except local_auth.LocalAuthError as exc:
        raise _translate(exc) from exc


@router.post("/auth/password")
def change_password(user: CurrentUser, payload: dict = Body(...)) -> dict:
    _require_local()
    if settings.is_demo_user(user.id):
        raise HTTPException(
            status_code=403,
            detail="The demo account is shared, so its password cannot be changed.",
        )
    try:
        local_auth.change_password(user.id, str(payload.get("password") or ""))
    except local_auth.LocalAuthError as exc:
        raise _translate(exc) from exc
    return {"updated": True}


@router.delete("/auth/account", status_code=204)
def delete_account(user: CurrentUser) -> None:
    """Permanently delete this account, every business in it and every file.

    Stored files are removed before the records, so a failure part-way cannot
    leave a file behind with nothing pointing at it.
    """
    _require_local()
    if settings.is_demo_user(user.id):
        raise HTTPException(status_code=403, detail="The shared demo account cannot be deleted.")

    store = LocalStore(user_id=user.id)
    for merchant in ws.list_merchants(store, user, include_archived=True):
        ws.delete_merchant(store, user, merchant["id"])
    local_auth.delete_user(user.id)


@router.get("/files/{reference}")
def download_file(reference: str) -> FileResponse:
    """Serve one stored object named by a short-lived signed reference.

    The reference is only minted after ownership has been confirmed, carries
    its own expiry, and is tamper-evident, which is what a signed URL is.
    """
    _require_local()
    try:
        bucket, path = local_auth.read_file_reference(reference)
        target = storage_file_for(bucket, path)
    except local_auth.LocalAuthError as exc:
        raise _translate(exc) from exc
    except Exception as exc:  # noqa: BLE001 - any path problem is a refusal
        raise HTTPException(status_code=403, detail="This download link is not valid.") from exc

    if not target.exists():
        raise HTTPException(status_code=404, detail="That file no longer exists.")

    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    filename = "merchantai-report.pdf" if target.suffix == ".pdf" else "merchantai-data.csv"
    return FileResponse(
        target,
        media_type=media_type,
        filename=filename,
        headers={"Cache-Control": "private, no-store"},
    )
