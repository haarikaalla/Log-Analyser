"""SQLite-backed snapshots of analyzed incidents.

Only report summaries are stored; raw log lines are never copied into the DB.
The same source and report content produce the same run ID, so retries are safe.
"""

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from .analyzer import AnalysisReport


def database_path() -> Path:
    return Path(os.environ.get("LOG_ANALYZER_DB_PATH", "log_analyzer.db"))


def _serialize_report(report: AnalysisReport) -> str:
    return json.dumps(
        asdict(report),
        default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        sort_keys=True,
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            total_lines INTEGER NOT NULL,
            total_errors INTEGER NOT NULL,
            anomaly_count INTEGER NOT NULL,
            report_json TEXT NOT NULL
        )"""
    )
    return connection


def save_run(report: AnalysisReport, source: str, path: Path | None = None) -> str:
    """Persist an analysis summary and return its stable ID."""
    source_name = Path(source).name
    payload = _serialize_report(report)
    run_id = hashlib.sha256(f"{source_name}\0{payload}".encode()).hexdigest()
    with closing(_connect(path or database_path())) as connection:
        with connection:
            connection.execute(
                """INSERT OR IGNORE INTO runs
                (id, source_name, created_at, total_lines, total_errors, anomaly_count, report_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    source_name,
                    datetime.now(timezone.utc).isoformat(),
                    report.total_lines,
                    report.total_errors,
                    len(report.anomalies),
                    payload,
                ),
            )
    return run_id


def list_runs(limit: int = 20, path: Path | None = None) -> list[dict]:
    """Return recent run summaries without exposing stored report content."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with closing(_connect(path or database_path())) as connection:
        rows = connection.execute(
            """SELECT id, source_name, created_at, total_lines, total_errors, anomaly_count
            FROM runs ORDER BY created_at DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: str, path: Path | None = None) -> dict | None:
    """Retrieve a stored analysis, or None when its ID is unknown."""
    with closing(_connect(path or database_path())) as connection:
        row = connection.execute(
            "SELECT id, source_name, created_at, report_json FROM runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "source_name": row["source_name"],
        "created_at": row["created_at"],
        "report": json.loads(row["report_json"]),
    }
