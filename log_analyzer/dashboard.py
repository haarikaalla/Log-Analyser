"""
dashboard.py
Minimal FastAPI dashboard that surfaces the analysis report in a browser.

Run:
    uvicorn log_analyzer.dashboard:app --reload
Then open http://127.0.0.1:8000  (upload or point it at a log file via ?path=)
"""

from dataclasses import asdict
from html import escape
import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .parser import parse_file
from .analyzer import analyze
from .store import get_run, list_runs, save_run

app = FastAPI(title="Log Analyzer Dashboard")

DEFAULT_LOG = str(Path(__file__).resolve().parent.parent / "sample_logs" / "app.log")


@app.get("/health")
def health():
    return {"status": "ok"}


def _load_report(path: str):
    """Only serve logs from the configured directory, including through symlinks."""
    allowed_dir = Path(os.environ.get("LOG_ANALYZER_ALLOWED_DIR", Path(DEFAULT_LOG).parent)).resolve()
    requested = Path(path).resolve()
    if not requested.is_relative_to(allowed_dir):
        raise HTTPException(status_code=403, detail="Log path is outside the allowed directory")
    if not requested.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    max_bytes = int(os.environ.get("LOG_ANALYZER_MAX_BYTES", "52428800"))
    if requested.stat().st_size > max_bytes:
        raise HTTPException(status_code=413, detail="Log file exceeds size limit")
    try:
        records = parse_file(str(requested))
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Unable to read log file") from exc
    return analyze(records)


def _require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.environ.get("LOG_ANALYZER_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Set LOG_ANALYZER_API_KEY to enable run history")
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _row(cells):
    return "<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in cells) + "</tr>"


@app.get("/", response_class=HTMLResponse)
def dashboard(path: str = Query(default=DEFAULT_LOG, description="Path to a log file on disk")):
    report = _load_report(path)
    if report.total_lines == 0:
        return HTMLResponse("<h2>No parseable lines found</h2>", status_code=404)

    cluster_rows = "".join(
        _row([c.count, c.signature, (c.sample_message or "")[:80], c.first_seen, c.last_seen])
        for c in report.clusters[:15]
    )
    anomaly_rows = "".join(
        _row([a.severity.upper(), a.kind, a.detail, a.window_start, a.window_end])
        for a in report.anomalies
    )
    slow_rows = "".join(
        _row([e["endpoint"], f"{e['avg_ms']} ms", f"{e['max_ms']} ms", e["requests"]])
        for e in report.slowest_endpoints
    )

    html = f"""
    <html>
    <head>
        <title>Log Analyzer Dashboard</title>
        <style>
            body {{ font-family: -apple-system, Arial, sans-serif; margin: 2rem; color: #222; }}
            h1 {{ margin-bottom: 0; }}
            .subtitle {{ color: #666; margin-top: 0.25rem; }}
            .stat-row {{ display: flex; gap: 2rem; margin: 1.5rem 0; }}
            .stat {{ background: #f4f6f8; border-radius: 8px; padding: 1rem 1.5rem; }}
            .stat .value {{ font-size: 1.6rem; font-weight: 700; }}
            .stat .label {{ color: #666; font-size: 0.85rem; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
            th, td {{ border-bottom: 1px solid #e0e0e0; text-align: left; padding: 0.5rem 0.75rem; font-size: 0.9rem; }}
            th {{ background: #fafafa; }}
            h2 {{ margin-top: 2rem; }}
        </style>
    </head>
    <body>
        <h1>Log Analyzer Dashboard</h1>
        <div class="subtitle">Source: {escape(path)}</div>
        <div class="stat-row">
            <div class="stat"><div class="value">{report.total_lines}</div><div class="label">Lines parsed</div></div>
            <div class="stat"><div class="value">{report.total_errors}</div><div class="label">Errors</div></div>
            <div class="stat"><div class="value">{report.error_rate}%</div><div class="label">Error rate</div></div>
            <div class="stat"><div class="value">{len(report.anomalies)}</div><div class="label">Anomalies</div></div>
        </div>

        <h2>Anomalies</h2>
        <table>
            <tr><th>Severity</th><th>Type</th><th>Detail</th><th>Start</th><th>End</th></tr>
            {anomaly_rows or '<tr><td colspan="5">None detected</td></tr>'}
        </table>

        <h2>Top Error Clusters</h2>
        <table>
            <tr><th>Count</th><th>Signature</th><th>Sample message</th><th>First seen</th><th>Last seen</th></tr>
            {cluster_rows or '<tr><td colspan="5">None found</td></tr>'}
        </table>

        <h2>Slowest Endpoints</h2>
        <table>
            <tr><th>Endpoint</th><th>Avg</th><th>Max</th><th>Requests</th></tr>
            {slow_rows or '<tr><td colspan="4">No timing data</td></tr>'}
        </table>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/api/report")
def api_report(path: str = Query(default=DEFAULT_LOG)):
    return asdict(_load_report(path))


@app.post("/api/runs", dependencies=[Depends(_require_api_key)])
def create_run(path: str = Query(default=DEFAULT_LOG)):
    report = _load_report(path)
    if not report.total_lines:
        raise HTTPException(status_code=422, detail="No parseable log lines found")
    run_id = save_run(report, path)
    return {"id": run_id, "source_name": Path(path).name, "report": asdict(report)}


@app.get("/api/runs", dependencies=[Depends(_require_api_key)])
def recent_runs(limit: int = Query(default=20, ge=1, le=100)):
    return list_runs(limit=limit)


@app.get("/api/runs/{run_id}", dependencies=[Depends(_require_api_key)])
def stored_run(run_id: str):
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return run
