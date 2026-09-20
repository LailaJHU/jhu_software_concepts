"""
load_data.py

Loads the cleaned Module 2 Grad Cafe data (``cleaned_applicant_data.json``)
and, where available, the LLM-standardized fields
(``llm_extend_applicant_data.json``) into a PostgreSQL ``applicants`` table.

Connection settings are read from environment variables (never hardcoded /
committed); ``load(..., dsn=...)`` also accepts an explicit DSN so callers
(including the test suite, against a throwaway test database) can bypass
the environment entirely.

Usage::

    python load_data.py
    python load_data.py --cleaned cleaned_applicant_data.json --llm llm_extend_applicant_data.json

Design notes:

- ``url`` is the natural unique key for a Grad Cafe entry, so the table has
  a UNIQUE constraint on ``url`` and inserts use ``ON CONFLICT (url) DO
  NOTHING``. This means re-running the loader (or the Flask "Pull Data"
  button, which calls this same insert path after scraping) never creates
  duplicate rows, and only genuinely new entries get added.
- Every optional field (gpa, gre, gre_v, gre_aw, comments, llm-generated
  fields) is allowed to be NULL. A record missing one or more of these still
  loads successfully -- only a missing/invalid ``url`` causes a row to be
  skipped, since url is what the whole dedup strategy depends on.
- ``program`` is stored as the combined "Department/Program, University"
  string (matching the convention the instructor-provided LLM tool expects),
  reconstructed from Module 2's already-split ``program`` / ``university``
  fields.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()  # loads .env if present; no-op otherwise


def build_dsn() -> str:
    """Assembles a libpq-style DSN from the ``DB_*`` environment variables
    (or translates ``DATABASE_URL`` into one if that is set instead)."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url.replace("postgresql+psycopg://", "postgresql://")
    return (
        f"dbname={os.environ.get('DB_NAME', 'gradcafe')} "
        f"user={os.environ.get('DB_USER', 'postgres')} "
        f"password={os.environ.get('DB_PASSWORD', '')} "
        f"host={os.environ.get('DB_HOST', 'localhost')} "
        f"port={os.environ.get('DB_PORT', '5432')}"
    )


