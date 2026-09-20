# Module 4 -- Pytest and Sphinx

**Name:** Laila Afmeged -- JHED: lafmege1
**Module:** Module 4 -- "Pytest and Sphinx"

Builds a real, dependency-injectable test suite (and Sphinx documentation)
around the Flask/PostgreSQL/SQLAlchemy application from Module 3. The
application's behavior is unchanged from Module 3 except where testability
required it (see **What changed from Module 3**, below); the actual data
in the `applicants` table, and every verified query result, are the same.

---

## Setup / How to Run

### 1. PostgreSQL

Same as Module 3 -- Postgres.app on macOS is simplest (no `sudo` needed).
The `applicants` table already exists from Module 3's data load; this
module reuses it as-is.

### 2. Python environment

```
cd module_4
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Credentials

Copy `.env.example` to `.env` and fill in your local Postgres settings
(either a single `DATABASE_URL`, or the individual `DB_*` variables --
both are supported; see `.env.example`). **`.env` is in `.gitignore` and
must never be committed.**

### 4. Run the app

```
python -m src.app
```

then visit `http://127.0.0.1:8080`.

### 5. Run the tests

```
pytest
```

`pytest.ini` already wires up coverage (`--cov=src --cov-report=term-missing
--cov-fail-under=100`), so a plain `pytest` run prints the coverage table
and fails if coverage drops below 100%. A saved passing run is checked in
at `coverage_summary.txt`. Run just one marker with e.g. `pytest -m db`.

The `db` / `integration` tests need a real PostgreSQL server reachable
with your `.env` credentials; they create and use a throwaway
`gradcafe_test` database automatically (never your real `gradcafe`
database). See `docs/testing.rst` for the full breakdown of what each of
the five test files covers and why.

### 6. Build the documentation

```
cd docs
pip install -r requirements.txt
make html
open _build/html/index.html
```

The same docs are set up to publish on Read the Docs via
`.readthedocs.yaml` (repository root) -- publishing there requires the
GitHub repository to be public, which is left to the student's own
judgment/action rather than done automatically here.

---

## What changed from Module 3

Module 3's application behavior is preserved; what changed is how it's
*built*, so it can actually be tested:

- **`create_app(...)` factory** (`src/app.py`) instead of one module-level
  `app` object, taking every external dependency (the analysis-query
  function, the Pull Data starter/status functions) as an optional keyword
  argument. Left unset, each falls back to the real implementation.
- **`DATABASE_URL`** is now the primary way to configure the database
  connection (the old `DB_HOST`/`DB_USER`/... variables still work as a
  fallback), so the test suite and CI can point the app at a different
  database than a developer's own `.env` without touching the environment.
- **`/pull-data` and `/update-analysis` now return JSON**, not a redirect:
  `POST /pull-data` returns `202 {"ok": true}` when idle (starting a pull)
  or `409 {"ok": false, "busy": true}` if one is already running; `POST
  /update-analysis` returns `200 {"ok": true, "results": {...}}` when
  idle, or `409 {"busy": true}` (performing no update) while a pull is in
  progress. A small inline script on the page calls these via `fetch` and
  reloads on response, so the browser experience is unchanged; the JSON
  contract is what makes both routes directly assertable with
  `app.test_client()`.
- **`data-testid` attributes** on every stat, table, and button in
  `templates/index.html`, for stable test selectors.
- **The Pull Data pipeline** (`src/pull_data_pipeline.py`) is refactored
  into `run_pipeline(steps)`, where each step is a small, swappable
  `PipelineStep`. Real usage is unchanged (it still shells out to
  `scrape.py` -> `clean.py` -> `load_data.py`); tests pass fake steps to
  verify the sequencing/error-handling logic without touching a browser,
  network, or database.
- **`load_data.load(...)`** now accepts an explicit `dsn` and returns a
  stats dict (`inserted_or_seen` / `skipped_no_url` / `total_in_table`)
  instead of only printing them, so the `ON CONFLICT (url) DO NOTHING`
  idempotency guarantee can be asserted on directly.

---

## Known limitations carried over from Module 2 / 3

Unchanged from Module 3: the local LLM standardization pass only finished
60 of 30,060 records (`llm_generated_program`/`university` are `NULL` for
the rest), and roughly 60% of raw GRE Quantitative values fall outside the
valid 130-170 ETS scale (excluded from the reported average). See Module
3's `query_results.pdf` / `limitations.pdf` for the full discussion --
those documents and the verified query results themselves are unchanged by
this module.

One new, small note: the page now renders `N/A` instead of crashing if an
average has no matching rows at all (e.g. a GRE average on a very sparse
or freshly-created database) -- this can't happen against the real,
30,060-row `gradcafe` database, but does come up in the test suite's
throwaway test database, which only ever contains the handful of rows a
given test explicitly inserted.

---

## Testing scope

`.coveragerc` intentionally omits `src/scrape.py`, `src/clean.py`, and
`src/llm_hosting/*` from the 100% coverage requirement -- they're Module
2's scraper/cleaner/local-LLM tooling, kept in `src/` because the Pull
Data button still needs them at runtime, but driving a real Selenium
Chrome session to full line coverage is out of scope for a module about
pytest and Sphinx. They're still fully documented via autodoc (see
`docs/api.rst`). See `docs/testing.rst` for the complete reasoning and a
breakdown of what each of the five required test files (`web`, `buttons`,
`analysis`, `db`, `integration` markers) actually tests.

---

## Continuous Integration

`.github/workflows/tests.yml` (repository root, alongside `module_1/`
`module_2/` etc.) runs the full marked pytest suite with coverage against
a disposable `postgres:16` GitHub Actions service container on every push
and pull request. `actions_success.png` (added by hand after pushing) is a
screenshot of that workflow's passing run.

---

## Project structure

```
module_4/
├── src/
│   ├── app.py                  # Flask create_app() factory
│   ├── models.py                # SQLAlchemy Applicant model + engine/session helpers
│   ├── orm_queries.py            # Same 11 questions via SQLAlchemy (unchanged from Module 3)
│   ├── query_data.py             # Raw SQL version of the same questions
│   ├── load_data.py              # Loads cleaned/LLM data into PostgreSQL (ON CONFLICT dedup)
│   ├── pull_data_pipeline.py      # scrape -> clean -> load, now step-injectable
│   ├── scrape.py, clean.py        # reused unmodified from Module 2
│   ├── llm_hosting/                # reused unmodified from Module 2
│   ├── templates/index.html        # Flask page, now with data-testid selectors
│   └── static/style.css
├── tests/
│   ├── conftest.py                 # fixtures: fake app, throwaway test database
│   ├── test_flask_page.py           # marker: web
│   ├── test_buttons.py              # marker: buttons
│   ├── test_analysis_format.py       # marker: analysis
│   ├── test_db_insert.py             # marker: db
│   └── test_integration_end_to_end.py # marker: integration
├── docs/                            # Sphinx source (overview, architecture, autodoc API, testing guide)
├── pytest.ini                       # markers + coverage addopts
├── .coveragerc                      # coverage source/omit configuration
├── coverage_summary.txt             # saved terminal output of a 100%-coverage run
├── requirements.txt
├── .env.example
└── .gitignore
```

`.github/workflows/tests.yml` and `.readthedocs.yaml` live at the
repository root (siblings of `module_1/` / `module_2/` / `module_3/` /
`module_4/`), not inside `module_4/` itself.
