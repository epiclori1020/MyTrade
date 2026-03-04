FROM python:3.12-slim

# System deps for potential native extensions (agno[postgres] → psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: Install deps from requirements.txt (cached unless deps change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: Install app from pyproject.toml (--no-deps: deps already installed)
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

# Production entrypoint — no --reload. Railway injects PORT env var.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
