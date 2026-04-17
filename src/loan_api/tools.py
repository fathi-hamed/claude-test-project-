"""Tool definitions and executor functions for the embedded Claude chat.

The executors mirror the REST endpoints but run in-process (no HTTP self-call).
Each executor returns a JSON-serializable dict; the chat loop stringifies it
before handing it back to Claude as a tool_result.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, inspect, select, text

from .config import settings
from .db import SessionLocal, readonly_connection
from .ingest import ingest
from .models import TABLE_MODELS
from .sql_safety import assert_read_only

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_tables",
        "description": "List the 3 loan tables (applicants, employment, loans) with their current row counts.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "describe_table",
        "description": "Return columns, types, primary key, and foreign keys for one loan table.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["applicants", "employment", "loans"],
                },
            },
            "required": ["table"],
        },
    },
    {
        "name": "read_rows",
        "description": "Read paginated rows from one of the loan tables.",
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["applicants", "employment", "loans"],
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 50},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
            },
            "required": ["table"],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Run a read-only SQL query against the loan database. "
            "Only SELECT / WITH / EXPLAIN statements are allowed; mutations are rejected. "
            "Use standard PostgreSQL syntax. The 3 tables are applicants, employment, loans."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_row_counts",
        "description": "Return a {table_name: row_count} mapping for the 3 loan tables. Cheap summary.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "ingest_from_path",
        "description": (
            "Ingest a CSV or Excel file from the server's uploads directory into one of "
            "the loan tables. The file must already exist under the mounted uploads folder "
            "(users drop files there via the web UI or file manager). Pass just the filename "
            "(e.g. 'loans.csv') or a path under the uploads directory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": ["applicants", "employment", "loans"],
                },
                "file_path": {
                    "type": "string",
                    "description": "Filename or path under the uploads directory (e.g. 'loans.csv').",
                },
            },
            "required": ["table", "file_path"],
        },
    },
]


def _list_tables() -> dict[str, Any]:
    with SessionLocal() as db:
        out = []
        for name, model in TABLE_MODELS.items():
            count = db.scalar(select(func.count()).select_from(model)) or 0
            out.append({"name": name, "row_count": int(count)})
    return {"tables": out}


def _describe_table(table: str) -> dict[str, Any]:
    if table not in TABLE_MODELS:
        return {"error": f"Unknown table: {table}"}
    t = TABLE_MODELS[table].__table__
    cols = []
    for col in t.columns:
        fk = next(iter(col.foreign_keys), None)
        cols.append(
            {
                "name": col.name,
                "type": str(col.type),
                "nullable": bool(col.nullable),
                "primary_key": col.primary_key,
                "foreign_key": str(fk.column) if fk else None,
            }
        )
    return {"name": table, "columns": cols}


def _read_rows(table: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if table not in TABLE_MODELS:
        return {"error": f"Unknown table: {table}"}
    limit = max(1, min(1000, int(limit)))
    offset = max(0, int(offset))
    model = TABLE_MODELS[table]
    with SessionLocal() as db:
        rows = db.execute(select(model).limit(limit).offset(offset)).scalars().all()
        cols = [c.name for c in inspect(model).columns]
        serialized = [{c: getattr(r, c) for c in cols} for r in rows]
    return {"table": table, "limit": limit, "offset": offset, "rows": serialized}


def _run_sql(query: str) -> dict[str, Any]:
    try:
        assert_read_only(query)
    except Exception as exc:  # HTTPException or other
        detail = getattr(exc, "detail", str(exc))
        return {"error": detail}
    with readonly_connection() as conn:
        result = conn.execute(text(query))
        cols = list(result.keys())
        rows = [list(r) for r in result.fetchall()]
    return {"columns": cols, "rows": rows, "row_count": len(rows)}


def _get_row_counts() -> dict[str, Any]:
    with SessionLocal() as db:
        return {
            name: int(db.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in TABLE_MODELS.items()
        }


def _resolve_upload_path(file_path: str) -> Path:
    """Resolve a user-supplied path to an absolute path under UPLOADS_DIR.

    Prevents path traversal — rejects paths that resolve outside the uploads dir.
    """
    uploads = Path(settings.uploads_dir).resolve()
    candidate = Path(file_path)
    if not candidate.is_absolute():
        candidate = uploads / candidate
    resolved = candidate.resolve()
    if uploads not in resolved.parents and resolved != uploads:
        raise ValueError(f"Path is outside the uploads directory: {file_path}")
    return resolved


def _ingest_from_path(table: str, file_path: str) -> dict[str, Any]:
    try:
        resolved = _resolve_upload_path(file_path)
    except ValueError as exc:
        return {"error": str(exc)}
    if not resolved.exists() or not resolved.is_file():
        return {"error": f"File not found under uploads: {file_path}"}
    if resolved.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
        return {"error": f"Unsupported file type: {resolved.suffix}"}
    with SessionLocal() as db, resolved.open("rb") as f:
        try:
            result = ingest(table, resolved.name, f, db)
        except Exception as exc:
            detail = getattr(exc, "detail", str(exc))
            return {"error": detail}
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


EXECUTORS: dict[str, Callable[..., dict[str, Any]]] = {
    "list_tables": _list_tables,
    "describe_table": _describe_table,
    "read_rows": _read_rows,
    "run_sql": _run_sql,
    "get_row_counts": _get_row_counts,
    "ingest_from_path": _ingest_from_path,
}


def run_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    fn = EXECUTORS.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**(tool_input or {}))
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
