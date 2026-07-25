from log_analyzer.parser import parse_line


def test_parses_app_log_line():
    line = "2026-07-04 09:00:00,000 INFO [order-service] GET /api/orders/854 -> 200 (82ms)"
    rec = parse_line(line)
    assert rec is not None
    assert rec.level == "INFO"
    assert rec.service == "order-service"
    assert rec.method == "GET"
    assert rec.endpoint == "/api/orders/854"
    assert rec.status == 200
    assert rec.duration_ms == 82


def test_parses_error_with_message():
    line = "2026-07-04 09:31:00,000 ERROR [order-service] GET /api/orders/394 -> 500 (198ms) KeyError: 'discount_code' not found"
    rec = parse_line(line)
    assert rec is not None
    assert rec.status == 500
    assert "KeyError" in rec.message


def test_upgrades_level_when_status_5xx_but_level_info():
    line = "2026-07-04 09:31:00,000 INFO [order-service] GET /api/orders/394 -> 500 (198ms) boom"
    rec = parse_line(line)
    assert rec.level == "ERROR"


def test_returns_none_for_garbage():
    assert parse_line("not a real log line") is None


def test_returns_none_for_blank_line():
    assert parse_line("   ") is None


def test_parses_access_log_format():
    line = '127.0.0.1 - - [04/Jul/2026:12:03:11 +0000] "GET /api/orders/883 HTTP/1.1" 500 512'
    rec = parse_line(line)
    assert rec is not None
    assert rec.method == "GET"
    assert rec.endpoint == "/api/orders/883"
    assert rec.status == 500
    assert rec.level == "ERROR"
