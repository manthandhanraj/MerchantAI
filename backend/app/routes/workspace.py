"""Private workspace API.

Every route here requires a verified Supabase access token and operates only on
records the caller owns. The routes stay thin, as the public ones do: they parse
input, call one service, and shape a response. All ownership logic lives in
`services/workspace.py`, and the database enforces the same rules again through
Row Level Security.

Errors are returned as clean JSON. A stack trace never reaches the client.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile

from backend.app.config import settings
from backend.app.routes.dependencies import CurrentUser, UserClient, workspace_http_error
from backend.app.services import uploads as upload_service
from backend.app.services import workspace as ws
from backend.app.services.assistant import ask as assistant_ask
from backend.app.services.assistant import is_enabled as assistant_enabled
from backend.app.services.reporting import build_report_pdf
from backend.app.services.supabase_client import SupabaseError

router = APIRouter(prefix="/api", tags=["workspace"])


DEMO_REFUSAL = (
    "The demo workspace is read-only, so everyone who opens it sees the same "
    "working example. Create a free account to upload your own data."
)


def _block_demo(user) -> None:
    """Refuse a mutating call from the shared demo account.

    Enforced on the server, not in the interface: hiding a button stops an
    honest visitor, and this stops everyone else. The demo is a single shared
    record, and one deleted merchant would break it for every later visitor.
    """
    if settings.is_demo_user(user.id):
        raise HTTPException(status_code=403, detail=DEMO_REFUSAL)


def _guard(call):
    """Run a workspace call, converting its failures into HTTP responses."""
    try:
        return call()
    except ws.WorkspaceError as exc:
        raise workspace_http_error(exc) from exc
    except SupabaseError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _parse_mapping(raw: Any) -> dict[str, str | None] | None:
    """Accept a mapping as a dict or a JSON string, and reject anything else."""
    if raw in (None, "", "null"):
        return None
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Column mapping is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="Column mapping must be an object.")
    return {str(k): (str(v) if v not in (None, "") else None) for k, v in raw.items()}


# --------------------------------------------------------------------------
# Account
# --------------------------------------------------------------------------
@router.get("/me")
def me(user: CurrentUser, client: UserClient) -> dict:
    """The signed-in user, their profile and whether onboarding is complete."""
    profile = _guard(lambda: ws.get_profile(client, user))
    merchants = _guard(lambda: ws.list_merchants(client, user))
    is_demo = settings.is_demo_user(user.id)
    return {
        "user": user.as_dict(),
        "profile": profile,
        "merchant_count": len(merchants),
        # A demo visitor has a workspace already; sending them to onboarding
        # would only show them a form they are not allowed to submit.
        "needs_onboarding": len(merchants) == 0 and not is_demo,
        "is_demo": is_demo,
        "read_only": is_demo,
        "auth_mode": settings.resolved_auth_mode,
        "persistent_storage": (
            settings.local_storage_persistent
            if settings.resolved_auth_mode == "local"
            else True
        ),
    }


@router.patch("/me")
def update_me(user: CurrentUser, client: UserClient, payload: dict = Body(default={})) -> dict:
    _block_demo(user)
    profile = _guard(lambda: ws.update_profile(client, user, payload.get("full_name")))
    return {"profile": profile}


# --------------------------------------------------------------------------
# Merchants
# --------------------------------------------------------------------------
@router.get("/my/merchants")
def list_my_merchants(
    user: CurrentUser,
    client: UserClient,
    include_archived: bool = Query(False),
) -> dict:
    rows = _guard(lambda: ws.list_merchants(client, user, include_archived))
    return {"count": len(rows), "merchants": rows}


@router.post("/my/merchants", status_code=201)
def create_my_merchant(user: CurrentUser, client: UserClient, payload: dict = Body(...)) -> dict:
    _block_demo(user)
    return {"merchant": _guard(lambda: ws.create_merchant(client, user, payload))}


@router.get("/my/merchants/{merchant_id}")
def get_my_merchant(merchant_id: str, user: CurrentUser, client: UserClient) -> dict:
    merchant = _guard(lambda: ws.get_merchant(client, user, merchant_id))
    uploads = _guard(lambda: ws.list_uploads(client, user, merchant_id))
    analyses = _guard(lambda: ws.list_analyses(client, user, merchant_id))
    return {
        "merchant": merchant,
        "upload_count": len(uploads),
        "analysis_count": len(analyses),
        "has_sales_data": any(u["upload_type"] == "sales" and u["status"] == "ready" for u in uploads),
        "has_customer_data": any(
            u["upload_type"] == "customers" and u["status"] == "ready" for u in uploads
        ),
    }


@router.patch("/my/merchants/{merchant_id}")
def patch_my_merchant(
    merchant_id: str, user: CurrentUser, client: UserClient, payload: dict = Body(...)
) -> dict:
    _block_demo(user)
    return {"merchant": _guard(lambda: ws.update_merchant(client, user, merchant_id, payload))}


@router.delete("/my/merchants/{merchant_id}", status_code=204)
def delete_my_merchant(merchant_id: str, user: CurrentUser, client: UserClient) -> None:
    """Permanently remove a merchant, its uploads, analyses, reports and files."""
    _block_demo(user)
    _guard(lambda: ws.delete_merchant(client, user, merchant_id))


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------
@router.get("/my/merchants/{merchant_id}/uploads/schema")
def upload_schema(merchant_id: str, user: CurrentUser, client: UserClient) -> dict:
    """The columns each upload type expects, so the wizard can explain them."""
    _guard(lambda: ws.get_merchant(client, user, merchant_id))
    return {
        "max_bytes": settings.max_upload_bytes,
        "max_rows": settings.max_upload_rows,
        "types": {
            name: [
                {
                    "name": spec.name,
                    "kind": spec.kind,
                    "required": spec.required,
                    "description": spec.description,
                }
                for spec in upload_service.fields_for(name)
            ]
            for name in upload_service.UPLOAD_TYPES
        },
    }


@router.post("/my/merchants/{merchant_id}/uploads/validate")
async def validate_upload(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    file: UploadFile = File(...),
    upload_type: str = Form(...),
    mapping: str | None = Form(default=None),
) -> dict:
    """Check a file without storing it, so the wizard can show problems first."""
    _guard(lambda: ws.get_merchant(client, user, merchant_id))
    content = await _read_upload(file)
    check = _guard(
        lambda: ws.validate_upload_bytes(
            content, file.filename or "upload.csv", upload_type, _parse_mapping(mapping)
        )
    )
    return check.as_dict()


@router.post("/my/merchants/{merchant_id}/uploads", status_code=201)
async def create_upload(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    file: UploadFile = File(...),
    upload_type: str = Form(...),
    mapping: str | None = Form(default=None),
    idempotency_key: str | None = Form(default=None),
) -> dict:
    """Store a validated file and record the upload."""
    _block_demo(user)
    content = await _read_upload(file)
    row = _guard(
        lambda: ws.store_upload(
            client,
            user,
            merchant_id,
            content=content,
            filename=file.filename or "upload.csv",
            upload_type=upload_type,
            mapping=_parse_mapping(mapping),
            idempotency_key=_clean_key(idempotency_key),
        )
    )
    return {"upload": row}


@router.get("/my/merchants/{merchant_id}/uploads")
def list_my_uploads(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    upload_type: str | None = Query(None),
) -> dict:
    rows = _guard(lambda: ws.list_uploads(client, user, merchant_id, upload_type))
    return {"count": len(rows), "uploads": rows}


@router.get("/my/merchants/{merchant_id}/uploads/{upload_id}")
def get_my_upload(merchant_id: str, upload_id: str, user: CurrentUser, client: UserClient) -> dict:
    return {"upload": _guard(lambda: ws.get_upload(client, user, merchant_id, upload_id))}


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, refusing anything past the size limit.

    The limit is applied while reading rather than after, so an oversized file
    is never fully held in memory.
    """
    limit = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"The file is larger than the {limit / (1024 * 1024):.0f} MB limit.",
            )
        chunks.append(chunk)
    if not chunks:
        raise HTTPException(status_code=422, detail="The file is empty.")
    return b"".join(chunks)


