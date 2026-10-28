from datetime import datetime, timedelta

from log_analyzer.parser import LogRecord
from log_analyzer.analyzer import cluster_errors, detect_anomalies, analyze, slowest_endpoints


def make_record(ts, level="INFO", endpoint="/api/orders/1", status=200, duration=100, message=""):
    return LogRecord(
        timestamp=ts, level=level, service="order-service", method="GET",
        endpoint=endpoint, status=status, duration_ms=duration, message=message,
        raw="synthetic",
    )


def test_cluster_errors_groups_by_normalized_endpoint():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [
        make_record(base, level="ERROR", endpoint="/api/orders/1", status=500, message="boom"),
        make_record(base + timedelta(seconds=5), level="ERROR", endpoint="/api/orders/2", status=500, message="boom"),
        make_record(base + timedelta(seconds=10), level="INFO", endpoint="/api/orders/3", status=200),
    ]
    clusters = cluster_errors(records)
    assert len(clusters) == 1
    assert clusters[0].count == 2
    assert clusters[0].signature == "500 /api/orders/{id}"


def test_cluster_errors_separates_exception_types():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [
        make_record(base, level="ERROR", status=500, message="KeyError: missing discount"),
        make_record(base, level="ERROR", status=500, message="TimeoutError: upstream did not respond"),
    ]
    signatures = {cluster.signature for cluster in cluster_errors(records)}
    assert signatures == {
        "500 /api/orders/{id} [KeyError]",
        "500 /api/orders/{id} [TimeoutError]",
    }


def test_repeated_timeout_detected():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [
        make_record(base + timedelta(minutes=i), status=504,
                    message="TimeoutError: upstream did not respond", endpoint="/api/payments/charge")
        for i in range(4)
    ]
    anomalies = detect_anomalies(records, repeated_timeout_threshold=3)
    kinds = [a.kind for a in anomalies]
    assert "repeated_timeout" in kinds


def test_spike_uses_only_prior_buckets():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [make_record(base + timedelta(minutes=i)) for i in range(5)]
    records.extend(
        make_record(base + timedelta(minutes=5), level="ERROR", status=500)
        for _ in range(10)
    )

    anomalies = detect_anomalies(records)

    assert {a.kind for a in anomalies} == {"traffic_spike", "error_count_spike"}
    assert all(a.window_start == base + timedelta(minutes=5) for a in anomalies)


def test_slowest_endpoints_sorted_desc():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [
        make_record(base, endpoint="/api/fast", duration=50),
        make_record(base, endpoint="/api/slow", duration=900),
    ]
    result = slowest_endpoints(records)
    assert result[0]["endpoint"] == "/api/slow"


def test_analyze_computes_error_rate():
    base = datetime(2026, 7, 4, 9, 0, 0)
    records = [make_record(base, status=200) for _ in range(9)] + [
        make_record(base, level="ERROR", status=500)
    ]
    report = analyze(records)
    assert report.total_lines == 10
    assert report.total_errors == 1
    assert report.error_rate == 10.0
