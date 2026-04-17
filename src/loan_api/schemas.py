from typing import Any

from pydantic import BaseModel


class IngestResult(BaseModel):
    table: str
    inserted: int
    skipped_duplicates: int
    rejected_fk_violations: list[str]
    rejected_rows: int


class TableInfo(BaseModel):
    name: str
    row_count: int


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool
    foreign_key: str | None


class TableSchema(BaseModel):
    name: str
    columns: list[ColumnInfo]


class RowsResponse(BaseModel):
    table: str
    limit: int
    offset: int
    rows: list[dict[str, Any]]


class SqlRequest(BaseModel):
    query: str


class SqlResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
