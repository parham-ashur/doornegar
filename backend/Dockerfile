FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PORT=8000

EXPOSE 8000

CMD sh -c "timeout 30 alembic upgrade head || true; uvicorn app.main:app --host 0.0.0.0 --port $PORT"
