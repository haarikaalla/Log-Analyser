from fastapi.testclient import TestClient

from log_analyzer.dashboard import app
from log_analyzer.store import get_run, list_runs


LOG_LINE = (
    "2026-07-04 09:31:00,000 ERROR [order-service] "
    "GET /api/orders/394 -> 500 (198ms) boom\n"
)


def test_authenticated_run_history_is_idempotent(tmp_path, monkeypatch):
    log = tmp_path / "incident.log"
    log.write_text(LOG_LINE)
    monkeypatch.setenv("LOG_ANALYZER_ALLOWED_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_ANALYZER_DB_PATH", str(tmp_path / "history.db"))
    monkeypatch.setenv("LOG_ANALYZER_API_KEY", "test-secret")
    client = TestClient(app)

    assert client.post("/api/runs", params={"path": str(log)}).status_code == 401
    headers = {"X-API-Key": "test-secret"}
    first = client.post("/api/runs", params={"path": str(log)}, headers=headers)
    second = client.post("/api/runs", params={"path": str(log)}, headers=headers)

    assert first.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["report"]["total_errors"] == 1
    assert len(client.get("/api/runs", headers=headers).json()) == 1
    run_id = first.json()["id"]
    assert client.get(f"/api/runs/{run_id}", headers=headers).json()["report"]["total_errors"] == 1
    assert client.get("/api/runs/missing", headers=headers).status_code == 404
    assert get_run(run_id, tmp_path / "history.db") is not None
    assert len(list_runs(path=tmp_path / "history.db")) == 1


def test_run_history_requires_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_ANALYZER_API_KEY", raising=False)
    monkeypatch.setenv("LOG_ANALYZER_DB_PATH", str(tmp_path / "history.db"))
    client = TestClient(app)

    assert client.get("/api/runs").status_code == 503


def test_web_file_size_limit(tmp_path, monkeypatch):
    log = tmp_path / "large.log"
    log.write_text(LOG_LINE)
    monkeypatch.setenv("LOG_ANALYZER_ALLOWED_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_ANALYZER_MAX_BYTES", "1")
    client = TestClient(app)

    assert client.get("/api/report", params={"path": str(log)}).status_code == 413


def test_health_endpoint():
    assert TestClient(app).get("/health").json() == {"status": "ok"}
