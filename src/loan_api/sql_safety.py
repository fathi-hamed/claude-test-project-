import sqlparse
from fastapi import HTTPException

ALLOWED_STATEMENTS = {"SELECT", "WITH", "EXPLAIN"}


def assert_read_only(query: str) -> None:
    """Reject any statement that isn't a SELECT/WITH/EXPLAIN.

    The read-only DB role is the primary defense; this is belt-and-suspenders
    so accidental writes fail fast with a 400 instead of leaking a DB error.
    """
    statements = [s for s in sqlparse.parse(query) if s.tokens]
    if not statements:
        raise HTTPException(400, "Empty query")
    if len(statements) > 1:
        raise HTTPException(400, "Only a single statement is allowed")

    stmt_type = statements[0].get_type().upper()
    if stmt_type not in ALLOWED_STATEMENTS:
        raise HTTPException(
            400,
            f"Only read-only queries are allowed (got {stmt_type}). "
            "Use POST /sql/write for mutations.",
        )
