"""The private workspace: merchants, uploads, analyses and reports.

This module is the seam between a merchant's own uploaded data and the existing
analytics engine. It deliberately contains **no business logic of its own** — it
assembles a `Dataset` from stored uploads and then calls exactly the same
services the public demo calls. Metrics, findings, thresholds, recommendations,
ranking, the forecast and the assistant are untouched, so a number computed for
an uploaded merchant is computed by the same code that computed it for M001.

Ownership is checked here on every path, in addition to the Row Level Security
policies enforced by the database. Two independent layers, because one of them
will eventually have a bug.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from backend.app.config import settings
from backend.app.models.schemas import CUSTOMERS_COLUMNS, SALES_COLUMNS
from backend.app.services import uploads as upload_service
from backend.app.services.action_plan import plan_from_recommendations
from backend.app.services.analysis import analyse
from backend.app.services.auth import AuthUser
from backend.app.services.data_loader import Dataset, dataset_from_frames
from backend.app.services.forecasting import forecast as build_forecast
from backend.app.services.metrics import (
    category_performance,
    daily_metrics,
    filter_dataset,
    inventory_position,
    product_performance,
    summary_metrics,
)
from backend.app.services.recommendations import recommendations_from_report
from backend.app.services.supabase_client import SupabaseClient, SupabaseError
from backend.app.services.validation import DatasetValidationError

MERCHANTS = "merchants"
UPLOADS = "uploads"
ANALYSIS_RUNS = "analysis_runs"
REPORTS = "reports"
PROFILES = "profiles"


class WorkspaceError(Exception):
    """A workspace failure with the HTTP status the route should return."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------
# Identifier safety
# --------------------------------------------------------------------------
def require_uuid(value: str, label: str) -> str:
    """Reject anything that is not a UUID.

    Every identifier reaching this module becomes part of a storage object path,
    so this is also the guard that makes path traversal impossible: a value
    containing '..', '/' or a null byte cannot parse as a UUID.
    """
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise WorkspaceError(f"Invalid {label}.", 400) from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------
def get_profile(client: SupabaseClient, user: AuthUser) -> dict[str, Any]:
    row = client.select(PROFILES, filters={"id": f"eq.{user.id}"}, single=True)
    if row is None:
        # The sign-up trigger normally creates this; a project restored from a
        # backup might not have it, so make the read self-healing.
        row = client.insert(PROFILES, {"id": user.id})
    return row


def update_profile(client: SupabaseClient, user: AuthUser, full_name: str | None) -> dict[str, Any]:
    patch = {"full_name": (full_name or "").strip() or None}
    updated = client.update(PROFILES, {"id": f"eq.{user.id}"}, patch)
    return updated or get_profile(client, user)


# --------------------------------------------------------------------------
# Merchants
# --------------------------------------------------------------------------
def list_merchants(client: SupabaseClient, user: AuthUser, include_archived: bool = False) -> list[dict]:
    filters = {"owner_id": f"eq.{user.id}"}
    if not include_archived:
        filters["archived_at"] = "is.null"
    return client.select(MERCHANTS, filters=filters, order="created_at.asc") or []


def create_merchant(client: SupabaseClient, user: AuthUser, payload: dict[str, Any]) -> dict:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise WorkspaceError("A business name is required.", 422)
    if len(name) > 120:
        raise WorkspaceError("The business name must be 120 characters or fewer.", 422)

    currency = str(payload.get("currency") or "INR").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise WorkspaceError("Currency must be a three-letter code, e.g. INR.", 422)

    description = (payload.get("description") or "").strip() or None
    if description and len(description) > 500:
        raise WorkspaceError("The description must be 500 characters or fewer.", 422)

    row = {
        "owner_id": user.id,
        "name": name,
        "business_type": (payload.get("business_type") or "").strip() or None,
        "description": description,
        "currency": currency,
        "timezone": (payload.get("timezone") or "Asia/Kolkata").strip() or "Asia/Kolkata",
    }
    return client.insert(MERCHANTS, row)


def get_merchant(client: SupabaseClient, user: AuthUser, merchant_id: str) -> dict:
    """Fetch a merchant, or fail as if it did not exist.

    A merchant belonging to someone else returns 404, not 403: confirming that
    an id exists but belongs to another account leaks information.
    """
    merchant_id = require_uuid(merchant_id, "merchant id")
    row = client.select(
        MERCHANTS,
        filters={"id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"},
        single=True,
    )
    if row is None:
        raise WorkspaceError("Merchant not found.", 404)
    return row


