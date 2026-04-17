# Loan Data Ingestion Service + MCP Agent

CSV/Excel ingestion into a normalized 3-table PostgreSQL schema (`applicants`, `employment`, `loans`), with a standalone MCP server so Claude can drive ingestion and run read-only SQL.

## Architecture

```
Claude Code  ──MCP──►  loan_mcp  ──HTTP──►  loan_api (FastAPI)  ──SQL──►  PostgreSQL
```

## Setup

### Option A — everything in Docker (recommended)

```bash
docker compose up -d --build
# postgres + loan_api start; alembic upgrade runs in the loan_api container on boot
curl http://localhost:8000/health
```

### Option B — Postgres in Docker, API on host (for live reload)

```bash
python -m venv .venv && source .venv/Scripts/activate   # bash on Windows
pip install -e .[dev]
docker compose up -d postgres
cp .env.example .env
alembic upgrade head
uvicorn loan_api.main:app --reload
```

## Ingest the sample data

```bash
curl -F "file=@data/applicants.csv" http://localhost:8000/ingest/applicants
curl -F "file=@data/employment.csv" http://localhost:8000/ingest/employment
curl -F "file=@data/loans.csv"      http://localhost:8000/ingest/loans
curl http://localhost:8000/tables
```

## Use from Claude Code

`.mcp.json` is checked in. Restart Claude Code in this directory and the `loan-data` MCP server appears with these tools:

- `ingest_csv(table, file_path)`
- `list_tables()`
- `describe_table(table)`
- `read_rows(table, limit, offset)`
- `run_sql(query)` — read-only
- `get_row_counts()`

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/ingest/{table}` | multipart upload |
| GET | `/tables` | row counts |
| GET | `/tables/{name}/schema` | columns + FKs |
| GET | `/tables/{name}/rows` | paginated |
| POST | `/sql` | read-only (SELECT/WITH/EXPLAIN) |
| POST | `/sql/write` | gated by `ALLOW_SQL_WRITES=true` |
| GET | `/health` | DB ping |

## Tests

```bash
pytest
```