def _clean_key(value: str | None) -> str | None:
    """Idempotency keys are client-supplied, so keep them short and inert."""
    if not value:
        return None
    cleaned = "".join(c for c in str(value) if c.isalnum() or c in "-_")[:80]
    return cleaned or None


# --------------------------------------------------------------------------
# Analyses
# --------------------------------------------------------------------------
@router.post("/my/merchants/{merchant_id}/analyses", status_code=201)
def create_analysis(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    payload: dict = Body(default={}),
) -> dict:
    """Run the analytics pipeline over this merchant's uploaded data."""
    _block_demo(user)
    start = _parse_date(payload.get("start"), "start")
    end = _parse_date(payload.get("end"), "end")
    row = _guard(
        lambda: ws.run_analysis(
            client,
            user,
            merchant_id,
            start=start,
            end=end,
            sales_upload_id=payload.get("sales_upload_id"),
            customers_upload_id=payload.get("customers_upload_id"),
            idempotency_key=_clean_key(payload.get("idempotency_key")),
        )
    )
    return {"analysis": row}


@router.get("/my/merchants/{merchant_id}/analyses")
def list_my_analyses(merchant_id: str, user: CurrentUser, client: UserClient) -> dict:
    rows = _guard(lambda: ws.list_analyses(client, user, merchant_id))
    return {"count": len(rows), "analyses": rows}