def update_merchant(client: SupabaseClient, user: AuthUser, merchant_id: str, payload: dict) -> dict:
    get_merchant(client, user, merchant_id)  # ownership gate

    patch: dict[str, Any] = {}
    if "name" in payload:
        name = str(payload["name"] or "").strip()
        if not name:
            raise WorkspaceError("A business name is required.", 422)
        patch["name"] = name[:120]
    for key in ("business_type", "timezone"):
        if key in payload:
            patch[key] = (str(payload[key] or "").strip() or None)
    if "description" in payload:
        patch["description"] = (str(payload["description"] or "").strip() or None)
    if "currency" in payload:
        currency = str(payload["currency"] or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise WorkspaceError("Currency must be a three-letter code, e.g. INR.", 422)
        patch["currency"] = currency
    if "archived" in payload:
        patch["archived_at"] = _now() if payload["archived"] else None

    if not patch:
        return get_merchant(client, user, merchant_id)

    updated = client.update(
        MERCHANTS, {"id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"}, patch
    )
    if updated is None:
        raise WorkspaceError("Merchant not found.", 404)
    return updated


def delete_merchant(client: SupabaseClient, user: AuthUser, merchant_id: str) -> None:
    """Remove a merchant and everything derived from it.

    Database rows cascade. Stored objects do not, so they are removed here
    first; a file left behind after its row is gone would be unreachable but
    still hold the merchant's data.
    """
    get_merchant(client, user, merchant_id)

    for upload in list_uploads(client, user, merchant_id):
        if upload.get("storage_path"):
            client.delete_object(settings.supabase_data_bucket, upload["storage_path"])
    for report in list_reports(client, user, merchant_id):
        if report.get("storage_path"):
            client.delete_object(settings.supabase_reports_bucket, report["storage_path"])

    client.delete(MERCHANTS, {"id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"})


# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------
def storage_path_for_upload(user_id: str, merchant_id: str, upload_id: str) -> str:
    return f"{user_id}/{merchant_id}/{upload_id}/source.csv"


def list_uploads(
    client: SupabaseClient, user: AuthUser, merchant_id: str, upload_type: str | None = None
) -> list[dict]:
    merchant_id = require_uuid(merchant_id, "merchant id")
    filters = {"merchant_id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"}
    if upload_type:
        filters["upload_type"] = f"eq.{upload_type}"
    return client.select(UPLOADS, filters=filters, order="created_at.desc") or []


def get_upload(client: SupabaseClient, user: AuthUser, merchant_id: str, upload_id: str) -> dict:
    merchant_id = require_uuid(merchant_id, "merchant id")
    upload_id = require_uuid(upload_id, "upload id")
    row = client.select(
        UPLOADS,
        filters={
            "id": f"eq.{upload_id}",
            "merchant_id": f"eq.{merchant_id}",
            "owner_id": f"eq.{user.id}",
        },
        single=True,
    )
    if row is None:
        raise WorkspaceError("Upload not found.", 404)
    return row


def validate_upload_bytes(
    content: bytes,
    filename: str,
    upload_type: str,
    mapping: dict[str, str | None] | None,
) -> upload_service.UploadCheck:
    """Parse and check a file without storing anything. Used by the wizard."""
    if upload_type not in upload_service.UPLOAD_TYPES:
        raise WorkspaceError("Unknown upload type.", 422)
    try:
        frame = upload_service.read_csv_bytes(content, filename)
        return upload_service.check_upload(frame, upload_type, mapping)
    except upload_service.UploadError as exc:
        raise WorkspaceError(str(exc), 422) from exc


def store_upload(
    client: SupabaseClient,
    user: AuthUser,
    merchant_id: str,
    *,
    content: bytes,
    filename: str,
    upload_type: str,
    mapping: dict[str, str | None] | None,
    idempotency_key: str | None = None,
) -> dict:
    """Validate, store the original file, and record the upload.

    The file is only written once validation has passed, so storage never holds
    a file the product would refuse to analyse.
    """
    merchant = get_merchant(client, user, merchant_id)

    # A retried submission must not create a second upload.
    if idempotency_key:
        existing = client.select(
            UPLOADS,
            filters={
                "merchant_id": f"eq.{merchant['id']}",
                "owner_id": f"eq.{user.id}",
                "idempotency_key": f"eq.{idempotency_key}",
            },
            single=True,
        )
        if existing:
            return existing

    check = validate_upload_bytes(content, filename, upload_type, mapping)
    if not check.ok:
        raise WorkspaceError(
            "The file did not pass validation. Fix the reported rows and upload it again.",
            422,
        )

    upload_id = str(uuid.uuid4())
    path = storage_path_for_upload(user.id, merchant["id"], upload_id)
    client.upload_object(settings.supabase_data_bucket, path, content, "text/csv")

    row = {
        "id": upload_id,
        "merchant_id": merchant["id"],
        "owner_id": user.id,
        "upload_type": upload_type,
        "original_filename": _safe_filename(filename),
        "storage_path": path,
        "status": "ready",
        "row_count": check.row_count,
        "validation_summary": {
            "messages": check.messages,
            "warnings": check.warnings,
            "mapping": check.mapping,
            "date_start": check.date_start,
            "date_end": check.date_end,
        },
        "idempotency_key": idempotency_key,
        "processed_at": _now(),
    }
    try:
        return client.insert(UPLOADS, row)
    except SupabaseError:
        # The record could not be written, so the stored object would be an
        # orphan holding the merchant's data. Remove it.
        client.delete_object(settings.supabase_data_bucket, path)
        raise


def _safe_filename(name: str) -> str:
    """Keep a recognisable name without keeping anything path-like.

    Separators are dropped and runs of dots collapse to one, so a traversal
    attempt such as '../../etc/passwd.csv' cannot survive as '..'. The name is
    only ever shown back to the owner — the stored object path is built from
    verified ids, never from this.
    """
    cleaned = "".join(c for c in str(name) if c.isalnum() or c in "._- ").strip()
    cleaned = re.sub(r"\.{2,}", ".", cleaned).lstrip(".")
    return (cleaned or "upload.csv")[:255]


# --------------------------------------------------------------------------
# Building a Dataset from stored uploads
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class MerchantData:
    dataset: Dataset
    sales_upload: dict
    customers_upload: dict


def _latest(uploads: list[dict], upload_type: str) -> dict | None:
    for row in uploads:  # already ordered newest first
        if row.get("upload_type") == upload_type and row.get("status") == "ready":
            return row
    return None


def build_merchant_dataset(
    client: SupabaseClient,
    user: AuthUser,
    merchant_id: str,
    *,
    sales_upload_id: str | None = None,
    customers_upload_id: str | None = None,
) -> MerchantData:
    """Assemble a `Dataset` for one merchant from their stored uploads.

    Both a sales file and a customer file are required. The analytics layer
    joins them on (date, merchant_id), and customer counts are held at daily
    grain precisely so they cannot be double counted — there is no honest way to
    derive one from the other, so neither is invented.
    """
    merchant = get_merchant(client, user, merchant_id)
    all_uploads = list_uploads(client, user, merchant["id"])

    sales_row = (
        get_upload(client, user, merchant["id"], sales_upload_id)
        if sales_upload_id
        else _latest(all_uploads, upload_service.SALES)
    )
    customers_row = (
        get_upload(client, user, merchant["id"], customers_upload_id)
        if customers_upload_id
        else _latest(all_uploads, upload_service.CUSTOMERS)
    )

    missing = []
    if sales_row is None:
        missing.append("sales")
    if customers_row is None:
        missing.append("customer")
    if missing:
        raise WorkspaceError(
            "Upload a " + " file and a ".join(missing) + " file before running an analysis.",
            409,
        )

    sales_frame = _canonical_frame(client, user, merchant, sales_row, upload_service.SALES)
    customers_frame = _canonical_frame(
        client, user, merchant, customers_row, upload_service.CUSTOMERS
    )

    try:
        dataset = dataset_from_frames(sales_frame, customers_frame)
    except DatasetValidationError as exc:
        raise WorkspaceError(
            "The uploaded files do not form a consistent dataset.\n" + str(exc), 422
        ) from exc

    return MerchantData(dataset=dataset, sales_upload=sales_row, customers_upload=customers_row)


def _canonical_frame(
    client: SupabaseClient,
    user: AuthUser,
    merchant: dict,
    upload_row: dict,
    upload_type: str,
) -> pd.DataFrame:
    """Download one stored upload and convert it to the canonical schema."""
    path = upload_row.get("storage_path") or ""
    # The stored path is regenerated from verified ids rather than trusted, so a
    # tampered row cannot point the download at another user's object.
    expected = storage_path_for_upload(user.id, merchant["id"], upload_row["id"])
    if path != expected:
        raise WorkspaceError("This upload's stored file could not be verified.", 409)

    content = client.download_object(settings.supabase_data_bucket, path)
    frame = upload_service.read_csv_bytes(content, "source.csv")

    mapping = (upload_row.get("validation_summary") or {}).get("mapping")
    if not mapping:
        mapping = upload_service.suggest_mapping(list(frame.columns), upload_type)

    return upload_service.to_canonical(frame, upload_type, mapping, merchant["id"])


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def _json_ready(value: Any) -> Any:
    """Make analytics output safe for JSON storage.

    pandas and NumPy scalars are not serialisable, and NaN is not valid JSON.
    """
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, (pd.Timestamp, date, datetime)):
        return value.isoformat()[:10] if not isinstance(value, datetime) else value.isoformat()
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            return str(value)
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return value


