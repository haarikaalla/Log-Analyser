"""
generate_sample_logs.py
Generates a realistic synthetic application log file with:
  - normal baseline traffic
  - a repeated-timeout incident on one endpoint
  - a traffic spike
  - an error-rate spike (500s) tied to a bad deploy window

Run: python scripts/generate_sample_logs.py
Writes: sample_logs/app.log
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

SERVICES = ["order-service", "payment-service", "auth-service", "inventory-service"]
ENDPOINTS = [
    ("GET", "/api/orders/{id}"),
    ("POST", "/api/orders"),
    ("GET", "/api/users/{id}"),
    ("POST", "/api/payments/charge"),
    ("GET", "/api/inventory/{id}"),
    ("POST", "/api/auth/login"),
]

OUT_PATH = Path(__file__).resolve().parent.parent / "sample_logs" / "app.log"


def fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M:%S,") + f"{ts.microsecond // 1000:03d}"


def make_line(ts, level, service, method, endpoint, status, duration, message=""):
    ep = endpoint.replace("{id}", str(random.randint(100, 999)))
    line = f"{fmt(ts)} {level} [{service}] {method} {ep} -> {status} ({duration}ms)"
    if message:
        line += f" {message}"
    return line


def normal_traffic(start, n=6):
    lines = []
    for _ in range(n):
        method, endpoint = random.choice(ENDPOINTS)
        service = random.choice(SERVICES)
        duration = random.randint(20, 180)
        status = random.choices([200, 201, 404], weights=[92, 5, 3])[0]
        level = "INFO" if status < 400 else "WARN"
        lines.append(make_line(start, level, service, method, endpoint, status, duration))
    return lines


def main():
    lines = []
    t = datetime(2026, 7, 4, 9, 0, 0)

    # --- Phase 1: normal baseline traffic (first ~25 minutes) ---
    for _ in range(25):
        lines.extend(normal_traffic(t, n=random.randint(4, 8)))
        t += timedelta(minutes=1)

    # --- Phase 2: repeated timeout incident on payment-service ---
    incident_start = t
    for _ in range(6):
        lines.extend(normal_traffic(t, n=4))
        lines.append(make_line(
            t, "ERROR", "payment-service", "POST", "/api/payments/charge",
            504, 3000 + random.randint(0, 500),
            "TimeoutError: upstream payment gateway did not respond"
        ))
        t += timedelta(minutes=1)

    # --- Phase 3: bad deploy -> error rate spike on order-service ---
    deploy_start = t
    for _ in range(4):
        for _ in range(10):
            lines.append(make_line(
                t, "ERROR", "order-service", "GET", "/api/orders/{id}",
                500, random.randint(80, 200),
                "KeyError: 'discount_code' not found in response payload"
            ))
        lines.extend(normal_traffic(t, n=3))
        t += timedelta(minutes=1)

    # --- Phase 4: traffic spike (flash sale) on inventory-service ---
    for _ in range(3):
        lines.extend(normal_traffic(t, n=40))
        t += timedelta(minutes=1)

    # --- Phase 5: back to normal ---
    for _ in range(15):
        lines.extend(normal_traffic(t, n=random.randint(4, 8)))
        t += timedelta(minutes=1)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {len(lines)} log lines to {OUT_PATH}")
    print(f"Timeout incident starts around: {incident_start}")
    print(f"Bad deploy error spike starts around: {deploy_start}")


if __name__ == "__main__":
    main()
