"""initial loan schema

Revision ID: 0001
Revises:
Create Date: 2026-04-16

"""
from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applicants",
        sa.Column("applicant_id", sa.String(10), primary_key=True),
        sa.Column("gender", sa.String(10)),
        sa.Column("married", sa.String(5)),
        sa.Column("dependents", sa.String(5)),
        sa.Column("education", sa.String(20)),
    )

    op.create_table(
        "employment",
        sa.Column("employment_id", sa.String(10), primary_key=True),
        sa.Column("applicant_id", sa.String(10), sa.ForeignKey("applicants.applicant_id")),
        sa.Column("self_employed", sa.String(5)),
        sa.Column("applicant_income", sa.Integer),
        sa.Column("coapplicant_income", sa.Integer),
    )
    op.create_index("ix_employment_applicant_id", "employment", ["applicant_id"])

    op.create_table(
        "loans",
        sa.Column("loan_id", sa.String(20), primary_key=True),
        sa.Column("applicant_id", sa.String(10), sa.ForeignKey("applicants.applicant_id")),
        sa.Column("loan_amount", sa.Float),
        sa.Column("loan_amount_term", sa.Integer),
        sa.Column("credit_history", sa.Integer),
        sa.Column("property_area", sa.String(20)),
    )
    op.create_index("ix_loans_applicant_id", "loans", ["applicant_id"])

    # Grant SELECT on the new tables to the read-only role created by init_db.sql.
    # Wrapped in DO block so the migration still works if the role doesn't exist
    # (e.g., when running against a fresh DB outside docker-compose).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'loan_reader') THEN
                GRANT SELECT ON applicants, employment, loans TO loan_reader;
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_loans_applicant_id", table_name="loans")
    op.drop_table("loans")
    op.drop_index("ix_employment_applicant_id", table_name="employment")
    op.drop_table("employment")
    op.drop_table("applicants")