def serialise_report(report) -> dict:
    """Same shape as GET /api/insights, so one renderer serves both."""
    return {
        "merchant_id": report.merchant_id,
        "has_data": report.has_data,
        "period": report.period.as_dict() if report.period else None,
        "comparison_period": (
            report.comparison_period.as_dict() if report.comparison_period else None
        ),
        "comparison_basis": report.comparison_basis,
        "finding_count": len(report.findings),
        "severity_counts": report.severity_counts,
        "notes": list(report.notes),
        "findings": [finding.as_dict() for finding in report.findings],
    }


def serialise_recommendations(source) -> dict:
    """Same shape as GET /api/recommendations."""
    return {
        "merchant_id": source.merchant_id,
        "has_data": source.has_data,
        "period": source.period,
        "comparison_period": source.comparison_period,
        "comparison_basis": source.comparison_basis,
        "priority_counts": source.priority_counts,
        "recommendations": [item.as_dict() for item in source.recommendations],
        "unactioned": [item.as_dict() for item in source.unactioned],
        "notes": list(source.notes),
    }


def serialise_plan(plan) -> dict:
    """Same shape as GET /api/action-plan."""
    return {
        "merchant_id": plan.merchant_id,
        "has_data": plan.has_data,
        "period": plan.period,
        "comparison_period": plan.comparison_period,
        "comparison_basis": plan.comparison_basis,
        "total_available": plan.total_available,
        "included": plan.included,
        "truncated": plan.truncated,
        "notes": list(plan.notes),
        "high": [item.as_dict() for item in plan.high],
        "medium": [item.as_dict() for item in plan.medium],
        "low": [item.as_dict() for item in plan.low],
    }


