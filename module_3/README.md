# Module 3 — Database Queries, SQLAlchemy, and Dynamic Webpages

**Name:** Laila Afmeged — JHED: lafmege1
**Module:** Module 3 — "Database Queries, SQLAlchemy, and Dynamic Webpages"

---

## Setup / How to Run

### 1. PostgreSQL

Install PostgreSQL locally if you haven't already (Postgres.app is the
simplest route on macOS: postgresapp.com — no `sudo` needed, just open the
app and click "Initialize"). Once it's running:

```
createdb gradcafe
```

(or create the `gradcafe` database however you prefer — `load_data.py`
creates the `applicants` table itself the first time it runs, so you only
need the empty database to exist first.)

### 2. Python environment

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Credentials

Copy `.env.example` to `.env` and fill in your local Postgres username /
password (Postgres.app's default user has no password, matching your Mac
username — leave `DB_PASSWORD` blank in that case). **`.env` is in
`.gitignore` and must never be committed.**

### 4. Load the data

```
python load_data.py
```

This reads `cleaned_applicant_data.json` (Module 2's cleaned output) and
`llm_extend_applicant_data.json` (Module 2's LLM-standardized output, only
partially complete — see **Known limitation** below) and inserts everything
into the `applicants` table. `url` is a unique key, so re-running this
command never creates duplicate rows.

### 5. Run the raw SQL analysis

```
python query_data.py
```

### 6. Run the same analyses via SQLAlchemy

```
python orm_queries.py
```

### 7. Run the Flask webpage

```
python app.py
```

then visit `http://127.0.0.1:8080`.

**Pull Data** (button on the page) reuses the Module 2 scraper. Exactly as
in Module 2, `scrape.py` attaches to an already-open, manually-launched
Chrome window (`--remote-debugging-port=9222`) rather than driving its own
browser — Grad Cafe sits behind Cloudflare, and a human has to clear any
challenge once before the scraper can read pages. So before clicking Pull
Data, open Chrome by hand with remote debugging enabled and load
`https://www.thegradcafe.com/survey/` once, the same as the Module 2 setup.
Clicking Pull Data then runs `scrape.py` → `clean.py` → `load_data.py` in
the background (see `pull_data_pipeline.py`); only genuinely new records
get added, since `load_data.py`'s dedup logic applies here too.

**Update Analysis** just re-queries PostgreSQL through the ORM and refreshes
the page. It never starts a scrape, and if a Pull Data run is currently in
progress, the page tells you that instead of showing stale-looking "new"
data.

---

## Known limitation carried over from Module 2

The local LLM standardization pass (`llm_hosting/`, TinyLlama on a single
Mac) only finished processing 60 of the 30,060 cleaned records before the
Module 2 deadline — a multi-hour CPU-bound run that didn't fit the time
available. `llm_generated_program` / `llm_generated_university` are
therefore `NULL` for the other 29,940 rows. This directly explains why
Question 9's LLM-field count (0) is lower than Question 8's original-field
count (28) — it's a coverage gap in how much data was standardized, not a
disagreement in how the LLM matches programs/universities. See
`query_results.pdf` and `limitations.pdf` for more detail.

A second, separate data-quality note: roughly 60% of the raw GRE
Quantitative values in the scraped data fall outside the valid 130-170 ETS
scale (some applicants appear to have entered a combined score or a
percentile rank instead). `query_data.py`, `orm_queries.py`, and the Flask
page all restrict the GRE Quant/Verbal averages to the valid range, and this
is disclosed directly in the SQL comments and in `query_results.pdf`.

---

## Part 7: Raw SQL vs. SQLAlchemy comparison

**Question 8** — Fall 2026 PhD Computer Science acceptances at Georgetown,
MIT, Stanford, or Carnegie Mellon, using the original downloaded fields.

**Raw SQL** (`query_data.py`):

```sql
SELECT count(*)
FROM applicants
WHERE term ILIKE 'Fall 2026'
  AND lower(status) = 'accepted'
  AND lower(degree) = 'phd'
  AND program ILIKE '%computer science%'
  AND (
        program ILIKE '%georgetown%'
     OR program ILIKE '%massachusetts institute of technology%'
     OR program ~* '\ymit\y'
     OR program ILIKE '%stanford%'
     OR program ILIKE '%carnegie mellon%'
  );
```

**SQLAlchemy** (`orm_queries.py`):

```python
def _target_school(field):
    return or_(
        field.ilike("%georgetown%"),
        field.ilike("%massachusetts institute of technology%"),
        field.op("~*")(r"\ymit\y"),
        field.ilike("%stanford%"),
        field.ilike("%carnegie mellon%"),
    )

stmt = select(func.count()).select_from(Applicant).where(
    and_(
        Applicant.term.ilike("Fall 2026"),
        func.lower(Applicant.status) == "accepted",
        func.lower(Applicant.degree) == "phd",
        Applicant.program.ilike("%computer science%"),
        _target_school(Applicant.program),
    )
)
count8 = session.execute(stmt).scalar_one()
```

**Comparison:** Both produce the identical count (28) against the same
table, which makes sense since SQLAlchemy's `select()`/`where()` compiles
down to essentially the same SQL under the hood. The SQL version is more
compact and lets you paste it straight into `psql` to sanity-check it by
hand, which made it faster to iterate on the exact MIT word-boundary regex
while exploring the real data. The SQLAlchemy version is more verbose but
gains real advantages: the `_target_school()` helper is trivially reusable
between Question 8 and Question 9 (they differ only in which column is
passed in), Python catches a typo in a column name at import time instead of
at query time, and the whole query is composed from Python objects rather
than string-concatenated SQL, which matters more as an application grows
past a handful of one-off scripts. Raw SQL keeps full, direct control over
exactly what Postgres executes (useful for the `~*` regex and `FILTER`
clauses used elsewhere in this project); the ORM trades a little of that
directness for portability (the same Python code would mostly still work
against a different database engine) and for integration with the rest of a
Python codebase (the Flask app, for instance, reuses these same functions
directly instead of duplicating query logic).

---

## Project structure

```
module_3/
├── load_data.py              # Part 1: loads cleaned data into PostgreSQL
├── query_data.py              # Part 2: raw SQL analysis (Questions 1-9 + 2 original)
├── models.py                  # Part 5: SQLAlchemy Applicant model + Engine/Session
├── orm_queries.py              # Part 6: same analyses via SQLAlchemy
├── app.py                     # Part 8-10: Flask webpage (Pull Data / Update Analysis)
├── pull_data_pipeline.py       # Part 9: scrape -> clean -> load, run by the Pull Data button
├── templates/index.html        # Flask analysis page
├── static/style.css            # Flask page styling
├── query_results.pdf           # Part 4: all 11 questions, results, SQL, explanations
├── limitations.pdf             # Part 11: written reflection
├── generate_query_results_pdf.py  # script used to build query_results.pdf
├── generate_limitations_pdf.py    # script used to build limitations.pdf
├── scrape.py, clean.py, llm_hosting/  # reused Module 2 code (for Pull Data)
├── cleaned_applicant_data.json         # Module 2's cleaned output (loader input)
├── llm_extend_applicant_data.json      # Module 2's LLM output (60/30,060 rows)
├── screenshots/                # raw SQL / ORM console output, running Flask page
├── requirements.txt
├── .env.example                # copy to .env with your own local credentials
└── github.txt                  # SSH URL to the private GitHub repo
```
