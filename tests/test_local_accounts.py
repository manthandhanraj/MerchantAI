"""Built-in accounts: sign-up, sign-in, persistence, isolation, the full journey.

These run against the real HTTP API with a throwaway data directory (see
conftest), so they exercise exactly what a browser exercises: the password is
hashed, the token is signed and verified, rows and files are written to disk,
and every private route is confined to the caller's own data.
"""

from __future__ import annotations

import time

import jwt
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app.config import LOCAL_DEMO_USER_ID, settings
from backend.app.main import app
from backend.app.services import local_auth
from backend.app.services.local_store import LocalStore


@pytest.fixture(autouse=True)
def built_in_mode(monkeypatch):
    """Force built-in accounts regardless of any .env on this machine."""
    monkeypatch.setattr(settings, "auth_mode", "local")
    monkeypatch.setattr(settings, "demo_user_id", "")
    # Plenty of room for the tests that sign in repeatedly.
    monkeypatch.setattr(settings, "login_attempt_limit", 8)


@pytest.fixture
def client():
    return TestClient(app)


def signup(client, email="riya@example.com", password="bakery2026", name="Riya Sharma"):
    response = client.post(
        "/api/auth/signup", json={"email": email, "password": password, "full_name": name}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def merchant_csvs(source: str = "M002") -> tuple[bytes, bytes]:
    sales = pd.read_csv(settings.sales_path, dtype=str)
    customers = pd.read_csv(settings.customers_path, dtype=str)
    sales = sales[sales.merchant_id == source].drop(columns=["merchant_id"])
    customers = customers[customers.merchant_id == source].drop(columns=["merchant_id"])
    return sales.to_csv(index=False).encode(), customers.to_csv(index=False).encode()


def upload(client, headers, merchant_id, kind, content, key=None):
    return client.post(
        f"/api/my/merchants/{merchant_id}/uploads",
        headers=headers,
        files={"file": (f"{kind}.csv", content, "text/csv")},
        data={"upload_type": kind, **({"idempotency_key": key} if key else {})},
    )


# ==========================================================================
# Passwords
# ==========================================================================
def test_password_is_never_stored_in_plain_text():
    stored = local_auth.hash_password("bakery2026")
    assert "bakery2026" not in stored
    assert stored.startswith("scrypt$")


def test_same_password_hashes_differently_each_time():
    """A random salt per account: identical passwords do not look identical."""
    assert local_auth.hash_password("bakery2026") != local_auth.hash_password("bakery2026")


def test_password_verification():
    stored = local_auth.hash_password("bakery2026")
    assert local_auth.verify_password("bakery2026", stored)
    assert not local_auth.verify_password("bakery2027", stored)
    assert not local_auth.verify_password("", stored)
    assert not local_auth.verify_password("bakery2026", "not-a-hash")


def test_database_holds_no_plain_text_password(client):
    signup(client, password="secret-bakery-99")
    raw = local_auth.db_path().read_bytes()
    assert b"secret-bakery-99" not in raw


# ==========================================================================
# Sign-up
# ==========================================================================
def test_signup_creates_an_account_and_signs_it_in(client):
    body, headers = signup(client)
    assert body["user"]["email"] == "riya@example.com"
    assert body["user"]["user_metadata"]["full_name"] == "Riya Sharma"
    assert body["expires_at"] > time.time()

    me = client.get("/api/me", headers=headers).json()
    assert me["profile"]["full_name"] == "Riya Sharma"
    assert me["auth_mode"] == "local"


def test_email_is_case_insensitive(client):
    signup(client, email="Riya@Example.COM")
    duplicate = client.post(
        "/api/auth/signup", json={"email": "riya@example.com", "password": "bakery2026"}
    )
    assert duplicate.status_code == 409


def test_duplicate_signup_gets_a_readable_message(client):
    signup(client)
    response = client.post(
        "/api/auth/signup", json={"email": "riya@example.com", "password": "another2026"}
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.parametrize(
    "password,reason",
    [
        ("short1", "at least 8"),
        ("onlyletters", "letter and one number"),
        ("12345678", "letter and one number"),
        ("x" * 200 + "1", "limited to"),
    ],
)
def test_weak_passwords_are_refused(client, password, reason):
    response = client.post(
        "/api/auth/signup", json={"email": "riya@example.com", "password": password}
    )
    assert response.status_code == 422
    assert reason in response.json()["detail"]


@pytest.mark.parametrize("email", ["", "not-an-email", "a@b", "spaces in@x.com"])
def test_invalid_emails_are_refused(client, email):
    response = client.post("/api/auth/signup", json={"email": email, "password": "bakery2026"})
    assert response.status_code == 422


def test_the_demo_address_cannot_be_registered(client):
    response = client.post(
        "/api/auth/signup",
        json={"email": settings.demo_user_email, "password": "bakery2026"},
    )
    assert response.status_code == 409


def test_a_new_account_starts_empty(client):
    """No demo data, no other user's data — a fresh workspace."""
    _, headers = signup(client)
    me = client.get("/api/me", headers=headers).json()
    assert me["needs_onboarding"] is True
    assert me["is_demo"] is False
    assert client.get("/api/my/merchants", headers=headers).json()["count"] == 0


# ==========================================================================
# Sign-in
# ==========================================================================
def test_signin_with_the_right_password(client):
    signup(client)
    response = client.post(
        "/api/auth/login", json={"email": "riya@example.com", "password": "bakery2026"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_wrong_password_and_unknown_email_look_identical(client):
    """Neither answer may reveal whether the account exists."""
    signup(client)
    wrong = client.post(
        "/api/auth/login", json={"email": "riya@example.com", "password": "bakery2027"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": "bakery2026"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_repeated_failures_are_throttled(client, monkeypatch):
    monkeypatch.setattr(settings, "login_attempt_limit", 3)
    signup(client)
    for _ in range(3):
        client.post("/api/auth/login", json={"email": "riya@example.com", "password": "nope1234"})

    blocked = client.post(
        "/api/auth/login", json={"email": "riya@example.com", "password": "bakery2026"}
    )
    assert blocked.status_code == 429
    assert "Too many attempts" in blocked.json()["detail"]


# ==========================================================================
# Tokens
# ==========================================================================
def test_signed_out_requests_are_refused(client):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/my/merchants").status_code == 401


def test_a_tampered_token_is_refused(client):
    body, _ = signup(client)
    token = body["access_token"]
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


def test_a_token_signed_with_another_secret_is_refused(client):
    body, _ = signup(client)
    forged = jwt.encode(
        {
            "sub": body["user"]["id"],
            "aud": "authenticated",
            "iss": "merchantai-local",
            "exp": int(time.time()) + 3600,
        },
        "attacker-secret",
        algorithm="HS256",
    )
    assert client.get("/api/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_an_expired_token_is_refused(client):
    body, _ = signup(client)
    expired = jwt.encode(
        {
            "sub": body["user"]["id"],
            "aud": "authenticated",
            "iss": "merchantai-local",
            "exp": int(time.time()) - 5,
        },
        local_auth.signing_secret(),
        algorithm="HS256",
    )
    assert client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_a_deleted_account_token_stops_working_at_once(client):
    _, headers = signup(client)
    assert client.delete("/api/auth/account", headers=headers).status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401


# ==========================================================================
# The whole journey, and that it survives a restart
# ==========================================================================
def test_full_journey_signup_to_downloaded_report(client):
    _, headers = signup(client)

    merchant = client.post(
        "/api/my/merchants", headers=headers, json={"name": "Gupta Kirana", "business_type": "Kirana"}
    ).json()["merchant"]

    sales, customers = merchant_csvs("M002")
    assert upload(client, headers, merchant["id"], "sales", sales).status_code == 201
    assert upload(client, headers, merchant["id"], "customers", customers).status_code == 201

    run = client.post(
        f"/api/my/merchants/{merchant['id']}/analyses", headers=headers, json={}
    ).json()["analysis"]
    assert run["status"] == "completed"

    dashboard = client.get(f"/api/my/merchants/{merchant['id']}/dashboard", headers=headers).json()
    # The committed dataset's own total for M002 — real figures, not placeholders.
    raw = pd.read_csv(settings.sales_path)
    expected = raw[raw.merchant_id == "M002"]["revenue"].sum()
    assert dashboard["summary"]["total_revenue"] == pytest.approx(expected, rel=1e-6)

    report = client.post(
        f"/api/my/merchants/{merchant['id']}/reports", headers=headers, json={}
    ).json()["report"]
    link = client.get(
        f"/api/my/merchants/{merchant['id']}/reports/{report['id']}/download", headers=headers
    ).json()["url"]

    pdf = client.get(link)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


def test_data_survives_a_restart(client):
    """Nothing is held only in memory: a fresh process finds it all again."""
    _, headers = signup(client)
    merchant = client.post("/api/my/merchants", headers=headers, json={"name": "Kept Shop"}).json()[
        "merchant"
    ]
    sales, customers = merchant_csvs("M003")
    upload(client, headers, merchant["id"], "sales", sales)
    upload(client, headers, merchant["id"], "customers", customers)
    client.post(f"/api/my/merchants/{merchant['id']}/analyses", headers=headers, json={})

    # Forget every in-memory cache, as a restarted server would.
    local_auth.reset_caches()
    fresh = TestClient(app)

    relogin = fresh.post(
        "/api/auth/login", json={"email": "riya@example.com", "password": "bakery2026"}
    )
    assert relogin.status_code == 200
    h = {"Authorization": f"Bearer {relogin.json()['access_token']}"}

    merchants = fresh.get("/api/my/merchants", headers=h).json()["merchants"]
    assert [m["name"] for m in merchants] == ["Kept Shop"]
    assert fresh.get(f"/api/my/merchants/{merchant['id']}/analyses", headers=h).json()["count"] == 1
    assert fresh.get(f"/api/my/merchants/{merchant['id']}/uploads", headers=h).json()["count"] == 2


def test_the_signing_secret_is_generated_once_and_kept(client):
    first = local_auth.signing_secret()
    local_auth.reset_caches()
    assert local_auth.signing_secret() == first
    assert len(first) >= 40


def test_duplicate_submissions_do_not_duplicate_records(client):
    _, headers = signup(client)
    merchant = client.post("/api/my/merchants", headers=headers, json={"name": "Shop"}).json()[
        "merchant"
    ]
    sales, _ = merchant_csvs("M001")
    first = upload(client, headers, merchant["id"], "sales", sales, key="same-click")
    second = upload(client, headers, merchant["id"], "sales", sales, key="same-click")
    assert first.json()["upload"]["id"] == second.json()["upload"]["id"]
    assert client.get(f"/api/my/merchants/{merchant['id']}/uploads", headers=headers).json()["count"] == 1


# ==========================================================================
# Isolation between accounts
# ==========================================================================
@pytest.fixture
def two_users(client):
    _, alice = signup(client, email="alice@example.com")
    _, bob = signup(client, email="bob@example.com")
    shop = client.post("/api/my/merchants", headers=alice, json={"name": "Alice Shop"}).json()[
        "merchant"
    ]
    sales, customers = merchant_csvs("M001")
    upload(client, alice, shop["id"], "sales", sales)
    upload(client, alice, shop["id"], "customers", customers)
    client.post(f"/api/my/merchants/{shop['id']}/analyses", headers=alice, json={})
    report = client.post(f"/api/my/merchants/{shop['id']}/reports", headers=alice, json={}).json()[
        "report"
    ]
    return alice, bob, shop, report


def test_user_b_cannot_see_user_a_merchants(client, two_users):
    _, bob, shop, _ = two_users
    assert client.get("/api/my/merchants", headers=bob).json()["count"] == 0
    assert client.get(f"/api/my/merchants/{shop['id']}", headers=bob).status_code == 404


def test_user_b_cannot_upload_to_user_a_merchant(client, two_users):
    _, bob, shop, _ = two_users
    sales, _ = merchant_csvs("M001")
    assert upload(client, bob, shop["id"], "sales", sales).status_code == 404


def test_user_b_cannot_run_analysis_for_user_a(client, two_users):
    _, bob, shop, _ = two_users
    response = client.post(f"/api/my/merchants/{shop['id']}/analyses", headers=bob, json={})
    assert response.status_code == 404


def test_user_b_cannot_list_or_download_user_a_reports(client, two_users):
    _, bob, shop, report = two_users
    assert client.get(f"/api/my/merchants/{shop['id']}/reports", headers=bob).json()["count"] == 0
    response = client.get(
        f"/api/my/merchants/{shop['id']}/reports/{report['id']}/download", headers=bob
    )
    assert response.status_code == 404


def test_store_cannot_write_rows_for_someone_else(client, two_users):
    """The RLS equivalent: a store refuses a row owned by another user."""
    _, _, shop, _ = two_users
    bob_id = local_auth.find_user_by_email("bob@example.com").id
    from backend.app.services.supabase_client import SupabaseError

    with pytest.raises(SupabaseError):
        LocalStore(user_id=bob_id).insert(
            "uploads",
            {"merchant_id": shop["id"], "owner_id": bob_id, "upload_type": "sales",
             "original_filename": "x.csv", "storage_path": f"{bob_id}/x"},
        )


def test_deleting_one_account_leaves_the_other_intact(client, two_users):
    alice, bob, shop, _ = two_users
    bob_shop = client.post("/api/my/merchants", headers=bob, json={"name": "Bob Shop"}).json()[
        "merchant"
    ]

    assert client.delete("/api/auth/account", headers=bob).status_code == 204

    assert client.get(f"/api/my/merchants/{shop['id']}", headers=alice).status_code == 200
    assert client.get("/api/my/merchants", headers=alice).json()["count"] == 1
    assert local_auth.find_user_by_email("bob@example.com") is None
    assert bob_shop["id"] not in str(client.get("/api/my/merchants", headers=alice).json())


def test_deleting_an_account_removes_its_files(client, two_users):
    alice, _, _, _ = two_users
    alice_id = local_auth.find_user_by_email("alice@example.com").id
    folders = [
        local_auth.data_dir() / "storage" / bucket / alice_id
        for bucket in ("merchant-data", "merchant-reports")
    ]
    assert any(folder.exists() and any(folder.rglob("*")) for folder in folders)

    client.delete("/api/auth/account", headers=alice)
    assert not any(folder.exists() and any(folder.rglob("*")) for folder in folders)


# ==========================================================================
# Signed download links
# ==========================================================================
def test_download_link_is_signed_and_single_file(client, two_users):
    _, _, _, report = two_users
    bucket, path = "merchant-reports", report["storage_path"]
    reference = local_auth.sign_file_reference(bucket, path, 60)

    assert client.get(f"/api/files/{reference}").status_code == 200

    body, signature = reference.rsplit(".", 1)
    forged = f"{body}.{'0' * len(signature)}"
    assert client.get(f"/api/files/{forged}").status_code == 403


def test_expired_download_link_is_refused(client, two_users):
    _, _, _, report = two_users
    reference = local_auth.sign_file_reference("merchant-reports", report["storage_path"], -1)
    response = client.get(f"/api/files/{reference}")
    assert response.status_code == 403
    assert "expired" in response.json()["detail"]


def test_path_traversal_is_refused():
    from backend.app.services.supabase_client import SupabaseError

    store = LocalStore(user_id="aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
    for bad in (
        "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa/../../../secret",
        "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb/x/report.pdf",
        "../etc/passwd",
    ):
        with pytest.raises(SupabaseError):
            store.upload_object("merchant-reports", bad, b"x", "application/pdf")


# ==========================================================================
# Password changes
# ==========================================================================
def test_change_password(client):
    _, headers = signup(client)
    assert (
        client.post("/api/auth/password", headers=headers, json={"password": "newbakery99"}).status_code
        == 200
    )
    old = client.post("/api/auth/login", json={"email": "riya@example.com", "password": "bakery2026"})
    new = client.post("/api/auth/login", json={"email": "riya@example.com", "password": "newbakery99"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_administrator_reset(client):
    signup(client)
    local_auth.set_password("riya@example.com", "resetbakery1")
    response = client.post(
        "/api/auth/login", json={"email": "riya@example.com", "password": "resetbakery1"}
    )
    assert response.status_code == 200


# ==========================================================================
# The demo account
# ==========================================================================
def test_demo_credentials_are_published(client):
    body = client.get("/api/auth/demo").json()
    assert body["available"] is True
    assert body["email"] == settings.demo_user_email
    assert body["password"] == settings.demo_password


def test_serverless_demo_uses_stateless_workspace(client, monkeypatch):
    monkeypatch.setattr(settings, "local_data_dir", "")
    monkeypatch.setenv("VERCEL", "1")

    body = client.get("/api/auth/demo").json()

    assert body["available"] is True
    assert body["workspace_url"] == "/demo"


def test_demo_login_seeds_a_populated_workspace(client):
    creds = client.get("/api/auth/demo").json()
    response = client.post(
        "/api/auth/login", json={"email": creds["email"], "password": creds["password"]}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    me = client.get("/api/me", headers=headers).json()
    assert me["is_demo"] is True and me["read_only"] is True
    assert me["needs_onboarding"] is False

    merchants = client.get("/api/my/merchants", headers=headers).json()["merchants"]
    assert len(merchants) == 1 and merchants[0]["is_demo"] is True

    dashboard = client.get(f"/api/my/merchants/{merchants[0]['id']}/dashboard", headers=headers).json()
    assert dashboard["summary"]["total_revenue"] > 0
    reports = client.get(f"/api/my/merchants/{merchants[0]['id']}/reports", headers=headers).json()
    assert reports["count"] >= 1


def test_demo_seeding_is_idempotent(client):
    creds = client.get("/api/auth/demo").json()
    for _ in range(3):
        client.post("/api/auth/login", json={"email": creds["email"], "password": creds["password"]})

    store = LocalStore(user_id=LOCAL_DEMO_USER_ID)
    assert len(store.select("merchants")) == 1
    assert len(store.select("uploads")) == 2
    assert len(store.select("analysis_runs")) == 1


def test_demo_is_read_only(client):
    creds = client.get("/api/auth/demo").json()
    token = client.post(
        "/api/auth/login", json={"email": creds["email"], "password": creds["password"]}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/my/merchants", headers=headers, json={"name": "x"}).status_code == 403
    assert client.post("/api/auth/password", headers=headers, json={"password": "hijack123"}).status_code == 403
    assert client.delete("/api/auth/account", headers=headers).status_code == 403


def test_demo_data_never_appears_in_a_real_account(client):
    creds = client.get("/api/auth/demo").json()
    client.post("/api/auth/login", json={"email": creds["email"], "password": creds["password"]})

    _, headers = signup(client)
    assert client.get("/api/my/merchants", headers=headers).json()["count"] == 0


def test_supabase_mode_refuses_built_in_signup(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "supabase")
    response = client.post(
        "/api/auth/signup", json={"email": "x@example.com", "password": "bakery2026"}
    )
    assert response.status_code == 409
    assert client.get("/api/auth/demo").json()["available"] is False
