# Loan Data Ingestion Service — Claude Context

## Project purpose

REST ingestion service + MCP agent surface for a normalized 3-table PostgreSQL loan dataset.
A browser UI with embedded multi-provider chat is the primary user surface.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12) |
| DB | PostgreSQL 16 via SQLAlchemy 2.0, Alembic migrations |
| Ingestion | pandas (CSV/Excel) with FK pre-check and ON CONFLICT DO NOTHING |
| MCP | `mcp` SDK stdio transport (`loan_mcp.server`) |
| Chat — Anthropic | `anthropic` SDK · `claude-sonnet-4-6` · prompt caching on system + tools |
| Chat — Gemini | `google-genai` SDK · `gemini-2.0-flash` · retry logic for 429 rate limits |
| Chat — Cerebras | `cerebras-cloud-sdk` · `llama3.1-8b` · OpenAI-compatible tool-use loop |
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
  tools.py         Tool schemas + executor functions (in-process, no HTTP self-call)
  chat.py          POST /chat SSE endpoint — Anthropic, Gemini, Cerebras provider loops
  routes/
    ingest.py      POST /ingest/{table}
    tables.py      GET /tables, /tables/{name}/schema, /tables/{name}/rows
    sql.py         POST /sql (read-only), POST /sql/write (gated)
  static/
    index.html     Single-page UI — row-count tiles, drop zones, chat panel
    app.js         Vanilla JS — upload, SSE consumer, provider toggle, ! commands

src/loan_mcp/
  server.py        FastMCP stdio server (7 tools)
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
- `ingest_from_path` in `tools.py` validates that the resolved path stays under `UPLOADS_DIR`
- Ingestion is idempotent: re-ingesting the same file inserts 0 rows, skips duplicates
- FK order matters: ingest `applicants` before `employment` or `loans`
- Gemini tool schemas must not contain `minimum`, `maximum`, `default` — `_clean_schema()` strips them

## Environment variables (see .env.example)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | App role connection string |
| `READONLY_DATABASE_URL` | Read-only role connection string |
| `ALLOW_SQL_WRITES` | Enables `POST /sql/write` (default false) |
| `ANTHROPIC_API_KEY` | Anthropic chat provider |
| `ANTHROPIC_MODEL` | Default `claude-sonnet-4-6` |
| `GEMINI_API_KEY` | Google Gemini chat provider (free tier: ~15 RPM, low daily quota) |
| `GEMINI_MODEL` | Default `gemini-2.0-flash` |
| `CEREBRAS_API_KEY` | Cerebras chat provider (generous free tier) |
| `CEREBRAS_MODEL` | Default `llama3.1-8b` |
| `UPLOADS_DIR` | Container path for ingest_from_path (default `/uploads`) |

## Chat providers

Three providers selectable via the UI toggle bar — conversation resets on switch.

| Provider | Model | Notes |
|---|---|---|
| Anthropic | claude-sonnet-4-6 | Prompt caching on system + tools; most reliable |
| Gemini | gemini-2.0-flash | Free tier exhausts quickly (daily limit); auto-retry on per-minute 429 |
| Cerebras | llama3.1-8b | OpenAI-compatible API; generous free tier; best for high-volume use |

**Gemini 429 handling:** transient per-minute limits → retry up to 2× with server-suggested delay (shown as amber info pill). Daily quota exhausted → fail fast with a message directing user to another provider.

## Chat SSE protocol

`POST /chat` body: `{"messages": [...], "provider": "anthropic"|"gemini"|"cerebras"}`

Stream events:
- `{"type":"text","text":"..."}` — partial assistant text
- `{"type":"tool","name":...,"id":...,"input":{...}}` — tool invocation
- `{"type":"tool_result","name":...,"id":...,"ok":bool}` — tool finished
- `{"type":"info","message":"..."}` — status notice (retry, etc.)
- `{"type":"error","message":"..."}` — fatal error
- `{"type":"done"}` — end of turn

## Direct ! commands (bypass LLM)

Type in the chat input to call tools without the LLM. Results rendered as monospace command output.

| Command | What it calls |
|---|---|
| `!list_tables` | `GET /tables` |
| `!get_row_counts` | `GET /tables` (same) |
| `!describe_table <table>` | `GET /tables/<table>/schema` |
| `!read_rows <table> [limit]` | `GET /tables/<table>/rows?limit=N` |
| `!run_sql <query>` | `POST /sql` |
| `!help` | Shows command reference |

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

## MCP tools (Claude Code / Claude Desktop)

`list_uploads`, `ingest_csv`, `list_tables`, `describe_table`, `read_rows`, `run_sql`, `get_row_counts`

MCP config: `.mcp.json` (Claude Code) and `claude_desktop_config.json` (Claude Desktop — runs via `docker run -i --rm`).
