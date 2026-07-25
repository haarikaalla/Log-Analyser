"""
analyzer.py
Takes parsed LogRecords and produces:
  - error clusters (grouped by endpoint + status/message signature)
  - time-bucketed request/error counts
  - anomaly flags: traffic spikes, error-rate spikes, repeated timeouts on one endpoint
"""

from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import List, Dict, Optional

from .parser import LogRecord


@dataclass
class ErrorCluster:
    signature: str
    endpoint: Optional[str]
    status: Optional[int]
    count: int
    sample_message: str
    first_seen: datetime
    last_seen: datetime


@dataclass
class Anomaly:
    kind: str          # "traffic_spike" | "error_rate_spike" | "repeated_timeout"
    window_start: datetime
    window_end: datetime
    detail: str
    severity: str       # "low" | "medium" | "high"


@dataclass
class AnalysisReport:
    total_lines: int
    total_errors: int
    error_rate: float
    clusters: List[ErrorCluster]
    anomalies: List[Anomaly]
    slowest_endpoints: List[Dict]


def _signature(rec: LogRecord) -> str:
    """Group similar errors together even if exact message text differs slightly."""
    endpoint = rec.endpoint or "unknown"
    status = rec.status or 0
    # collapse numeric IDs in the path so /api/orders/883 and /api/orders/991 cluster together
    import re
    normalized_endpoint = re.sub(r"/\d+", "/{id}", endpoint)
    return f"{status} {normalized_endpoint}"


def cluster_errors(records: List[LogRecord]) -> List[ErrorCluster]:
    groups: Dict[str, List[LogRecord]] = defaultdict(list)
    for r in records:
        if r.level in ("ERROR", "CRITICAL") or (r.status and r.status >= 500):
            groups[_signature(r)].append(r)

    clusters = []
    for sig, recs in groups.items():
        recs_sorted = sorted(recs, key=lambda r: r.timestamp or datetime.min)
        clusters.append(
            ErrorCluster(
                signature=sig,
                endpoint=recs_sorted[0].endpoint,
                status=recs_sorted[0].status,
                count=len(recs_sorted),
                sample_message=recs_sorted[0].message or recs_sorted[0].raw,
                first_seen=recs_sorted[0].timestamp,
                last_seen=recs_sorted[-1].timestamp,
            )
        )
    clusters.sort(key=lambda c: c.count, reverse=True)
    return clusters


def _bucket_counts(records: List[LogRecord], bucket_seconds: int = 60) -> Dict[datetime, Dict[str, int]]:
    buckets: Dict[datetime, Dict[str, int]] = defaultdict(lambda: {"total": 0, "errors": 0})
    for r in records:
        if r.timestamp is None:
            continue
        epoch = int(r.timestamp.timestamp())
        bucket_key = datetime.fromtimestamp(epoch - (epoch % bucket_seconds))
        buckets[bucket_key]["total"] += 1
        if r.level in ("ERROR", "CRITICAL") or (r.status and r.status >= 500):
            buckets[bucket_key]["errors"] += 1
    return dict(sorted(buckets.items()))


def detect_anomalies(records: List[LogRecord], bucket_seconds: int = 60,
                      spike_stddev_threshold: float = 2.0,
                      repeated_timeout_threshold: int = 3) -> List[Anomaly]:
    anomalies: List[Anomaly] = []
    buckets = _bucket_counts(records, bucket_seconds)
    if len(buckets) < 3:
        # not enough data to establish a baseline
        totals = [v["total"] for v in buckets.values()]
        errors = [v["errors"] for v in buckets.values()]
    else:
        totals = [v["total"] for v in buckets.values()]
        errors = [v["errors"] for v in buckets.values()]

        total_mean, total_std = mean(totals), pstdev(totals) or 1
        err_mean, err_std = mean(errors), pstdev(errors) or 1

        for bucket_start, counts in buckets.items():
            bucket_end = bucket_start + timedelta(seconds=bucket_seconds)
            if counts["total"] > total_mean + spike_stddev_threshold * total_std and counts["total"] > 5:
                anomalies.append(Anomaly(
                    kind="traffic_spike",
                    window_start=bucket_start,
                    window_end=bucket_end,
                    detail=f"{counts['total']} requests vs baseline avg {total_mean:.1f}",
                    severity="medium",
                ))
            if counts["errors"] > err_mean + spike_stddev_threshold * err_std and counts["errors"] > 2:
                anomalies.append(Anomaly(
                    kind="error_rate_spike",
                    window_start=bucket_start,
                    window_end=bucket_end,
                    detail=f"{counts['errors']} errors vs baseline avg {err_mean:.1f}",
                    severity="high",
                ))

    # repeated timeout detection: same endpoint timing out N+ times regardless of time bucket
    timeout_counter = Counter()
    timeout_records: Dict[str, List[LogRecord]] = defaultdict(list)
    for r in records:
        msg = (r.message or "").lower()
        if "timeout" in msg or "timed out" in msg:
            key = r.endpoint or "unknown"
            timeout_counter[key] += 1
            timeout_records[key].append(r)

    for endpoint, count in timeout_counter.items():
        if count >= repeated_timeout_threshold:
            recs = sorted(timeout_records[endpoint], key=lambda r: r.timestamp or datetime.min)
            anomalies.append(Anomaly(
                kind="repeated_timeout",
                window_start=recs[0].timestamp,
                window_end=recs[-1].timestamp,
                detail=f"{endpoint} timed out {count} times",
                severity="high",
            ))

    return sorted(anomalies, key=lambda a: (a.severity != "high", a.window_start or datetime.min))


def slowest_endpoints(records: List[LogRecord], top_n: int = 5) -> List[Dict]:
    durations: Dict[str, List[int]] = defaultdict(list)
    for r in records:
        if r.endpoint and r.duration_ms is not None:
            durations[r.endpoint].append(r.duration_ms)

    result = []
    for endpoint, values in durations.items():
        result.append({
            "endpoint": endpoint,
            "avg_ms": round(mean(values), 1),
            "max_ms": max(values),
            "requests": len(values),
        })
    result.sort(key=lambda x: x["avg_ms"], reverse=True)
    return result[:top_n]


def analyze(records: List[LogRecord], bucket_seconds: int = 60) -> AnalysisReport:
    total = len(records)
    errors = sum(1 for r in records if r.level in ("ERROR", "CRITICAL") or (r.status and r.status >= 500))
    return AnalysisReport(
        total_lines=total,
        total_errors=errors,
        error_rate=round((errors / total) * 100, 2) if total else 0.0,
        clusters=cluster_errors(records),
        anomalies=detect_anomalies(records, bucket_seconds=bucket_seconds),
        slowest_endpoints=slowest_endpoints(records),
    )
