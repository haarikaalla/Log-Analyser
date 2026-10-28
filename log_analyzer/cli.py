"""
cli.py
Command-line interface:

    python -m log_analyzer.cli sample_logs/app.log
    python -m log_analyzer.cli sample_logs/app.log --json report.json
"""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime

from .parser import parse_file
from .analyzer import analyze
from .store import save_run


def _default_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def print_report(report, log_path: str):
    print(f"\nLog Analyzer Report — {log_path}")
    print("=" * 60)
    print(f"Total lines parsed : {report.total_lines}")
    print(f"Total errors       : {report.total_errors}")
    print(f"Error rate         : {report.error_rate}%")

    print("\nTop Error Clusters")
    print("-" * 60)
    if not report.clusters:
        print("  (none found)")
    for c in report.clusters[:10]:
        print(f"  [{c.count}x] {c.signature}")
        print(f"        sample: {c.sample_message[:90]}")
        print(f"        first: {c.first_seen}   last: {c.last_seen}")

    print("\nAnomalies Detected")
    print("-" * 60)
    if not report.anomalies:
        print("  (none found)")
    for a in report.anomalies:
        print(f"  [{a.severity.upper()}] {a.kind}: {a.detail}")
        print(f"        window: {a.window_start} → {a.window_end}")

    print("\nSlowest Endpoints (by avg response time)")
    print("-" * 60)
    if not report.slowest_endpoints:
        print("  (no timing data found)")
    for e in report.slowest_endpoints:
        print(f"  {e['endpoint']:<30} avg {e['avg_ms']:>7}ms   max {e['max_ms']:>6}ms   n={e['requests']}")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze application logs for errors and anomalies.")
    parser.add_argument("logfile", help="Path to the log file to analyze")
    parser.add_argument("--bucket-seconds", type=int, default=60, help="Time bucket size for spike detection (default: 60)")
    parser.add_argument("--json", metavar="OUTFILE", help="Also write the full report as JSON to this path")
    parser.add_argument("--save", action="store_true", help="Save an idempotent analysis snapshot to SQLite")
    args = parser.parse_args(argv)

    records = parse_file(args.logfile)
    if not records:
        print(f"No parseable log lines found in {args.logfile}", file=sys.stderr)
        sys.exit(1)

    report = analyze(records, bucket_seconds=args.bucket_seconds)
    print_report(report, args.logfile)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(asdict(report), f, indent=2, default=_default_serializer)
        print(f"Full report written to {args.json}")
    if args.save:
        print(f"Saved analysis run: {save_run(report, args.logfile)}")


if __name__ == "__main__":
    main()
