FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn loan_api.main:app --host 0.0.0.0 --port 8000"]
