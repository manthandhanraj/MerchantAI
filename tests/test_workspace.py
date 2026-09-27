"""Private workspace: ownership, uploads, analysis and reports.

The property under test throughout: **one user can never reach another user's
data**, whichever door they try — merchant, upload, analysis, report or stored
file. The fake Supabase in `workspace_fakes` scopes by owner the way Row Level
Security does, so these tests exercise the API's checks against a store that is
itself enforcing ownership.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.config import settings
from backend.app.services import uploads as up
from backend.app.services import workspace as ws
from backend.app.services.auth import AuthUser
from backend.app.services.reporting import build_report_pdf
from tests.workspace_fakes import FakeSupabase, Store, token_for

ALICE = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa"
BOB = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb"

# Four weeks of trading. The values satisfy every invariant the dataset
# contract documents: a constant unit price per product, orders never above
# units, daily customers never above daily orders, new + repeat == customers,
# and inventory falling by exactly units_sold. Anything else would be rejected
# by the same validation the demo data passes, which is the point.
A_PRICE, A_COST = 100, 50
B_PRICE, B_COST = 50, 25


def _sales_csv(product_a="Widget A", product_b="Widget B") -> str:
    a_stock, b_stock = 600, 400
    lines = ["date,product,category,orders,units_sold,revenue,expenses,inventory"]
    for day in range(1, 29):
        a_units, b_units = 5 + day % 3, 2 + day % 2
        a_stock -= a_units
        b_stock -= b_units
        lines.append(
            f"2026-03-{day:02d},{product_a},Tools,{a_units},{a_units},"
            f"{a_units * A_PRICE},{a_units * A_COST},{a_stock}"
        )
        lines.append(
            f"2026-03-{day:02d},{product_b},Parts,{b_units},{b_units},"
            f"{b_units * B_PRICE},{b_units * B_COST},{b_stock}"
        )
    return "\n".join(lines) + "\n"


def _customers_csv() -> str:
    lines = ["date,customers,new_customers,repeat_customers"]
    for day in range(1, 29):
        total = 4 + day % 3
        lines.append(f"2026-03-{day:02d},{total},2,{total - 2}")
    return "\n".join(lines) + "\n"


SALES_CSV = _sales_csv()
CUSTOMERS_CSV = _customers_csv()

EXPECTED_REVENUE = sum((5 + d % 3) * A_PRICE + (2 + d % 2) * B_PRICE for d in range(1, 29))
EXPECTED_ORDERS = sum((5 + d % 3) + (2 + d % 2) for d in range(1, 29))
EXPECTED_PROFIT = EXPECTED_REVENUE - sum(
    (5 + d % 3) * A_COST + (2 + d % 2) * B_COST for d in range(1, 29)
)


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def alice(store):
    return AuthUser(id=ALICE, email="alice@example.com", role="authenticated", token=token_for(ALICE))


@pytest.fixture
def bob(store):
    return AuthUser(id=BOB, email="bob@example.com", role="authenticated", token=token_for(BOB))


@pytest.fixture
def alice_client(store, alice):
    return FakeSupabase(access_token=alice.token, store=store)


@pytest.fixture
def bob_client(store, bob):
    return FakeSupabase(access_token=bob.token, store=store)


def make_merchant(client, user, name="Alice Bakery"):
    return ws.create_merchant(client, user, {"name": name, "business_type": "Cafe"})


def upload_both(client, user, merchant_id):
    sales = ws.store_upload(
        client, user, merchant_id,
        content=SALES_CSV.encode(), filename="sales.csv", upload_type=up.SALES, mapping=None,
    )
    customers = ws.store_upload(
        client, user, merchant_id,
        content=CUSTOMERS_CSV.encode(), filename="customers.csv", upload_type=up.CUSTOMERS,
        mapping=None,
    )
    return sales, customers


# ==========================================================================
# Merchants
# ==========================================================================
def test_create_and_list_merchants(alice_client, alice):
    make_merchant(alice_client, alice)
    rows = ws.list_merchants(alice_client, alice)
    assert len(rows) == 1
    assert rows[0]["owner_id"] == ALICE
    assert rows[0]["currency"] == "INR"


def test_merchant_requires_a_name(alice_client, alice):
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.create_merchant(alice_client, alice, {"name": "   "})
    assert caught.value.status_code == 422


def test_currency_must_be_a_three_letter_code(alice_client, alice):
    with pytest.raises(ws.WorkspaceError):
        ws.create_merchant(alice_client, alice, {"name": "Shop", "currency": "rupees"})


def test_list_shows_only_your_own_merchants(alice_client, alice, bob_client, bob):
    make_merchant(alice_client, alice, "Alice Bakery")
    make_merchant(bob_client, bob, "Bob Electronics")

    assert [m["name"] for m in ws.list_merchants(alice_client, alice)] == ["Alice Bakery"]
    assert [m["name"] for m in ws.list_merchants(bob_client, bob)] == ["Bob Electronics"]


def test_another_users_merchant_reads_as_not_found(alice_client, alice, bob_client, bob):
    """404 rather than 403: confirming the id exists would leak information."""
    merchant = make_merchant(alice_client, alice)
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.get_merchant(bob_client, bob, merchant["id"])
    assert caught.value.status_code == 404


def test_another_user_cannot_update_your_merchant(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    with pytest.raises(ws.WorkspaceError):
        ws.update_merchant(bob_client, bob, merchant["id"], {"name": "Taken over"})
    assert ws.get_merchant(alice_client, alice, merchant["id"])["name"] == "Alice Bakery"


def test_another_user_cannot_delete_your_merchant(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    with pytest.raises(ws.WorkspaceError):
        ws.delete_merchant(bob_client, bob, merchant["id"])
    assert ws.get_merchant(alice_client, alice, merchant["id"])


def test_deleting_a_merchant_removes_its_data_and_files(alice_client, alice, store):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    assert store.objects

    ws.delete_merchant(alice_client, alice, merchant["id"])

    assert ws.list_merchants(alice_client, alice) == []
    assert store.rows("uploads") == []
    assert store.objects == {}


@pytest.mark.parametrize("bad", ["../../etc/passwd", "not-a-uuid", "", "1 OR 1=1"])
def test_non_uuid_identifiers_are_rejected(alice_client, alice, bad):
    """Ids become storage paths, so anything path-like must fail to parse."""
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.get_merchant(alice_client, alice, bad)
    assert caught.value.status_code == 400


# ==========================================================================
# Uploads
# ==========================================================================
def test_valid_upload_is_stored_privately(alice_client, alice, store):
    merchant = make_merchant(alice_client, alice)
    upload = ws.store_upload(
        alice_client, alice, merchant["id"],
        content=SALES_CSV.encode(), filename="sales.csv", upload_type=up.SALES, mapping=None,
    )

    assert upload["status"] == "ready"
    assert upload["row_count"] == 56
    # The object path starts with the owner's id, which is what the storage
    # policy in 0003_storage.sql checks.
    assert upload["storage_path"].startswith(f"{ALICE}/")
    assert f"{settings.supabase_data_bucket}/{upload['storage_path']}" in store.objects


def test_invalid_upload_is_refused_and_nothing_is_stored(alice_client, alice, store):
    merchant = make_merchant(alice_client, alice)
    broken = SALES_CSV.replace("2026-03-05", "not-a-date")

    with pytest.raises(ws.WorkspaceError) as caught:
        ws.store_upload(
            alice_client, alice, merchant["id"],
            content=broken.encode(), filename="sales.csv", upload_type=up.SALES, mapping=None,
        )

    assert caught.value.status_code == 422
    assert store.rows("uploads") == []
    assert store.objects == {}


def test_repeating_an_upload_with_the_same_key_does_not_duplicate_it(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    first = ws.store_upload(
        alice_client, alice, merchant["id"], content=SALES_CSV.encode(), filename="s.csv",
        upload_type=up.SALES, mapping=None, idempotency_key="retry-1",
    )
    second = ws.store_upload(
        alice_client, alice, merchant["id"], content=SALES_CSV.encode(), filename="s.csv",
        upload_type=up.SALES, mapping=None, idempotency_key="retry-1",
    )
    assert first["id"] == second["id"]
    assert len(ws.list_uploads(alice_client, alice, merchant["id"])) == 1


def test_cannot_upload_to_another_users_merchant(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.store_upload(
            bob_client, bob, merchant["id"], content=SALES_CSV.encode(), filename="s.csv",
            upload_type=up.SALES, mapping=None,
        )
    assert caught.value.status_code == 404


def test_cannot_read_another_users_upload(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    sales, _ = upload_both(alice_client, alice, merchant["id"])
    with pytest.raises(ws.WorkspaceError):
        ws.get_upload(bob_client, bob, merchant["id"], sales["id"])


def test_upload_filenames_are_made_safe(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    upload = ws.store_upload(
        alice_client, alice, merchant["id"], content=SALES_CSV.encode(),
        filename="../../../etc/passwd.csv", upload_type=up.SALES, mapping=None,
    )
    assert "/" not in upload["original_filename"]
    assert ".." not in upload["original_filename"]


# ==========================================================================
# Analysis
# ==========================================================================
def test_analysis_requires_both_files(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    ws.store_upload(
        alice_client, alice, merchant["id"], content=SALES_CSV.encode(), filename="s.csv",
        upload_type=up.SALES, mapping=None,
    )
    with pytest.raises(ws.WorkspaceError) as caught:
        ws.run_analysis(alice_client, alice, merchant["id"])
    assert caught.value.status_code == 409
    assert "customer" in str(caught.value)


def test_uploaded_data_produces_the_expected_metrics(alice_client, alice):
    """The headline figures must match the uploaded file, not an approximation."""
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])

    run = ws.run_analysis(alice_client, alice, merchant["id"])
    summary = run["summary"]

    assert run["status"] == "completed"
    assert summary["total_revenue"] == pytest.approx(EXPECTED_REVENUE, rel=1e-6)
    assert summary["total_orders"] == EXPECTED_ORDERS
    assert summary["total_profit"] == pytest.approx(EXPECTED_PROFIT, rel=1e-6)
    assert summary["days"] == 28


def test_analysis_produces_every_section(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    for section in ("summary", "daily", "products", "categories", "inventory",
                    "insights", "recommendations", "action_plan", "forecast"):
        assert run[section] is not None, section

    assert len(run["daily"]) == 28
    assert {row["product"] for row in run["products"]} == {"Widget A", "Widget B"}


def test_recommendations_reference_real_findings(alice_client, alice):
    """Traceability: every action points back at a finding that exists."""
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    finding_ids = {f["id"] for f in run["insights"]["findings"]}
    plan = run["action_plan"]
    items = [*plan["high"], *plan["medium"], *plan["low"]]

    assert items, "expected at least one action for this dataset"
    for item in items:
        assert item["source_finding"] in finding_ids
        assert item["reason"]


def test_forecast_reports_insufficient_history_rather_than_guessing(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    short_sales = "date,product,category,orders,units_sold,revenue,expenses,inventory\n" + "".join(
        f"2026-03-{day:02d},Widget A,Tools,4,5,500,250,{100 - day}\n" for day in range(1, 6)
    )
    short_customers = "date,customers,new_customers,repeat_customers\n" + "".join(
        f"2026-03-{day:02d},4,2,2\n" for day in range(1, 6)
    )
    ws.store_upload(alice_client, alice, merchant["id"], content=short_sales.encode(),
                    filename="s.csv", upload_type=up.SALES, mapping=None)
    ws.store_upload(alice_client, alice, merchant["id"], content=short_customers.encode(),
                    filename="c.csv", upload_type=up.CUSTOMERS, mapping=None)

    run = ws.run_analysis(alice_client, alice, merchant["id"])
    assert run["forecast"]["available"] is False
    assert run["forecast"]["reason"]


def test_analysis_respects_a_date_range(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(
        alice_client, alice, merchant["id"], start=date(2026, 3, 1), end=date(2026, 3, 14)
    )
    assert run["summary"]["days"] == 14
    assert run["date_start"] == "2026-03-01"
    assert run["date_end"] == "2026-03-14"


def test_repeated_analysis_with_the_same_key_is_not_duplicated(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])

    first = ws.run_analysis(alice_client, alice, merchant["id"], idempotency_key="run-1")
    second = ws.run_analysis(alice_client, alice, merchant["id"], idempotency_key="run-1")

    assert first["id"] == second["id"]
    assert len(ws.list_analyses(alice_client, alice, merchant["id"])) == 1


def test_cannot_run_an_analysis_on_another_users_merchant(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    with pytest.raises(ws.WorkspaceError):
        ws.run_analysis(bob_client, bob, merchant["id"])


def test_cannot_list_or_read_another_users_analyses(alice_client, alice, bob_client, bob):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    assert ws.list_analyses(bob_client, bob, merchant["id"]) == []
    with pytest.raises(ws.WorkspaceError):
        ws.get_analysis(bob_client, bob, merchant["id"], run["id"])


def test_analysis_json_has_no_nan(alice_client, alice):
    """NaN is not valid JSON; it must be converted before storage."""
    import json

    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    encoded = json.dumps(
        {k: v for k, v in run.items() if k != "id"}, allow_nan=False
    )
    assert "NaN" not in encoded


def test_two_users_analyses_do_not_mix(alice_client, alice, bob_client, bob):
    """The assistant and the dashboard read one merchant's data and no other."""
    alice_merchant = make_merchant(alice_client, alice, "Alice Bakery")
    bob_merchant = make_merchant(bob_client, bob, "Bob Electronics")
    upload_both(alice_client, alice, alice_merchant["id"])

    bob_sales = _sales_csv("Gadget X", "Gadget Y")
    ws.store_upload(bob_client, bob, bob_merchant["id"], content=bob_sales.encode(),
                    filename="s.csv", upload_type=up.SALES, mapping=None)
    ws.store_upload(bob_client, bob, bob_merchant["id"], content=CUSTOMERS_CSV.encode(),
                    filename="c.csv", upload_type=up.CUSTOMERS, mapping=None)

    alice_run = ws.run_analysis(alice_client, alice, alice_merchant["id"])
    bob_run = ws.run_analysis(bob_client, bob, bob_merchant["id"])

    assert {p["product"] for p in alice_run["products"]} == {"Widget A", "Widget B"}
    assert {p["product"] for p in bob_run["products"]} == {"Gadget X", "Gadget Y"}


