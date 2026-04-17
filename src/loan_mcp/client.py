import os
from pathlib import Path
from typing import Any

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "/data"))
TIMEOUT = httpx.Timeout(60.0)


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=TIMEOUT)


def list_tables() -> Any:
    with _client() as c:
        r = c.get("/tables")
        r.raise_for_status()
        return r.json()


def describe_table(table: str) -> Any:
    with _client() as c:
        r = c.get(f"/tables/{table}/schema")
        r.raise_for_status()
        return r.json()


def read_rows(table: str, limit: int = 50, offset: int = 0) -> Any:
    with _client() as c:
        r = c.get(f"/tables/{table}/rows", params={"limit": limit, "offset": offset})
        r.raise_for_status()
        return r.json()


def run_sql(query: str) -> Any:
    with _client() as c:
        r = c.post("/sql", json={"query": query})
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}
        return r.json()


def ingest_csv(table: str, file_path: str) -> Any:
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}
    with _client() as c, path.open("rb") as f:
        files = {"file": (path.name, f, "application/octet-stream")}
        r = c.post(f"/ingest/{table}", files=files)
        if r.status_code >= 400:
            return {"error": r.text, "status": r.status_code}
        return r.json()


def list_uploads() -> Any:
    if not UPLOADS_DIR.exists():
        return {"uploads_dir": str(UPLOADS_DIR), "error": "directory not mounted"}
    files = [
        {"name": p.name, "path": str(p), "size_bytes": p.stat().st_size}
        for p in sorted(UPLOADS_DIR.iterdir())
        if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xls"}
    ]
    return {"uploads_dir": str(UPLOADS_DIR), "files": files}


def get_row_counts() -> Any:
    tables = list_tables()
    return {t["name"]: t["row_count"] for t in tables}
