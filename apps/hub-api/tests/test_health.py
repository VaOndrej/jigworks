from fastapi.testclient import TestClient

from hub_api.main import app


def test_health_is_ok():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
