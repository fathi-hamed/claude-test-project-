import pytest
from fastapi import HTTPException

from loan_api.sql_safety import assert_read_only


def test_select_allowed():
    assert_read_only("SELECT * FROM applicants")


def test_with_allowed():
    assert_read_only("WITH x AS (SELECT 1) SELECT * FROM x")


def test_explain_allowed():
    assert_read_only("EXPLAIN SELECT * FROM loans")


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO applicants VALUES ('A1','M','No','0','Graduate')",
        "UPDATE loans SET loan_amount = 0",
        "DELETE FROM employment",
        "DROP TABLE loans",
        "TRUNCATE applicants",
        "ALTER TABLE loans ADD COLUMN x INT",
        "CREATE TABLE foo (id INT)",
    ],
)
def test_mutations_rejected(query):
    with pytest.raises(HTTPException) as exc:
        assert_read_only(query)
    assert exc.value.status_code == 400


def test_multiple_statements_rejected():
    with pytest.raises(HTTPException):
        assert_read_only("SELECT 1; SELECT 2;")


def test_empty_rejected():
    with pytest.raises(HTTPException):
        assert_read_only("   ")
