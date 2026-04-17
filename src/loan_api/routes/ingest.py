from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from ..db import get_session
from ..ingest import ingest
from ..schemas import IngestResult

router = APIRouter()


@router.post("/ingest/{table}", response_model=IngestResult)
def ingest_file(
    table: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> IngestResult:
    return ingest(table, file.filename or "", file.file, db)