# ==========================================================================
# Reports
# ==========================================================================
def test_report_pdf_is_generated_from_the_stored_analysis(alice_client, alice):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    pdf = build_report_pdf(merchant, run)

    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 2000


def test_report_never_contains_ids_paths_or_tokens(alice_client, alice):
    """A report is a business document, not a debug dump."""
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    pdf = build_report_pdf(merchant, run)

    for secret in (ALICE.encode(), merchant["id"].encode(), run["id"].encode(),
                   b"storage_path", b"owner_id", b"Bearer "):
        assert secret not in pdf, secret


def test_download_url_is_only_issued_to_the_owner(alice_client, alice, bob_client, bob, store):
    merchant = make_merchant(alice_client, alice)
    upload_both(alice_client, alice, merchant["id"])
    run = ws.run_analysis(alice_client, alice, merchant["id"])

    report_id = "cccccccc-3333-4333-8333-cccccccccccc"
    path = ws.storage_path_for_report(ALICE, merchant["id"], report_id)
    alice_client.upload_object(settings.supabase_reports_bucket, path, b"%PDF-1.4", "application/pdf")
    alice_client.insert(ws.REPORTS, {
        "id": report_id, "merchant_id": merchant["id"], "owner_id": ALICE,
        "analysis_run_id": run["id"], "format": "pdf", "storage_path": path,
    })

    assert ws.report_download_url(alice_client, alice, merchant["id"], report_id)

    with pytest.raises(ws.WorkspaceError):
        ws.report_download_url(bob_client, bob, merchant["id"], report_id)


