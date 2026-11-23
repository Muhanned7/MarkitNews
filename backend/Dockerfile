# FinnWinn FastAPI backend for Google Cloud Run
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Create/upgrade tables (idempotent), then start the API on Cloud Run's $PORT.
# init_db failing (e.g. the free database is waking up) must not stop the API from starting.
CMD python scripts/init_db.py || echo "init_db failed - continuing"; \
    exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
