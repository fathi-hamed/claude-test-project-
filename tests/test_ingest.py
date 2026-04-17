from io import BytesIO

import pandas as pd
import pytest
from fastapi import HTTPException

from loan_api.ingest import ingest


def _csv(rows: list[dict]) -> tuple[str, BytesIO]:
    buf = BytesIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    buf.seek(0)
    return "test.csv", buf


def _seed_applicants(db, ids: list[str]) -> None:
    name, fileobj = _csv(
        [
            {
                "applicant_id": aid,
                "gender": "Male",
                "married": "Yes",
                "dependents": "0",
                "education": "Graduate",
            }
            for aid in ids
        ]
    )
    ingest("applicants", name, fileobj, db)


def test_ingest_applicants_happy_path(db_session):
    name, fileobj = _csv(
        [
            {
                "applicant_id": "A001",
                "gender": "Male",
                "married": "Yes",
                "dependents": "0",
                "education": "Graduate",
            },
            {
                "applicant_id": "A002",
                "gender": "Female",
                "married": "No",
                "dependents": "1",
                "education": "Graduate",
            },
        ]
    )
    result = ingest("applicants", name, fileobj, db_session)
    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert result.rejected_rows == 0


def test_ingest_dedup_on_pk(db_session):
    _seed_applicants(db_session, ["A001"])
    name, fileobj = _csv(
        [
            {
                "applicant_id": "A001",
                "gender": "Male",
                "married": "Yes",
                "dependents": "0",
                "education": "Graduate",
            },
            {
                "applicant_id": "A002",
                "gender": "Male",
                "married": "Yes",
                "dependents": "0",
                "education": "Graduate",
            },
        ]
    )
    result = ingest("applicants", name, fileobj, db_session)
    assert result.inserted == 1
    assert result.skipped_duplicates == 1


def test_ingest_fk_violation_for_loans(db_session):
    _seed_applicants(db_session, ["A001"])
    name, fileobj = _csv(
        [
            {
                "loan_id": "L001",
                "applicant_id": "A001",
                "loan_amount": 100.0,
                "loan_amount_term": 360,
                "credit_history": 1,
                "property_area": "Urban",
            },
            {
                "loan_id": "L002",
                "applicant_id": "A_MISSING",
                "loan_amount": 50.0,
                "loan_amount_term": 180,
                "credit_history": 0,
                "property_area": "Rural",
            },
        ]
    )
    result = ingest("loans", name, fileobj, db_session)
    assert result.inserted == 1
    assert result.rejected_rows == 1
    assert "A_MISSING" in result.rejected_fk_violations


def test_missing_required_column(db_session):
    name, fileobj = _csv(
        [{"applicant_id": "A001", "gender": "Male"}]  # missing married/dependents/education
    )
    with pytest.raises(HTTPException) as exc:
        ingest("applicants", name, fileobj, db_session)
    assert exc.value.status_code == 400
    assert "Missing required columns" in exc.value.detail


def test_unexpected_column_rejected(db_session):
    name, fileobj = _csv(
        [
            {
                "applicant_id": "A001",
                "gender": "Male",
                "married": "Yes",
                "dependents": "0",
                "education": "Graduate",
                "extra_col": "x",
            }
        ]
    )
    with pytest.raises(HTTPException) as exc:
        ingest("applicants", name, fileobj, db_session)
    assert exc.value.status_code == 400


def test_unknown_table(db_session):
    name, fileobj = _csv([{"x": 1}])
    with pytest.raises(HTTPException) as exc:
        ingest("nope", name, fileobj, db_session)
    assert exc.value.status_code == 404


def test_excel_file_supported(db_session):
    df = pd.DataFrame(
        [
            {
                "applicant_id": "A100",
                "gender": "Female",
                "married": "No",
                "dependents": "0",
                "education": "Graduate",
            }
        ]
    )
    buf = BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)
    result = ingest("applicants", "test.xlsx", buf, db_session)
    assert result.inserted == 1