@router.get("/my/merchants/{merchant_id}/analyses/{analysis_id}")
def get_my_analysis(
    merchant_id: str, analysis_id: str, user: CurrentUser, client: UserClient
) -> dict:
    return {"analysis": _guard(lambda: ws.get_analysis(client, user, merchant_id, analysis_id))}


def _parse_date(value: Any, label: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"'{label}' must be a date in YYYY-MM-DD form."
        ) from exc


# --------------------------------------------------------------------------
# Dashboard reads
#
# These serve a stored analysis rather than recomputing. The figures a merchant
# sees are therefore exactly the figures that were computed and recorded, and a
# report generated later from the same run cannot disagree with them.
# --------------------------------------------------------------------------
def _analysis_or_404(client, user, merchant_id: str, analysis_id: str | None) -> dict:
    return _guard(lambda: ws.get_analysis(client, user, merchant_id, analysis_id))


@router.get("/my/merchants/{merchant_id}/dashboard")
def my_dashboard(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    analysis_id: str | None = Query(None),
) -> dict:
    merchant = _guard(lambda: ws.get_merchant(client, user, merchant_id))
    analysis = _analysis_or_404(client, user, merchant_id, analysis_id)

    source_upload = None
    if analysis.get("upload_id"):
        try:
            source_upload = ws.get_upload(client, user, merchant_id, analysis["upload_id"])
        except ws.WorkspaceError:
            # The source upload was deleted; the analysis is still valid.
            source_upload = None

    summary = analysis.get("summary") or {}
    return {
        "merchant": merchant,
        "analysis_id": analysis.get("id"),
        "status": analysis.get("status"),
        "has_data": bool(summary.get("days")),
        "summary": summary,
        "daily": analysis.get("daily") or [],
        "products": analysis.get("products") or [],
        "categories": analysis.get("categories") or [],
        "inventory": analysis.get("inventory") or [],
        "period": {"start": analysis.get("date_start"), "end": analysis.get("date_end")},
        "generated_at": analysis.get("completed_at") or analysis.get("created_at"),
        "source_upload": (
            {
                "id": source_upload["id"],
                "original_filename": source_upload["original_filename"],
                "row_count": source_upload["row_count"],
                "created_at": source_upload["created_at"],
            }
            if source_upload
            else None
        ),
    }


@router.get("/my/merchants/{merchant_id}/insights")
def my_insights(
    merchant_id: str, user: CurrentUser, client: UserClient, analysis_id: str | None = Query(None)
) -> dict:
    analysis = _analysis_or_404(client, user, merchant_id, analysis_id)
    return analysis.get("insights") or {"has_data": False, "findings": []}


@router.get("/my/merchants/{merchant_id}/recommendations")
def my_recommendations(
    merchant_id: str, user: CurrentUser, client: UserClient, analysis_id: str | None = Query(None)
) -> dict:
    analysis = _analysis_or_404(client, user, merchant_id, analysis_id)
    return analysis.get("recommendations") or {"has_data": False, "recommendations": []}


@router.get("/my/merchants/{merchant_id}/action-plan")
def my_action_plan(
    merchant_id: str, user: CurrentUser, client: UserClient, analysis_id: str | None = Query(None)
) -> dict:
    analysis = _analysis_or_404(client, user, merchant_id, analysis_id)
    return analysis.get("action_plan") or {"has_data": False, "high": [], "medium": [], "low": []}


