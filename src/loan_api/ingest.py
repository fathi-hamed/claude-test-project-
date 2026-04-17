from io import BytesIO
from typing import IO

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import Applicant, TABLE_MODELS
from .schemas import IngestResult


def _insert_ignore(dialect_name: str, table, rows, pk):
    if dialect_name == "postgresql":
        return pg_insert(table).values(rows).on_conflict_do_nothing(index_elements=[pk])
    if dialect_name == "sqlite":
        return sqlite_insert(table).values(rows).on_conflict_do_nothing(index_elements=[pk])
    raise HTTPException(500, f"Unsupported DB dialect: {dialect_name}")

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "applicants": ["applicant_id", "gender", "married", "dependents", "education"],
    "employment": [
        "employment_id",
        "applicant_id",
        "self_employed",
        "applicant_income",
        "coapplicant_income",
    ],
    "loans": [
        "loan_id",
        "applicant_id",
        "loan_amount",
        "loan_amount_term",
        "credit_history",
        "property_area",
    ],
}

PK_COLUMN: dict[str, str] = {
    "applicants": "applicant_id",
    "employment": "employment_id",
    "loans": "loan_id",
}


def _parse_file(filename: str, fileobj: IO[bytes]) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(fileobj)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(fileobj.read()))
    raise HTTPException(400, f"Unsupported file type: {filename}")


def _validate_columns(df: pd.DataFrame, table: str) -> None:
    required = set(REQUIRED_COLUMNS[table])
    actual = set(df.columns)
    missing = required - actual
    if missing:
        raise HTTPException(400, f"Missing required columns: {sorted(missing)}")
    extra = actual - required
    if extra:
        raise HTTPException(400, f"Unexpected columns: {sorted(extra)}")


def ingest(table: str, filename: str, fileobj: IO[bytes], db: Session) -> IngestResult:
    if table not in TABLE_MODELS:
        raise HTTPException(404, f"Unknown table: {table}")

    df = _parse_file(filename, fileobj)
    _validate_columns(df, table)
    df = df[REQUIRED_COLUMNS[table]]
    df = df.where(pd.notna(df), None)

    rejected_fk: list[str] = []
    if table in ("employment", "loans"):
        existing_ids = set(db.scalars(select(Applicant.applicant_id)).all())
        mask = df["applicant_id"].isin(existing_ids)
        rejected_fk = df.loc[~mask, "applicant_id"].astype(str).tolist()
        df = df.loc[mask]

    rows = df.to_dict(orient="records")
    if not rows:
        return IngestResult(
            table=table,
            inserted=0,
            skipped_duplicates=0,
            rejected_fk_violations=rejected_fk,
            rejected_rows=len(rejected_fk),
        )

    model = TABLE_MODELS[table]
    pk = PK_COLUMN[table]
    stmt = _insert_ignore(db.bind.dialect.name, model.__table__, rows, pk)
    result = db.execute(stmt)
    db.commit()

    inserted = result.rowcount or 0
    skipped = len(rows) - inserted

    return IngestResult(
        table=table,
        inserted=inserted,
        skipped_duplicates=skipped,
        rejected_fk_violations=rejected_fk,
        rejected_rows=len(rejected_fk),
    )
