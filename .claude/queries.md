# SQL Query Reference

All queries run through `POST /sql` (read-only) or the `run_sql` tool.
Only `SELECT`, `WITH`, and `EXPLAIN` are permitted.

---

## Row counts

```sql
SELECT
    (SELECT COUNT(*) FROM applicants)  AS applicants,
    (SELECT COUNT(*) FROM employment)  AS employment,
    (SELECT COUNT(*) FROM loans)       AS loans;
```

---

## Schema inspection

```sql
-- Column names and types for a table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'loans'
ORDER BY ordinal_position;
```

---

## Basic exploration

```sql
-- First 10 applicants
SELECT * FROM applicants LIMIT 10;

-- Applicants with their loan count
SELECT a.applicant_id, a.education, COUNT(l.loan_id) AS loan_count
FROM applicants a
LEFT JOIN loans l ON a.applicant_id = l.applicant_id
GROUP BY a.applicant_id, a.education
ORDER BY loan_count DESC
LIMIT 20;

-- Applicants who have no employment record
SELECT a.applicant_id
FROM applicants a
LEFT JOIN employment e ON a.applicant_id = e.applicant_id
WHERE e.employment_id IS NULL;
```

---

## Loan analytics

```sql
-- Average loan amount by education level
SELECT a.education,
       ROUND(AVG(l.loan_amount)::numeric, 2) AS avg_loan,
       COUNT(l.loan_id)                       AS loan_count
FROM applicants a
JOIN loans l ON a.applicant_id = l.applicant_id
GROUP BY a.education
ORDER BY avg_loan DESC;

-- Average loan amount by property area
SELECT property_area,
       ROUND(AVG(loan_amount)::numeric, 2) AS avg_loan,
       COUNT(*)                             AS count
FROM loans
GROUP BY property_area
ORDER BY avg_loan DESC;

-- Loan amount distribution buckets
SELECT width_bucket(loan_amount, 0, 700, 7) AS bucket,
       MIN(loan_amount)                      AS min_amount,
       MAX(loan_amount)                      AS max_amount,
       COUNT(*)                              AS count
FROM loans
GROUP BY bucket
ORDER BY bucket;

-- Loans by term length
SELECT loan_amount_term AS term_months,
       COUNT(*)          AS count,
       ROUND(AVG(loan_amount)::numeric, 2) AS avg_amount
FROM loans
GROUP BY loan_amount_term
ORDER BY count DESC;
```

---

## Credit history analysis

```sql
-- Credit history breakdown
SELECT credit_history,
       COUNT(*) AS count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM loans
GROUP BY credit_history
ORDER BY credit_history DESC;

-- Average loan amount by credit history
SELECT credit_history,
       ROUND(AVG(loan_amount)::numeric, 2) AS avg_loan
FROM loans
GROUP BY credit_history;
```

---

## Income analysis

```sql
-- Total household income distribution (applicant + co-applicant)
SELECT applicant_id,
       applicant_income,
       coapplicant_income,
       applicant_income + coapplicant_income AS total_income
FROM employment
ORDER BY total_income DESC
LIMIT 20;

-- Average income by self-employment status
SELECT self_employed,
       ROUND(AVG(applicant_income)::numeric, 0)   AS avg_applicant_income,
       ROUND(AVG(coapplicant_income)::numeric, 0) AS avg_coapplicant_income
FROM employment
GROUP BY self_employed;

-- Loan-to-income ratio (loan_amount is in thousands)
SELECT e.applicant_id,
       e.applicant_income + e.coapplicant_income          AS household_income,
       l.loan_amount,
       ROUND((l.loan_amount * 1000.0 /
         NULLIF(e.applicant_income + e.coapplicant_income, 0))::numeric, 2) AS lti_ratio
FROM employment e
JOIN loans l ON e.applicant_id = l.applicant_id
ORDER BY lti_ratio DESC NULLS LAST
LIMIT 20;
```

---

## Cross-dimensional queries

```sql
-- Loan amount by education × property area
SELECT a.education,
       l.property_area,
       ROUND(AVG(l.loan_amount)::numeric, 2) AS avg_loan,
       COUNT(*)                               AS count
FROM applicants a
JOIN loans l ON a.applicant_id = l.applicant_id
GROUP BY a.education, l.property_area
ORDER BY a.education, l.property_area;

-- Married vs single: loan amounts and income
SELECT a.married,
       ROUND(AVG(e.applicant_income)::numeric, 0)   AS avg_income,
       ROUND(AVG(e.coapplicant_income)::numeric, 0) AS avg_coincome,
       ROUND(AVG(l.loan_amount)::numeric, 2)        AS avg_loan,
       COUNT(l.loan_id)                              AS loan_count
FROM applicants a
LEFT JOIN employment e ON a.applicant_id = e.applicant_id
LEFT JOIN loans l      ON a.applicant_id = l.applicant_id
GROUP BY a.married;

-- Dependents breakdown with average loan
SELECT a.dependents,
       COUNT(DISTINCT a.applicant_id)          AS applicant_count,
       ROUND(AVG(l.loan_amount)::numeric, 2)   AS avg_loan
FROM applicants a
LEFT JOIN loans l ON a.applicant_id = l.applicant_id
GROUP BY a.dependents
ORDER BY a.dependents;
```

---

## Data quality checks

```sql
-- Loans with no matching applicant (should be 0 after clean ingest)
SELECT l.loan_id, l.applicant_id
FROM loans l
LEFT JOIN applicants a ON l.applicant_id = a.applicant_id
WHERE a.applicant_id IS NULL;

-- Applicants with multiple loans
SELECT applicant_id, COUNT(*) AS loan_count
FROM loans
GROUP BY applicant_id
HAVING COUNT(*) > 1
ORDER BY loan_count DESC;

-- NULL value counts per table
SELECT
    SUM(CASE WHEN gender         IS NULL THEN 1 ELSE 0 END) AS gender_nulls,
    SUM(CASE WHEN married        IS NULL THEN 1 ELSE 0 END) AS married_nulls,
    SUM(CASE WHEN dependents     IS NULL THEN 1 ELSE 0 END) AS dependents_nulls,
    SUM(CASE WHEN education      IS NULL THEN 1 ELSE 0 END) AS education_nulls
FROM applicants;

SELECT
    SUM(CASE WHEN self_employed       IS NULL THEN 1 ELSE 0 END) AS self_employed_nulls,
    SUM(CASE WHEN applicant_income    IS NULL THEN 1 ELSE 0 END) AS income_nulls,
    SUM(CASE WHEN coapplicant_income  IS NULL THEN 1 ELSE 0 END) AS coincome_nulls
FROM employment;

SELECT
    SUM(CASE WHEN loan_amount      IS NULL THEN 1 ELSE 0 END) AS amount_nulls,
    SUM(CASE WHEN loan_amount_term IS NULL THEN 1 ELSE 0 END) AS term_nulls,
    SUM(CASE WHEN credit_history   IS NULL THEN 1 ELSE 0 END) AS credit_nulls,
    SUM(CASE WHEN property_area    IS NULL THEN 1 ELSE 0 END) AS area_nulls
FROM loans;
```

---

## Tips for the chat agent

- Always join through `applicant_id` — it's the only FK connecting all three tables.
- `loan_amount` is stored in **thousands** (e.g. `130` = $130 000).
- `credit_history = 1` means **good** credit; `0` means bad or missing.
- `loan_amount_term` is in **months** (360 = 30-year mortgage).
- Use `NULLIF(..., 0)` when dividing by income to avoid division-by-zero.
- Use `::numeric` before `ROUND()` to avoid float precision issues.
