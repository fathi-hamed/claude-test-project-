from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import chat
from .db import engine
from .routes import ingest, sql, tables

app = FastAPI(title="Loan Data Ingestion Service", version="0.1.0")

app.include_router(ingest.router, tags=["ingest"])
app.include_router(tables.router, tags=["tables"])
app.include_router(sql.router, tags=["sql"])
app.include_router(chat.router, tags=["chat"])

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
