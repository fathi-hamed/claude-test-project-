-- Runs on first container start. Creates the read-only role used by /sql.
-- The app role (loan_app) is the bootstrap superuser from POSTGRES_USER.

CREATE ROLE loan_reader LOGIN PASSWORD 'loan_reader_pw';
GRANT CONNECT ON DATABASE loan_db TO loan_reader;
GRANT USAGE ON SCHEMA public TO loan_reader;

-- Grant SELECT on tables created later by Alembic
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO loan_reader;
