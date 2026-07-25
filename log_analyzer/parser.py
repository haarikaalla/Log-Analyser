"""
parser.py
Parses raw application log lines into structured records.

Supports two common formats out of the box:
  1. App/service logs:   2026-07-04 12:03:11,204 ERROR [order-service] GET /api/orders/883 -> 500 (812ms) TimeoutError: upstream did not respond
  2. Nginx/Apache-style access logs (combined log format)

Returns a list of dicts with normalized fields:
  timestamp, level, service, method, endpoint, status, duration_ms, message
"""

import re
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List


APP_LOG_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"\[(?P<service>[^\]]+)\]\s+"
    r"(?P<method>[A-Z]+)\s+"
    r"(?P<endpoint>\S+)\s+->\s+"
    r"(?P<status>\d{3})\s+"
    r"\((?P<duration>\d+)ms\)"
    r"(?:\s+(?P<message>.*))?$"
)

ACCESS_LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<endpoint>\S+) \S+" '
    r'(?P<status>\d{3}) (?P<size>\S+)'
)


@dataclass
class LogRecord:
    timestamp: Optional[datetime]
    level: str
    service: Optional[str]
    method: Optional[str]
    endpoint: Optional[str]
    status: Optional[int]
    duration_ms: Optional[int]
    message: str
    raw: str


def _parse_app_timestamp(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f")


def _parse_access_timestamp(ts: str) -> datetime:
    # e.g. 04/Jul/2026:12:03:11 +0000
    return datetime.strptime(ts.split(" ")[0], "%d/%b/%Y:%H:%M:%S")


def parse_line(line: str) -> Optional[LogRecord]:
    """Parse a single log line. Returns None if it matches no known format."""
    line = line.rstrip("\n")
    if not line.strip():
        return None

    m = APP_LOG_RE.match(line)
    if m:
        d = m.groupdict()
        status = int(d["status"])
        level = d["level"]
        # infer severity from status code if the log line itself says INFO but status is 5xx
        if status >= 500 and level == "INFO":
            level = "ERROR"
        return LogRecord(
            timestamp=_parse_app_timestamp(d["timestamp"]),
            level=level,
            service=d["service"],
            method=d["method"],
            endpoint=d["endpoint"],
            status=status,
            duration_ms=int(d["duration"]),
            message=d.get("message") or "",
            raw=line,
        )

    m = ACCESS_LOG_RE.match(line)
    if m:
        d = m.groupdict()
        status = int(d["status"])
        level = "ERROR" if status >= 500 else ("WARN" if status >= 400 else "INFO")
        return LogRecord(
            timestamp=_parse_access_timestamp(d["timestamp"]),
            level=level,
            service=None,
            method=d["method"],
            endpoint=d["endpoint"],
            status=status,
            duration_ms=None,
            message="",
            raw=line,
        )

    return None


def parse_file(path: str) -> List[LogRecord]:
    """Parse a full log file, skipping unparseable lines."""
    records: List[LogRecord] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            rec = parse_line(line)
            if rec is not None:
                records.append(rec)
    return records
