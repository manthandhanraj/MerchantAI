"""The shared demo account is read-only, and enforced on the server.

The demo is one record that everyone who clicks "Try demo account" lands in.
If a visitor could delete its merchant or change its data, the next visitor
would find it broken. Hiding the buttons stops an honest visitor; these tests
cover everyone else.

Read access is deliberately unaffected — the demo has to be able to show a
populated dashboard and hand over a report.
"""

from __future__ import annotations

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.config import settings
from backend.app.main import app
from backend.app.services import auth
from backend.app.services import workspace as ws

SECRET = "demo-mode-test-secret"
DEMO_USER = "dddddddd-0000-4000-8000-dddddddddddd"
REAL_USER = "eeeeeeee-0000-4000-8000-eeeeeeeeeeee"
MERCHANT = "11111111-2222-4222-8222-333333333333"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "https://project.supabase.co")
    monkeypatch.setattr(settings, "supabase_anon_key", "anon-key")
    monkeypatch.setattr(settings, "supabase_jwt_secret", SECRET)
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    monkeypatch.setattr(settings, "demo_user_id", DEMO_USER)
    auth.reset_jwks_cache()


def token(subject: str) -> str:
    return jwt.encode(
        {
            "sub": subject,
            "email": "someone@example.com",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
        SECRET,
        algorithm="HS256",
    )


def headers(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(subject)}"}


# ---------------------------------------------------------------- settings
def test_only_the_configured_id_is_the_demo():
    assert settings.is_demo_user(DEMO_USER) is True
    assert settings.is_demo_user(REAL_USER) is False


def test_no_one_is_the_demo_when_none_is_configured(monkeypatch):
    """An unconfigured deployment must not accidentally lock a real user out."""
    monkeypatch.setattr(settings, "demo_user_id", "")
    assert settings.is_demo_user(DEMO_USER) is False
    assert settings.is_demo_user("") is False


# ------------------------------------------------------- mutations refused
MUTATIONS = [
    ("post", "/api/my/merchants", {"json": {"name": "Taken over"}}),
    ("patch", f"/api/my/merchants/{MERCHANT}", {"json": {"name": "Renamed"}}),
    ("delete", f"/api/my/merchants/{MERCHANT}", {}),
    ("post", f"/api/my/merchants/{MERCHANT}/analyses", {"json": {}}),
    ("delete", f"/api/my/merchants/{MERCHANT}/reports/{MERCHANT}", {}),
    ("patch", "/api/me", {"json": {"full_name": "Someone Else"}}),
]


@pytest.mark.parametrize("method,path,kwargs", MUTATIONS)
def test_demo_account_cannot_mutate_anything(client, method, path, kwargs):
    response = getattr(client, method)(path, headers=headers(DEMO_USER), **kwargs)
    assert response.status_code == 403
    assert "read-only" in response.json()["detail"].lower()


def test_demo_account_cannot_upload(client):
    response = client.post(
        f"/api/my/merchants/{MERCHANT}/uploads",
        headers=headers(DEMO_USER),
        files={"file": ("sales.csv", b"date,product\n2026-01-01,Widget\n", "text/csv")},
        data={"upload_type": "sales"},
    )
    assert response.status_code == 403


def test_the_refusal_explains_itself_and_offers_a_way_forward(client):
    detail = client.post(
        "/api/my/merchants", headers=headers(DEMO_USER), json={"name": "x"}
    ).json()["detail"]
    assert "demo" in detail.lower()
    assert "account" in detail.lower()
    # No internal identifier leaks into a message a visitor will read.
    assert DEMO_USER not in detail


# ------------------------------------------------- real users are unaffected
@pytest.mark.parametrize("method,path,kwargs", MUTATIONS)
def test_a_real_user_is_not_blocked_by_demo_mode(client, method, path, kwargs):
    """The guard must reject the demo id and nothing else.

    A real caller gets past it and fails later, on data access — never 403
    from the demo guard.
    """
    response = getattr(client, method)(path, headers=headers(REAL_USER), **kwargs)
    assert response.status_code != 403


# ------------------------------------------------------- reads still work
@pytest.mark.parametrize(
    "path",
    [
        "/api/my/merchants",
        "/api/my/assistant/status",
        f"/api/my/merchants/{MERCHANT}/reports",
    ],
)
def test_demo_account_can_still_read(client, path):
    """A read must never be refused by the demo guard itself."""
    response = client.get(path, headers=headers(DEMO_USER))
    assert response.status_code != 403


def test_demo_account_can_still_generate_a_report(client):
    """Downloading a report is part of the demo journey, so it stays allowed."""
    response = client.post(
        f"/api/my/merchants/{MERCHANT}/reports", headers=headers(DEMO_USER), json={}
    )
    assert response.status_code != 403


# ------------------------------------------------------------ onboarding
def test_a_demo_visitor_is_never_sent_to_onboarding(monkeypatch):
    """They cannot create a merchant, so the form would be a dead end."""
    from backend.app.routes import workspace as routes

    class _Client:
        def select(self, *args, **kwargs):
            return {"id": DEMO_USER, "full_name": "MerchantAI Demo"} if kwargs.get("single") else []

        def insert(self, *args, **kwargs):  # pragma: no cover - not reached
            raise AssertionError("should not insert")

    user = auth.AuthUser(id=DEMO_USER, email="demo@x", role="authenticated", token="t")
    body = routes.me(user, _Client())

    assert body["is_demo"] is True
    assert body["read_only"] is True
    assert body["needs_onboarding"] is False


def test_a_real_user_with_no_merchants_is_sent_to_onboarding():
    from backend.app.routes import workspace as routes

    class _Client:
        def select(self, *args, **kwargs):
            return {"id": REAL_USER, "full_name": None} if kwargs.get("single") else []

    user = auth.AuthUser(id=REAL_USER, email="new@x", role="authenticated", token="t")
    body = routes.me(user, _Client())

    assert body["is_demo"] is False
    assert body["needs_onboarding"] is True
    assert body["merchant_count"] == 0