@router.get("/my/merchants/{merchant_id}/forecast")
def my_forecast(
    merchant_id: str, user: CurrentUser, client: UserClient, analysis_id: str | None = Query(None)
) -> dict:
    analysis = _analysis_or_404(client, user, merchant_id, analysis_id)
    return analysis.get("forecast") or {"available": False, "reason": "No forecast was produced."}


# --------------------------------------------------------------------------
# Assistant
# --------------------------------------------------------------------------
@router.post("/my/merchants/{merchant_id}/assistant/ask")
def my_assistant(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    payload: dict = Body(...),
) -> dict:
    """Answer a question about this merchant, grounded in their own data.

    Ownership is confirmed before any context is built, and the context is
    assembled from this merchant's dataset alone — there is no path by which
    another merchant's numbers could enter the answer.
    """
    question = str(payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Ask a question first.")
    if len(question) > settings.max_question_length:
        raise HTTPException(
            status_code=422,
            detail=f"Questions are limited to {settings.max_question_length} characters.",
        )

    data = _guard(lambda: ws.build_merchant_dataset(client, user, merchant_id))
    merchant = _guard(lambda: ws.get_merchant(client, user, merchant_id))

    start = _parse_date(payload.get("start"), "start")
    end = _parse_date(payload.get("end"), "end")

    answer = assistant_ask(
        data.dataset,
        merchant["id"],
        question,
        start,
        end,
        include_context=False,
    )
    body = answer.as_dict()
    # The merchant id is an internal identifier; the caller already knows which
    # merchant they asked about.
    body.pop("merchant_id", None)
    return body


@router.get("/my/assistant/status")
def my_assistant_status(user: CurrentUser) -> dict:
    from backend.app.services.assistant import STARTER_QUESTIONS

    return {
        "enabled": assistant_enabled(),
        "suggested_questions": list(STARTER_QUESTIONS),
    }


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
@router.post("/my/merchants/{merchant_id}/reports", status_code=201)
def create_report(
    merchant_id: str,
    user: CurrentUser,
    client: UserClient,
    payload: dict = Body(default={}),
) -> dict:
    """Render a stored analysis as a PDF and file it privately."""
    merchant = _guard(lambda: ws.get_merchant(client, user, merchant_id))
    analysis = _analysis_or_404(client, user, merchant_id, payload.get("analysis_id"))

    if analysis.get("status") != "completed":
        raise HTTPException(
            status_code=409, detail="This analysis did not complete, so it cannot be reported on."
        )

    pdf = build_report_pdf(merchant, analysis)
    report_id = str(uuid.uuid4())
    path = ws.storage_path_for_report(user.id, merchant["id"], report_id)

    def _store() -> dict:
        client.upload_object(settings.supabase_reports_bucket, path, pdf, "application/pdf")
        try:
            return client.insert(
                ws.REPORTS,
                {
                    "id": report_id,
                    "merchant_id": merchant["id"],
                    "owner_id": user.id,
                    "analysis_run_id": analysis.get("id"),
                    "format": "pdf",
                    "storage_path": path,
                    "byte_size": len(pdf),
                },
            )
        except SupabaseError:
            client.delete_object(settings.supabase_reports_bucket, path)
            raise

    row = _guard(_store)
    return {"report": row}


@router.get("/my/merchants/{merchant_id}/reports")
def list_my_reports(merchant_id: str, user: CurrentUser, client: UserClient) -> dict:
    rows = _guard(lambda: ws.list_reports(client, user, merchant_id))
    return {"count": len(rows), "reports": rows}


@router.get("/my/merchants/{merchant_id}/reports/{report_id}/download")
def download_report(
    merchant_id: str, report_id: str, user: CurrentUser, client: UserClient
) -> dict:
    """A short-lived signed URL, issued only after ownership is confirmed."""
    url = _guard(lambda: ws.report_download_url(client, user, merchant_id, report_id))
    return {"url": url, "expires_in": settings.signed_url_ttl_seconds}


@router.delete("/my/merchants/{merchant_id}/reports/{report_id}", status_code=204)
def delete_report(merchant_id: str, report_id: str, user: CurrentUser, client: UserClient) -> None:
    _block_demo(user)
    report = _guard(lambda: ws.get_report(client, user, merchant_id, report_id))
    client.delete_object(settings.supabase_reports_bucket, report["storage_path"])
    client.delete(ws.REPORTS, {"id": f"eq.{report['id']}", "owner_id": f"eq.{user.id}"})
