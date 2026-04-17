"""MCP server exposing the loan ingestion service to Claude.

Run as: `python -m loan_mcp.server` (stdio transport).
Reads API_BASE_URL from the environment.
"""
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import client

mcp = FastMCP("loan-data")


@mcp.tool()
def list_uploads() -> str:
    """List CSV/Excel files in the shared uploads directory mounted into the MCP container.

    The user drops files into the host-side `uploads/` folder; they appear here
    at `/data/*`. Call this first to discover filenames, then pass a returned
    `path` to `ingest_csv`. The file bytes never go through the chat context.
    """
    return _json(client.list_uploads())


@mcp.tool()
def ingest_csv(table: str, file_path: str) -> str:
    """Ingest a CSV or Excel file into one of the loan tables.

    `file_path` must be a path the MCP server can read. With the default Docker
    setup, files placed in the host `uploads/` folder appear at `/data/<name>`
    inside the container — use `list_uploads` to discover them.

    Args:
        table: One of "applicants", "employment", "loans".
        file_path: Path to a .csv, .xlsx, or .xls file (typically `/data/<name>`).
    """
    return _json(client.ingest_csv(table, file_path))


@mcp.tool()
def list_tables() -> str:
    """List the 3 loan tables with their current row counts."""
    return _json(client.list_tables())


@mcp.tool()
def describe_table(table: str) -> str:
    """Return columns, types, primary key, and foreign keys for one table.

    Args:
        table: One of "applicants", "employment", "loans".
    """
    return _json(client.describe_table(table))


@mcp.tool()
def read_rows(table: str, limit: int = 50, offset: int = 0) -> str:
    """Read paginated rows from a table.

    Args:
        table: One of "applicants", "employment", "loans".
        limit: Max rows to return (1-1000, default 50).
        offset: Rows to skip (default 0).
    """
    return _json(client.read_rows(table, limit=limit, offset=offset))


@mcp.tool()
def run_sql(query: str) -> str:
    """Run a read-only SQL query (SELECT / WITH / EXPLAIN only).

    Mutating statements are rejected. Use ingest_csv to add data.
    """
    return _json(client.run_sql(query))


@mcp.tool()
def get_row_counts() -> str:
    """Return a {table_name: row_count} mapping for all 3 loan tables."""
    return _json(client.get_row_counts())


def _json(value: Any) -> str:
    return json.dumps(value, default=str, indent=2)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
