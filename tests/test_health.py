"""Foundation smoke test: the API boots and answers."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_endpoint_responds():
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "MerchantAI"
    # No key is configured in Stage 1, so the assistant must stay off.
    assert body["llm_enabled"] is False


def test_root_endpoint_responds():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["app"] == "MerchantAI"
