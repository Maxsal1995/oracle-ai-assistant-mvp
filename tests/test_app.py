from fastapi.testclient import TestClient

from app.main import app


def test_application_starts_and_serves_local_ui() -> None:
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {
            "status": "ok",
            "database_connection": False,
        }

        page = client.get("/")
        assert page.status_code == 200
        assert "Oracle AI Assistant" in page.text

        profiles = client.get("/api/profiles")
        assert profiles.status_code == 200
        assert isinstance(profiles.json(), list)
