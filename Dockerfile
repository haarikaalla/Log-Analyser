FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_ANALYZER_ALLOWED_DIR=/app/sample_logs \
    LOG_ANALYZER_DB_PATH=/data/log_analyzer.db

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir . && \
    useradd --system --uid 10001 --create-home appuser && \
    mkdir -p /data && chown appuser:appuser /data

USER appuser
EXPOSE 8000
CMD ["uvicorn", "log_analyzer.dashboard:app", "--host", "0.0.0.0", "--port", "8000"]
