from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..config import settings
from ..db import engine, readonly_connection
from ..schemas import SqlRequest, SqlResponse
from ..sql_safety import assert_read_only

router = APIRouter()


@router.post("/sql", response_model=SqlResponse)
def run_sql(req: SqlRequest) -> SqlResponse:
    assert_read_only(req.query)
    with readonly_connection() as conn:
        result = conn.execute(text(req.query))
        cols = list(result.keys())
        rows = [list(r) for r in result.fetchall()]
    return SqlResponse(columns=cols, rows=rows, row_count=len(rows))


@router.post("/sql/write", response_model=SqlResponse)
def run_sql_write(req: SqlRequest) -> SqlResponse:
    if not settings.allow_sql_writes:
        raise HTTPException(
            403,
            "SQL writes disabled. Set ALLOW_SQL_WRITES=true to enable this endpoint.",
        )
    with engine.begin() as conn:
        result = conn.execute(text(req.query))
        cols = list(result.keys()) if result.returns_rows else []
        rows = [list(r) for r in result.fetchall()] if result.returns_rows else []
    return SqlResponse(columns=cols, rows=rows, row_count=len(rows))