def get_connection(dsn: str | None = None):
    """Connect to PostgreSQL. Pass ``dsn`` explicitly to bypass the
    environment (used by the test suite against a test database)."""
    try:
        return psycopg.connect(dsn or build_dsn())
    except psycopg.OperationalError as e:  # pragma: no cover - depends on a live DB outage
        print(f"[load_data] Could not connect to PostgreSQL: {e}", file=sys.stderr)
        print(
            "[load_data] Check that PostgreSQL is running and that DATABASE_URL "
            "(or DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT) is set "
            "correctly (see .env.example).",
            file=sys.stderr,
        )
        raise


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS applicants (
    p_id                      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    program                   TEXT,
    comments                  TEXT,
    date_added                DATE,
    url                       TEXT UNIQUE,
    status                    TEXT,
    term                      TEXT,
    us_or_international       TEXT,
    gpa                       FLOAT,
    gre                       FLOAT,
    gre_v                     FLOAT,
    gre_aw                    FLOAT,
    degree                    TEXT,
    llm_generated_program     TEXT,
    llm_generated_university  TEXT
);
"""

INSERT_SQL = """
INSERT INTO applicants (
    program, comments, date_added, url, status, term, us_or_international,
    gpa, gre, gre_v, gre_aw, degree, llm_generated_program, llm_generated_university
) VALUES (
    %(program)s, %(comments)s, %(date_added)s, %(url)s, %(status)s, %(term)s,
    %(us_or_international)s, %(gpa)s, %(gre)s, %(gre_v)s, %(gre_aw)s, %(degree)s,
    %(llm_generated_program)s, %(llm_generated_university)s
)
ON CONFLICT (url) DO NOTHING;
"""


def parse_date(raw: str | None):
    """'Sep 12, 2026' -> date(2026, 9, 12). Returns None if missing/unparseable."""
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%b %d, %Y").date()
    except ValueError:
        return None


def parse_float(raw) -> float | None:
    """Best-effort float coercion. Returns None for missing/unparseable values
    rather than raising, so a bad/blank GPA or GRE score never crashes the load."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    raw = str(raw).strip()
    if raw == "" or raw.upper() in {"N/A", "NA", "--"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def build_record(row: dict, llm_row: dict | None) -> dict:
    """Turns one cleaned Module 2 row (plus its optional matching LLM row)
    into the dict of column values ``INSERT_SQL`` expects."""
    program = (row.get("program") or "").strip()
    university = (row.get("university") or "").strip()
    if program and university:
        combined_program = f"{program}, {university}"
    else:
        combined_program = program or university or None

    return {
        "program": combined_program,
        "comments": row.get("comments") or None,
        "date_added": parse_date(row.get("date_added")),
        "url": row.get("url") or None,
        "status": row.get("status") or None,
        "term": row.get("term") or None,
        "us_or_international": row.get("US/International") or None,
        "gpa": parse_float(row.get("GPA")),
        "gre": parse_float(row.get("GRE")),
        "gre_v": parse_float(row.get("GRE V")),
        "gre_aw": parse_float(row.get("GRE AW")),
        "degree": row.get("Degree") or None,
        "llm_generated_program": (llm_row or {}).get("llm-generated-program"),
        "llm_generated_university": (llm_row or {}).get("llm-generated-university"),
    }


def load(cleaned_path: str, llm_path: str | None, dsn: str | None = None) -> dict:
    """Loads ``cleaned_path`` (and, if present, ``llm_path``) into the
    ``applicants`` table and returns a small stats dict:
    ``{"inserted_or_seen": int, "skipped_no_url": int, "total_in_table": int}``.

    Returning stats (instead of only printing them, as Module 3 did) is
    what lets the ``db``-marked tests assert on the outcome of a load
    directly, and is also what makes the ``ON CONFLICT`` idempotency
    property easy to test: loading the same file twice should leave
    ``total_in_table`` unchanged the second time.
    """
    cleaned_data = json.loads(Path(cleaned_path).read_text(encoding="utf-8"))

    llm_by_url: dict[str, dict] = {}
    if llm_path and Path(llm_path).exists():
        llm_data = json.loads(Path(llm_path).read_text(encoding="utf-8"))
        llm_by_url = {r["url"]: r for r in llm_data if r.get("url")}
    else:
        print(f"[load_data] No LLM output file found at {llm_path!r} -- "
              f"llm_generated_program/university will be NULL for all rows.")

    skipped_no_url = 0
    inserted_or_seen = 0

    with get_connection(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)

            for row in cleaned_data:
                url = row.get("url")
                if not url:
                    skipped_no_url += 1
                    continue
                record = build_record(row, llm_by_url.get(url))
                cur.execute(INSERT_SQL, record)
                inserted_or_seen += 1

        conn.commit()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM applicants;")
            total_in_table = cur.fetchone()[0]

    print(f"[load_data] Processed {inserted_or_seen} records "
          f"({skipped_no_url} skipped for missing url).")
    print(f"[load_data] applicants table now has {total_in_table} total rows "
          f"(duplicates from re-running this loader are skipped via ON CONFLICT).")

    return {
        "inserted_or_seen": inserted_or_seen,
        "skipped_no_url": skipped_no_url,
        "total_in_table": total_in_table,
    }


def main():  # pragma: no cover - CLI console output, exercised only interactively
    parser = argparse.ArgumentParser(description="Load cleaned Grad Cafe data into PostgreSQL.")
    parser.add_argument("--cleaned", default="cleaned_applicant_data.json",
                         help="Path to Module 2's cleaned data file.")
    parser.add_argument("--llm", default="llm_extend_applicant_data.json",
                         help="Path to the LLM-standardized output file (optional).")
    args = parser.parse_args()
    load(args.cleaned, args.llm)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
