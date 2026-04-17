# Loan Data Ingestion Service — Claude Context

## Project purpose

REST ingestion service + MCP agent surface for a normalized 3-table PostgreSQL loan dataset.
A browser UI with embedded Claude/Gemini chat is the primary user surface.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12) |
| DB | PostgreSQL 16 via SQLAlchemy 2.0, Alembic migrations |
| Ingestion | pandas (CSV/Excel) with FK pre-check and ON CONFLICT DO NOTHING |
| MCP | `mcp` SDK stdio transport (`loan_mcp.server`) |
| Chat | Anthropic SDK (`claude-sonnet-4-6`) + Google GenAI SDK (`gemini-2.0-flash`) |
| Infra | Docker Compose — `postgres` + `loan_api` services |

## Repository layout

```
src/loan_api/
  main.py          FastAPI app, static mount, router wiring
  config.py        Pydantic settings (reads .env)
  db.py            engine, readonly_engine, SessionLocal, readonly_connection()
  models.py        ORM: Applicant, Employment, Loan + TABLE_MODELS dict
  ingest.py        CSV/Excel parse → FK check → bulk INSERT ON CONFLICT DO NOTHING
  sql_safety.py    assert_read_only() — sqlparse + allowlist gate
  schemas.py       Pydantic request/response models
  tools.py         Anthropic/Gemini tool schemas + executor functions (in-process, no HTTP)
  chat.py          POST /chat SSE endpoint — Anthropic and Gemini provider loops
  routes/
    ingest.py      POST /ingest/{table}
    tables.py      GET /tables, /tables/{name}/schema, /tables/{name}/rows
    sql.py         POST /sql (read-only), POST /sql/write (gated)
  static/
    index.html     Single-page UI — row-count tiles, drop zones, chat panel
    app.js         Vanilla JS — upload, SSE stream consumer, provider toggle

src/loan_mcp/
  server.py        FastMCP stdio server (6 tools)
  client.py        httpx wrapper around loan_api

migrations/versions/0001_initial.py   Schema DDL + loan_reader GRANT
data/              Sample CSVs: applicants.csv (1000 rows), employment.csv (1000 rows), loans.csv (1500 rows)
uploads/           Host bind-mount for MCP/chat ingest_from_path (→ /uploads in container)
tests/             pytest: test_ingest.py, test_sql_safety.py
```

## Database schema

See `data.md` for full column reference.

```
applicants (applicant_id PK)
    └─< employment (employment_id PK, applicant_id FK)
    └─< loans      (loan_id PK,       applicant_id FK)
```

Two DB roles:
- `loan_app` — full DML, used by FastAPI ingest/write routes
- `loan_reader` — SELECT only, used by `POST /sql` and the `run_sql` tool

## Key invariants

- `ingest.py` is the **only** place that mutates loan tables — do not add writes elsewhere
- `sql_safety.assert_read_only()` gates all user-supplied SQL — always call it before executing
- `ingest_from_path` in `tools.py` validates that the resolved path stays under `UPLOADS_DIR` — do not weaken this check
- Ingestion is idempotent: re-ingesting the same file inserts 0 rows, skips duplicates
- FK order matters: ingest `applicants` before `employment` or `loans`

## Environment variables (see .env.example)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | App role connection string |
| `READONLY_DATABASE_URL` | Read-only role connection string |
| `ALLOW_SQL_WRITES` | Enables `POST /sql/write` (default false) |
| `ANTHROPIC_API_KEY` | Anthropic chat provider |
| `ANTHROPIC_MODEL` | Default `claude-sonnet-4-6` |
| `GEMINI_API_KEY` | Google Gemini chat provider |
| `GEMINI_MODEL` | Default `gemini-2.0-flash` |
| `UPLOADS_DIR` | Container path for ingest_from_path (default `/uploads`) |

## Running locally

```bash
# Full Docker (recommended)
cp .env.example .env          # fill in API keys
docker compose up -d --build
open http://localhost:8000/

# Partial (Postgres in Docker, API on host)
docker compose up -d postgres
source .venv/Scripts/activate
pip install -e .[dev]
alembic upgrade head
uvicorn loan_api.main:app --reload

# Tests
pytest
```

## Chat SSE protocol

`POST /chat` body: `{"messages": [...], "provider": "anthropic"|"gemini"}`

Stream events: `{"type":"text","text":"..."}` | `{"type":"tool","name":...,"input":...}` | `{"type":"tool_result","name":...,"ok":bool}` | `{"type":"error","message":"..."}` | `{"type":"done"}`

## MCP tools (Claude Code / Claude Desktop)

`list_uploads`, `ingest_csv`, `list_tables`, `describe_table`, `read_rows`, `run_sql`, `get_row_counts`

MCP config lives in `.mcp.json` (Claude Code) and `claude_desktop_config.json` (Claude Desktop — runs via `docker run -i --rm`).
