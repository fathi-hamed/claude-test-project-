# Data Reference

## Overview

Three normalized tables derived from a flat loan application dataset.
All IDs are string keys (`VARCHAR(10)` or `VARCHAR(20)`).

Sample data: 1 000 applicants, 1 000 employment records, 1 500 loans.

---

## Table: `applicants`

Primary key: `applicant_id`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `applicant_id` | VARCHAR(10) | No | PK — format `A00001` |
| `gender` | VARCHAR(10) | Yes | `Male` / `Female` |
| `married` | VARCHAR(5) | Yes | `Yes` / `No` |
| `dependents` | VARCHAR(5) | Yes | `0` / `1` / `2` / `3+` |
| `education` | VARCHAR(20) | Yes | `Graduate` / `Not Graduate` |

**Required CSV columns (exact names):** `applicant_id`, `gender`, `married`, `dependents`, `education`

---

## Table: `employment`

Primary key: `employment_id` · Foreign key: `applicant_id → applicants`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `employment_id` | VARCHAR(10) | No | PK — format `E00001` |
| `applicant_id` | VARCHAR(10) | Yes | FK → `applicants.applicant_id`, indexed |
| `self_employed` | VARCHAR(5) | Yes | `Yes` / `No` |
| `applicant_income` | INTEGER | Yes | Monthly income in currency units |
| `coapplicant_income` | INTEGER | Yes | Co-applicant monthly income |

**Required CSV columns:** `employment_id`, `applicant_id`, `self_employed`, `applicant_income`, `coapplicant_income`

---

## Table: `loans`

Primary key: `loan_id` · Foreign key: `applicant_id → applicants`

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `loan_id` | VARCHAR(20) | No | PK — format `L00001` |
| `applicant_id` | VARCHAR(10) | Yes | FK → `applicants.applicant_id`, indexed |
| `loan_amount` | FLOAT | Yes | Loan amount in thousands |
| `loan_amount_term` | INTEGER | Yes | Term in months (e.g. 360 = 30 years) |
| `credit_history` | INTEGER | Yes | `1` = good history, `0` = bad/missing |
| `property_area` | VARCHAR(20) | Yes | `Urban` / `Semiurban` / `Rural` |

**Required CSV columns:** `loan_id`, `applicant_id`, `loan_amount`, `loan_amount_term`, `credit_history`, `property_area`

---

## Ingest rules

1. Ingest `applicants` **before** `employment` or `loans` — FK violation rows are rejected and reported.
2. Re-ingesting the same file is safe — duplicate PKs are silently skipped (`ON CONFLICT DO NOTHING`).
3. Extra CSV columns are rejected with a 400 error; missing required columns are also rejected.
4. Null values in optional columns are preserved as `NULL` in the database.

### Ingest response shape

```json
{
  "table": "loans",
  "inserted": 1487,
  "skipped_duplicates": 13,
  "rejected_fk_violations": ["A00999", "A01000"],
  "rejected_rows": 2
}
```

---

## Sample data distribution (data/ CSVs)

| Table | Rows | ID range |
|---|---|---|
| applicants | 1 000 | A00001 – A01000 |
| employment | 1 000 | E00001 – E01000 |
| loans | 1 500 | L00001 – L01500 |

The loans table has ~1.5× more rows than applicants because some applicants have multiple loans.
Not all applicants have a corresponding employment record (outer-join-safe queries recommended).

---

## Value distributions (approximate)

**applicants.gender** — ~65% Male, ~35% Female  
**applicants.married** — ~65% Yes, ~35% No  
**applicants.dependents** — `0` most common, then `1`, `2`, `3+`  
**applicants.education** — ~80% Graduate, ~20% Not Graduate  

**employment.self_employed** — ~85% No, ~15% Yes  
**employment.applicant_income** — range ~1 000–81 000, median ~4 500  
**employment.coapplicant_income** — range 0–41 000, many are 0  

**loans.loan_amount** — range ~9–700 (thousands), median ~130  
**loans.loan_amount_term** — mostly 360 months (30 yr), some 180, 120, 60, 36, 12, 84, 240, 300, 480  
**loans.credit_history** — ~85% = 1 (good), ~15% = 0 (bad/missing)  
**loans.property_area** — ~38% Semiurban, ~33% Urban, ~29% Rural  
