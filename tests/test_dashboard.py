import pytest
from fastapi import HTTPException

from log_analyzer.dashboard import api_report, dashboard


LOG_LINE = (
    "2026-07-04 09:31:00,000 ERROR [order-service] "
    "GET /api/orders/394 -> 500 (198ms) <script>alert(1)</script>\n"
)


def test_dashboard_escapes_untrusted_log_content(tmp_path, monkeypatch):
    log = tmp_path / "incident.log"
    log.write_text(LOG_LINE)
    monkeypatch.setenv("LOG_ANALYZER_ALLOWED_DIR", str(tmp_path))

    response = dashboard(path=str(log))

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.body.decode()
    assert "<script>" not in response.body.decode()
    assert api_report(path=str(log))["total_errors"] == 1


def test_dashboard_rejects_paths_outside_allowed_directory(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "private.log"
    outside.write_text(LOG_LINE)
    monkeypatch.setenv("LOG_ANALYZER_ALLOWED_DIR", str(allowed))

    with pytest.raises(HTTPException) as error:
        api_report(path=str(outside))
    assert error.value.status_code == 403

    (allowed / "linked.log").symlink_to(outside)
    with pytest.raises(HTTPException) as error:
        dashboard(path=str(allowed / "linked.log"))
    assert error.value.status_code == 403


def test_dashboard_reports_missing_allowed_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_ANALYZER_ALLOWED_DIR", str(tmp_path))

    with pytest.raises(HTTPException) as error:
        api_report(path=str(tmp_path / "missing.log"))
    assert error.value.status_code == 404
