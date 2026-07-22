from fastapi.testclient import TestClient

from pfpd_ia.main import app


def test_liveness_does_not_depend_on_database() -> None:
    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
