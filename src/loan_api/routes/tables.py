from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import TABLE_MODELS
from ..schemas import ColumnInfo, RowsResponse, TableInfo, TableSchema

router = APIRouter()


@router.get("/tables", response_model=list[TableInfo])
def list_tables(db: Session = Depends(get_session)) -> list[TableInfo]:
    out: list[TableInfo] = []
    for name, model in TABLE_MODELS.items():
        count = db.scalar(select(func.count()).select_from(model)) or 0
        out.append(TableInfo(name=name, row_count=count))
    return out


@router.get("/tables/{name}/schema", response_model=TableSchema)
def describe_table(name: str) -> TableSchema:
    if name not in TABLE_MODELS:
        raise HTTPException(404, f"Unknown table: {name}")
    table = TABLE_MODELS[name].__table__
    cols: list[ColumnInfo] = []
    for col in table.columns:
        fk = next(iter(col.foreign_keys), None)
        cols.append(
            ColumnInfo(
                name=col.name,
                type=str(col.type),
                nullable=bool(col.nullable),
                primary_key=col.primary_key,
                foreign_key=str(fk.column) if fk else None,
            )
        )
    return TableSchema(name=name, columns=cols)


@router.get("/tables/{name}/rows", response_model=RowsResponse)
def read_rows(
    name: str,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_session),
) -> RowsResponse:
    if name not in TABLE_MODELS:
        raise HTTPException(404, f"Unknown table: {name}")
    model = TABLE_MODELS[name]
    rows = db.execute(select(model).limit(limit).offset(offset)).scalars().all()
    cols = [c.name for c in inspect(model).columns]
    serialized = [{c: getattr(r, c) for c in cols} for r in rows]
    return RowsResponse(table=name, limit=limit, offset=offset, rows=serialized)
