# Log Analyzer — Application Log Triage Tool

A small tool that parses raw application logs, clusters errors by root cause,
detects anomalies (traffic spikes, error-rate spikes, repeated timeouts), and
surfaces it all through a CLI report or a live web dashboard.

Built to mirror the kind of triage work a support/CX engineer does day to day:
a customer reports something broke → pull the logs → find the pattern → find
the root cause → confirm the fix.

## Why

Most "log analyzer" toy projects just grep for the word ERROR. This one
instead:
- **Clusters** errors by a normalized signature (`500 /api/orders/{id}`
  instead of 40 separate lines for 40 different order IDs), so one root
  cause shows up as one entry, not forty.
- **Detects anomalies statistically** — a traffic or error spike is flagged
  when a time bucket is more than 2 standard deviations above the rolling
  baseline, not from a hardcoded threshold.
- **Flags repeated timeouts** on a specific endpoint even when they're spread
  out over time and wouldn't show up as a "spike."

## Demo

Sample logs (`sample_logs/app.log`) simulate a realistic 45-minute incident
window: normal traffic, a payment-gateway timeout incident, a bad deploy that
causes a `KeyError` on one endpoint, and a traffic spike. Running the tool
against it correctly identifies all three injected incidents (see
[Example Output](#example-output) below).

### CLI

```bash
pip install -r requirements.txt
python scripts/generate_sample_logs.py        # (re)generate sample_logs/app.log
python -m log_analyzer.cli sample_logs/app.log
```

### Web dashboard

```bash
uvicorn log_analyzer.dashboard:app --reload
# open http://127.0.0.1:8000
```

By default the web app can read only files in `sample_logs/`. For another directory,
set `LOG_ANALYZER_ALLOWED_DIR` before starting the server:

```bash
LOG_ANALYZER_ALLOWED_DIR=/path/to/logs uvicorn log_analyzer.dashboard:app --reload
# open http://127.0.0.1:8000/?path=/path/to/logs/app.log
```

The dashboard and `/api/report` reject paths outside that directory, including
symlinks to outside files. Log content is escaped before display in HTML. Keep the
server local or place it behind your own authentication and network controls.

### JSON output (for piping into other tools)

```bash
python -m log_analyzer.cli sample_logs/app.log --json report.json
```

## Example Output

```
Log Analyzer Report — sample_logs/app.log
============================================================
Total lines parsed : 446
Total errors       : 46
Error rate         : 10.31%

Top Error Clusters
------------------------------------------------------------
  [40x] 500 /api/orders/{id}
        sample: KeyError: 'discount_code' not found in response payload
        first: 2026-07-04 09:31:00   last: 2026-07-04 09:34:00
  [6x] 504 /api/payments/charge
        sample: TimeoutError: upstream payment gateway did not respond
        first: 2026-07-04 09:25:00   last: 2026-07-04 09:30:00

Anomalies Detected
------------------------------------------------------------
  [HIGH] repeated_timeout: /api/payments/charge timed out 6 times
        window: 2026-07-04 09:25:00 → 2026-07-04 09:30:00
  [HIGH] error_rate_spike: 10 errors vs baseline avg 0.9
        window: 2026-07-04 09:31:00 → 2026-07-04 09:32:00
  [MEDIUM] traffic_spike: 40 requests vs baseline avg 8.4
        window: 2026-07-04 09:35:00 → 2026-07-04 09:36:00

Slowest Endpoints (by avg response time)
------------------------------------------------------------
  /api/payments/charge           avg   390.5ms   max   3439ms   n=66
```

Reading that output top to bottom tells the same story a support engineer
would need to reconstruct by hand: the payment gateway started timing out
around 09:25, which was likely still being investigated when a deploy at
09:31 introduced a `KeyError` on the orders endpoint, and a traffic spike hit
five minutes later on top of it.

## How it works

- **`log_analyzer/parser.py`** — regex-based parsers for a structured app-log
  format and standard Nginx/Apache combined log format. Returns normalized
  `LogRecord` objects regardless of source format.
- **`log_analyzer/analyzer.py`** — clustering (via normalized endpoint
  signatures), time-bucketed spike detection (mean + N·stddev), and
  repeated-timeout detection across the whole file regardless of bucket.
- **`log_analyzer/cli.py`** — argparse CLI, human-readable report + optional
  JSON export.
- **`log_analyzer/dashboard.py`** — FastAPI app rendering the same report as
  an HTML dashboard, plus a `/api/report` JSON endpoint.
- **`scripts/generate_sample_logs.py`** — generates the synthetic log file
  used for the demo/tests, with three deliberately injected incidents.

## Testing

```bash
pip install -r requirements.txt
pytest tests/ -v
```

13 tests cover log parsing, analysis, dashboard HTML escaping, path isolation,
and missing-file handling. GitHub Actions runs the suite on every push and pull request.

## Possible extensions

- Slack/email alerting when a `HIGH` severity anomaly is detected
- Support for JSON-structured logs (e.g. from `structlog`)
- Rolling live-tail mode instead of static-file analysis

## Stack

Python · FastAPI · regex-based log parsing · pytest