def test_tampered_storage_path_is_refused(alice_client, alice, bob_client, bob, store):
    """A row pointing at someone else's object must not produce a signed URL."""
    alice_merchant = make_merchant(alice_client, alice)
    bob_merchant = make_merchant(bob_client, bob)

    report_id = "dddddddd-4444-4444-8444-dddddddddddd"
    bob_client.insert(ws.REPORTS, {
        "id": report_id, "merchant_id": bob_merchant["id"], "owner_id": BOB,
        "format": "pdf",
        # Bob points his row at a path inside Alice's folder.
        "storage_path": ws.storage_path_for_report(ALICE, alice_merchant["id"], report_id),
    })

    with pytest.raises(ws.WorkspaceError) as caught:
        ws.report_download_url(bob_client, bob, bob_merchant["id"], report_id)
    assert caught.value.status_code == 409


# ==========================================================================
# The public demo is untouched
# ==========================================================================
def test_demo_dataset_still_loads_and_analyses():
    """The private workspace must not have changed the public path."""
    from backend.app.services.analysis import analyse
    from backend.app.services.data_loader import get_dataset
    from backend.app.services.metrics import summary_metrics, filter_dataset

    dataset = get_dataset()
    assert "M001" in dataset.merchant_ids

    scoped = filter_dataset(dataset, merchant_id="M001")
    summary = summary_metrics(scoped)
    assert summary["total_revenue"] > 0

    report = analyse(dataset, "M001")
    assert report.has_data
