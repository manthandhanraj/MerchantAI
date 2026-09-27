"""Seeding the shared read-only demo workspace.

One implementation for both account systems. With Supabase it is driven by
`scripts/seed_demo.py` using a privileged client; with built-in accounts it runs
automatically the first time someone signs in as the demo, against a store
scoped to the demo user.

Everything is idempotent. A second run finds and refreshes the same rows rather
than creating a second demo, so restarting the server — or two visitors
clicking "Try demo account" at the same moment — cannot duplicate anything.

The seeded data is synthetic throughout: one merchant taken from the committed
demonstration dataset, uploaded exactly as a real merchant would upload it.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pandas as pd

from backend.app.config import LOCAL_DEMO_USER_ID, settings
from backend.app.services import uploads as upload_service
from backend.app.services import workspace as ws
from backend.app.services.auth import AuthUser
from backend.app.services.reporting import build_report_pdf

# The declining cafe: revenue falls across the window and retention slides late
# in it, so the demo has real findings, a real plan and a falling forecast.
SOURCE_MERCHANT = "M003"

DEMO_MERCHANT = {
    "name": "Chai Point Cafe (Demo)",
    "business_type": "Cafe or restaurant",
    "currency": "INR",
    "timezone": "Asia/Kolkata",
    "description": "A synthetic example business. All figures are generated for demonstration.",
}

_seed_lock = threading.Lock()


class SeedError(Exception):
    """The committed dataset could not be turned into a demo workspace."""


def build_demo_csvs() -> tuple[str, str]:
    """Extract one merchant from the committed dataset, as a user would upload it.

    `merchant_id` is dropped: the upload contract does not ask for it, and the
    seeded files must look exactly like something a merchant would export.
    """
    sales = pd.read_csv(settings.sales_path, dtype=str)
    customers = pd.read_csv(settings.customers_path, dtype=str)

    sales = sales[sales["merchant_id"] == SOURCE_MERCHANT].drop(columns=["merchant_id"])
    customers = customers[customers["merchant_id"] == SOURCE_MERCHANT].drop(
        columns=["merchant_id"]
    )
    if sales.empty or customers.empty:
        raise SeedError(f"No rows for {SOURCE_MERCHANT} in the committed dataset.")
    return sales.to_csv(index=False), customers.to_csv(index=False)


def _ensure_merchant(client, user_id: str, log) -> dict:
    existing = client.select(
        ws.MERCHANTS,
        filters={"owner_id": f"eq.{user_id}", "is_demo": "eq.true"},
        single=True,
    )
    if existing:
        log(f"demo merchant already exists ({existing['name']})")
        return existing
    row = client.insert(ws.MERCHANTS, {**DEMO_MERCHANT, "owner_id": user_id, "is_demo": True})
    log(f"created demo merchant '{row['name']}'")
    return row


def _ensure_upload(client, user_id: str, merchant: dict, upload_type: str, content: str, log) -> dict:
    key = f"seed-{upload_type}"
    existing = client.select(
        ws.UPLOADS,
        filters={"merchant_id": f"eq.{merchant['id']}", "idempotency_key": f"eq.{key}"},
        single=True,
    )

    data = content.encode()
    check = upload_service.check_upload(upload_service.read_csv_bytes(data, "seed.csv"), upload_type)
    if not check.ok:
        raise SeedError(
            f"The committed {upload_type} data did not pass upload validation: "
            + "; ".join(f"row {e.row} {e.column} {e.problem}" for e in check.errors[:5])
        )

    upload_id = existing["id"] if existing else str(uuid.uuid4())
    path = ws.storage_path_for_upload(user_id, merchant["id"], upload_id)
    client.upload_object(settings.supabase_data_bucket, path, data, "text/csv")

    row = {
        "id": upload_id,
        "merchant_id": merchant["id"],
        "owner_id": user_id,
        "upload_type": upload_type,
        "original_filename": f"demo-{upload_type}.csv",
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
        "idempotency_key": key,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        client.update(ws.UPLOADS, {"id": f"eq.{upload_id}"}, row)
        log(f"refreshed {upload_type} upload ({check.row_count} rows)")
    else:
        client.insert(ws.UPLOADS, row)
        log(f"stored {upload_type} upload ({check.row_count} rows)")
    return row


def _ensure_analysis(client, user: AuthUser, merchant: dict, force: bool, log) -> dict:
    existing = client.select(
        ws.ANALYSIS_RUNS,
        filters={"merchant_id": f"eq.{merchant['id']}", "idempotency_key": "eq.seed-analysis"},
        single=True,
    )
    if existing and existing.get("status") == "completed" and not force:
        log("analysis already present")
        return existing
    if existing:
        client.delete(ws.ANALYSIS_RUNS, {"id": f"eq.{existing['id']}"})

    log("running the analysis pipeline over the demo data")
    run = ws.run_analysis(client, user, merchant["id"], idempotency_key="seed-analysis")
    summary = run.get("summary") or {}
    log(f"analysed {summary.get('days', 0)} days")
    return run


def _ensure_report(client, user_id: str, merchant: dict, analysis: dict, force: bool, log) -> dict:
    existing = client.select(
        ws.REPORTS,
        filters={"merchant_id": f"eq.{merchant['id']}"},
        order="created_at.asc",
        limit=1,
    )
    if existing and not force:
        log("report already present")
        return existing[0]

    report_id = existing[0]["id"] if existing else str(uuid.uuid4())
    pdf = build_report_pdf(merchant, analysis)
    path = ws.storage_path_for_report(user_id, merchant["id"], report_id)
    client.upload_object(settings.supabase_reports_bucket, path, pdf, "application/pdf")

    row = {
        "id": report_id,
        "merchant_id": merchant["id"],
        "owner_id": user_id,
        "analysis_run_id": analysis.get("id"),
        "format": "pdf",
        "storage_path": path,
        "byte_size": len(pdf),
    }
    if existing:
        client.update(ws.REPORTS, {"id": f"eq.{report_id}"}, row)
    else:
        client.insert(ws.REPORTS, row)
    log(f"report ready ({len(pdf) // 1024} KB)")
    return row


def seed_workspace(client, user: AuthUser, *, force: bool = False, log=lambda _m: None) -> dict:
    """Create or refresh the demo merchant, its data, analysis and report."""
    merchant = _ensure_merchant(client, user.id, log)
    sales_csv, customers_csv = build_demo_csvs()
    _ensure_upload(client, user.id, merchant, upload_service.SALES, sales_csv, log)
    _ensure_upload(client, user.id, merchant, upload_service.CUSTOMERS, customers_csv, log)
    analysis = _ensure_analysis(client, user, merchant, force, log)
    _ensure_report(client, user.id, merchant, analysis, force, log)
    return merchant


# --------------------------------------------------------------------------
# Built-in accounts
# --------------------------------------------------------------------------
def ensure_local_demo(*, force: bool = False) -> None:
    """Make sure the built-in demo account exists and is fully seeded.

    Called before a demo sign-in is checked. Cheap once seeded: a single lookup
    confirms the analysis is present and nothing else runs.
    """
    from backend.app.services import local_auth
    from backend.app.services.local_store import LocalStore

    with _seed_lock:
        user = local_auth.get_user(LOCAL_DEMO_USER_ID)
        if user is None:
            user = local_auth.create_user(
                settings.demo_user_email,
                settings.demo_password,
                "MerchantAI Demo",
                user_id=LOCAL_DEMO_USER_ID,
            )
        elif not local_auth.verify_password(settings.demo_password, _stored_hash(user.id)):
            # The configured demo password changed; follow it, so the login
            # page's displayed credentials always work.
            local_auth.change_password(user.id, settings.demo_password)

        store = LocalStore(user_id=user.id)
        auth_user = AuthUser(id=user.id, email=user.email, role="authenticated", token="")

        merchant = store.select(ws.MERCHANTS, filters={"is_demo": "eq.true"}, single=True)
        if merchant and not force:
            seeded = store.select(
                ws.ANALYSIS_RUNS,
                filters={"merchant_id": f"eq.{merchant['id']}", "status": "eq.completed"},
                single=True,
            )
            reports = store.select(ws.REPORTS, filters={"merchant_id": f"eq.{merchant['id']}"})
            if seeded and reports:
                return

        seed_workspace(store, auth_user, force=force)


def _stored_hash(user_id: str) -> str:
    from backend.app.services import local_auth

    with local_auth.connect() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return row["password_hash"] if row else ""