def _frame_records(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
    return _json_ready(out.to_dict(orient="records"))


def run_analysis(
    client: SupabaseClient,
    user: AuthUser,
    merchant_id: str,
    *,
    start: date | None = None,
    end: date | None = None,
    sales_upload_id: str | None = None,
    customers_upload_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Run the full analytics pipeline over a merchant's uploaded data.

    The chain is exactly the one the public demo uses, and the analysis report
    is computed once and reused for the recommendations and the plan rather than
    being recomputed for each.
    """
    merchant = get_merchant(client, user, merchant_id)

    if idempotency_key:
        existing = client.select(
            ANALYSIS_RUNS,
            filters={
                "merchant_id": f"eq.{merchant['id']}",
                "owner_id": f"eq.{user.id}",
                "idempotency_key": f"eq.{idempotency_key}",
            },
            single=True,
        )
        if existing:
            return existing

    run_id = str(uuid.uuid4())
    base = {
        "id": run_id,
        "merchant_id": merchant["id"],
        "owner_id": user.id,
        "idempotency_key": idempotency_key,
    }

    try:
        data = build_merchant_dataset(
            client,
            user,
            merchant["id"],
            sales_upload_id=sales_upload_id,
            customers_upload_id=customers_upload_id,
        )
    except WorkspaceError as exc:
        client.insert(
            ANALYSIS_RUNS,
            {**base, "status": "failed", "error_message": str(exc), "completed_at": _now()},
        )
        raise

    merchant_key = merchant["id"]
    dataset = data.dataset

    if start is not None and end is not None and start > end:
        raise WorkspaceError("The start date is after the end date.", 400)

    scoped = filter_dataset(dataset, merchant_id=merchant_key, start=start, end=end)
    summary = summary_metrics(scoped)

    report = analyse(dataset, merchant_key, start, end)
    suggestions = recommendations_from_report(report)
    plan = plan_from_recommendations(suggestions)
    projection = build_forecast(dataset, merchant_key, start, end)

    row = {
        **base,
        "upload_id": data.sales_upload["id"],
        "customers_upload_id": data.customers_upload["id"],
        "status": "completed",
        "date_start": summary.get("period_start"),
        "date_end": summary.get("period_end"),
        "summary": _json_ready(summary),
        "daily": _frame_records(daily_metrics(scoped)),
        "products": _frame_records(product_performance(scoped)),
        "categories": _frame_records(category_performance(scoped)),
        "inventory": _frame_records(inventory_position(scoped)),
        "insights": _json_ready(serialise_report(report)),
        "recommendations": _json_ready(serialise_recommendations(suggestions)),
        "action_plan": _json_ready(serialise_plan(plan)),
        "forecast": _json_ready(projection.as_dict()),
        "completed_at": _now(),
    }
    return client.insert(ANALYSIS_RUNS, row)


def list_analyses(client: SupabaseClient, user: AuthUser, merchant_id: str) -> list[dict]:
    merchant_id = require_uuid(merchant_id, "merchant id")
    rows = client.select(
        ANALYSIS_RUNS,
        columns="id,status,date_start,date_end,created_at,completed_at,error_message,upload_id",
        filters={"merchant_id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"},
        order="created_at.desc",
    )
    return rows or []


def get_analysis(
    client: SupabaseClient, user: AuthUser, merchant_id: str, analysis_id: str | None
) -> dict:
    """Fetch one analysis, or the most recent completed one when id is omitted."""
    merchant_id = require_uuid(merchant_id, "merchant id")

    if analysis_id:
        analysis_id = require_uuid(analysis_id, "analysis id")
        row = client.select(
            ANALYSIS_RUNS,
            filters={
                "id": f"eq.{analysis_id}",
                "merchant_id": f"eq.{merchant_id}",
                "owner_id": f"eq.{user.id}",
            },
            single=True,
        )
    else:
        rows = client.select(
            ANALYSIS_RUNS,
            filters={
                "merchant_id": f"eq.{merchant_id}",
                "owner_id": f"eq.{user.id}",
                "status": "eq.completed",
            },
            order="created_at.desc",
            limit=1,
        )
        row = (rows or [None])[0]

    if row is None:
        raise WorkspaceError("No analysis found for this merchant.", 404)
    return row


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
def storage_path_for_report(user_id: str, merchant_id: str, report_id: str) -> str:
    return f"{user_id}/{merchant_id}/{report_id}/report.pdf"


def list_reports(client: SupabaseClient, user: AuthUser, merchant_id: str) -> list[dict]:
    merchant_id = require_uuid(merchant_id, "merchant id")
    return (
        client.select(
            REPORTS,
            filters={"merchant_id": f"eq.{merchant_id}", "owner_id": f"eq.{user.id}"},
            order="created_at.desc",
        )
        or []
    )


def get_report(client: SupabaseClient, user: AuthUser, merchant_id: str, report_id: str) -> dict:
    merchant_id = require_uuid(merchant_id, "merchant id")
    report_id = require_uuid(report_id, "report id")
    row = client.select(
        REPORTS,
        filters={
            "id": f"eq.{report_id}",
            "merchant_id": f"eq.{merchant_id}",
            "owner_id": f"eq.{user.id}",
        },
        single=True,
    )
    if row is None:
        raise WorkspaceError("Report not found.", 404)
    return row


def report_download_url(client: SupabaseClient, user: AuthUser, merchant_id: str, report_id: str) -> str:
    """Mint a signed URL, but only after the row has been confirmed as theirs."""
    report = get_report(client, user, merchant_id, report_id)
    expected = storage_path_for_report(user.id, merchant_id, report["id"])
    if report.get("storage_path") != expected:
        raise WorkspaceError("This report's stored file could not be verified.", 409)
    return client.create_signed_url(
        settings.supabase_reports_bucket, expected, settings.signed_url_ttl_seconds
    )
