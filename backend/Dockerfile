FROM python:3.11-slim

WORKDIR /app

# postgresql-client gives us pg_dump for the R2 backup script
# (backend/scripts/r2_db_backup.py). Slim image doesn't include it
# by default. ~10MB extra; harmless for other services.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PORT=8000
# Unbuffered stdout/stderr so logs appear in Railway in real time,
# not held in Python's internal buffer until the process exits.
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD sh -c "timeout 30 alembic upgrade head || true; uvicorn app.main:app --host 0.0.0.0 --port $PORT"
