"""
test_db_insert.py -- marker: db

Exercises :mod:`load_data` against a real (throwaway) PostgreSQL database:
parsing helpers, record building, and -- the key behavior this module
depends on -- that loading the same file twice never creates duplicate
rows, because every insert goes through ``ON CONFLICT (url) DO NOTHING``.
"""

from __future__ import annotations

import json

import pytest

from src import load_data, models, orm_queries as oq, query_data

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Connection-string configuration -- deterministic via monkeypatch, so these
# don't depend on whatever happens to be set in the ambient environment.
# ---------------------------------------------------------------------------

def test_build_database_url_prefers_database_url_env_var(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://explicit:url@example.com/db")
    assert models.build_database_url() == "postgresql+psycopg://explicit:url@example.com/db"


def test_build_database_url_falls_back_to_db_star_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "alice")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_HOST", "db.example.com")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "mydb")
    assert models.build_database_url() == (
        "postgresql+psycopg://alice:secret@db.example.com:5433/mydb"
    )


def test_build_database_url_omits_colon_when_password_blank(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "alice")
    monkeypatch.setenv("DB_PASSWORD", "")
    assert "alice@" in models.build_database_url()


def test_make_engine_uses_explicit_url_without_touching_environment():
    engine = models.make_engine("postgresql+psycopg://x:y@localhost/z")
    assert str(engine.url) in ("postgresql+psycopg://x:***@localhost/z",
                                "postgresql+psycopg://x:y@localhost/z")


def test_make_session_factory_binds_to_the_given_engine():
    engine = models.make_engine("postgresql+psycopg://x:y@localhost/z")
    factory = models.make_session_factory(engine=engine)
    session = factory()
    try:
        assert session.get_bind() is engine
    finally:
        session.close()


@pytest.mark.parametrize("module", [load_data, query_data])
def test_build_dsn_prefers_database_url(monkeypatch, module):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@example.com:5432/db")
    assert module.build_dsn() == "postgresql://u:p@example.com:5432/db"


@pytest.mark.parametrize("module", [load_data, query_data])
def test_build_dsn_falls_back_to_db_star_vars(monkeypatch, module):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_NAME", "somedb")
    monkeypatch.setenv("DB_USER", "someone")
    monkeypatch.setenv("DB_PASSWORD", "")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5432")
    dsn = module.build_dsn()
    assert "dbname=somedb" in dsn
    assert "user=someone" in dsn


# ---------------------------------------------------------------------------
# Pure parsing/formatting helpers -- no database needed.
# ---------------------------------------------------------------------------

def test_parse_date_valid():
    assert load_data.parse_date("Sep 12, 2026").isoformat() == "2026-09-12"


@pytest.mark.parametrize("raw", [None, "", "not a date"])
def test_parse_date_invalid_returns_none(raw):
    assert load_data.parse_date(raw) is None


@pytest.mark.parametrize("raw,expected", [
    (None, None), ("", None), ("n/a", None), ("--", None),
    ("3.75", 3.75), (4, 4.0), (3.5, 3.5), ("not-a-number", None),
])
def test_parse_float_cases(raw, expected):
    assert load_data.parse_float(raw) == expected


def test_build_record_combines_program_and_university():
    record = load_data.build_record(
        {"program": "Computer Science", "university": "Johns Hopkins",
         "url": "https://example.com/1", "GPA": "3.9"},
        llm_row=None,
    )
    assert record["program"] == "Computer Science, Johns Hopkins"
    assert record["gpa"] == 3.9
    assert record["llm_generated_program"] is None


def test_build_record_uses_llm_row_when_present():
    record = load_data.build_record(
        {"program": "CS", "university": "MIT", "url": "https://example.com/2"},
        llm_row={"llm-generated-program": "Computer Science",
                 "llm-generated-university": "MIT"},
    )
    assert record["llm_generated_program"] == "Computer Science"
    assert record["llm_generated_university"] == "MIT"


@pytest.mark.parametrize("row,expected_program", [
    ({"program": "Computer Science", "university": ""}, "Computer Science"),
    ({"program": "", "university": "Johns Hopkins"}, "Johns Hopkins"),
    ({"program": "", "university": ""}, None),
    ({}, None),
])
def test_build_record_falls_back_when_only_one_side_present(row, expected_program):
    """Covers the case where program and university aren't both given --
    e.g. a row Module 2 only partially parsed."""
    record = load_data.build_record({**row, "url": "https://example.com/x"}, llm_row=None)
    assert record["program"] == expected_program


# ---------------------------------------------------------------------------
# Real database behavior.
# ---------------------------------------------------------------------------

@pytest.fixture()
def cleaned_data_file(tmp_path):
    rows = [
        {"program": "Computer Science", "university": "Johns Hopkins",
         "url": "https://example.com/applicant/1", "status": "Accepted",
         "term": "Fall 2026", "US/International": "American", "GPA": "3.9",
         "GRE": "168", "GRE V": "162", "GRE AW": "4.5", "Degree": "PhD",
         "comments": "great fit", "date_added": "Sep 12, 2026"},
        {"program": "Data Science", "university": "Georgetown",
         "url": "https://example.com/applicant/2", "status": "Rejected",
         "term": "Fall 2026", "US/International": "International", "GPA": "3.6",
         "Degree": "Masters", "date_added": "Sep 10, 2026"},
    ]
    path = tmp_path / "cleaned_applicant_data.json"
    path.write_text(json.dumps(rows))
    return path


def test_load_inserts_every_row_with_a_url(test_db_dsn, cleaned_data_file):
    stats = load_data.load(str(cleaned_data_file), None, dsn=test_db_dsn)
    assert stats == {"inserted_or_seen": 2, "skipped_no_url": 0, "total_in_table": 2}


def test_load_skips_rows_without_a_url(test_db_dsn, tmp_path):
    rows = [{"program": "No URL Program", "university": "Nowhere U"}]
    path = tmp_path / "cleaned_no_url.json"
    path.write_text(json.dumps(rows))

    stats = load_data.load(str(path), None, dsn=test_db_dsn)
    assert stats == {"inserted_or_seen": 0, "skipped_no_url": 1, "total_in_table": 0}


def test_load_is_idempotent_on_conflict_url(test_db_dsn, cleaned_data_file):
    """Loading the same file twice must not create duplicate rows -- the
    exact behavior the Pull Data button depends on when re-run."""
    first = load_data.load(str(cleaned_data_file), None, dsn=test_db_dsn)
    second = load_data.load(str(cleaned_data_file), None, dsn=test_db_dsn)

    assert first["total_in_table"] == 2
    assert second["total_in_table"] == 2
    assert second["inserted_or_seen"] == 2  # both rows were re-attempted...
    # ...but ON CONFLICT (url) DO NOTHING means the table size never grew.


def test_load_merges_llm_fields_by_url(test_db_dsn, cleaned_data_file, tmp_path):
    llm_rows = [{"url": "https://example.com/applicant/1",
                 "llm-generated-program": "Computer Science",
                 "llm-generated-university": "Johns Hopkins University"}]
    llm_path = tmp_path / "llm_extend_applicant_data.json"
    llm_path.write_text(json.dumps(llm_rows))

    load_data.load(str(cleaned_data_file), str(llm_path), dsn=test_db_dsn)

    import psycopg
    with psycopg.connect(test_db_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT llm_generated_program, llm_generated_university "
                "FROM applicants WHERE url = %s",
                ("https://example.com/applicant/1",),
            )
            row = cur.fetchone()
    assert row == ("Computer Science", "Johns Hopkins University")


def test_load_with_missing_llm_file_leaves_llm_fields_null(test_db_dsn, cleaned_data_file):
    load_data.load(str(cleaned_data_file), "does_not_exist.json", dsn=test_db_dsn)

    import psycopg
    with psycopg.connect(test_db_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT llm_generated_program FROM applicants "
                "WHERE url = %s",
                ("https://example.com/applicant/1",),
            )
            (value,) = cur.fetchone()
    assert value is None


# ---------------------------------------------------------------------------
# query_data.py -- the raw-SQL counterpart to orm_queries.py (Part 2 vs.
# Part 6 from Module 3). Exercised against the same throwaway database.
# ---------------------------------------------------------------------------

def test_query_data_get_connection_and_run(test_db_dsn, cleaned_data_file):
    load_data.load(str(cleaned_data_file), None, dsn=test_db_dsn)

    with query_data.get_connection(test_db_dsn) as conn:
        with conn.cursor() as cur:
            rows = query_data.run(cur, query_data.Q1_SQL)
    assert rows == [(2,)]  # both rows in cleaned_data_file are term="Fall 2026"


# ---------------------------------------------------------------------------
# orm_queries.py against an EMPTY table -- covers the "no matching rows"
# guard in every question (each returns None/0/[] rather than crashing on a
# NULL/NULLIF-by-zero division). The populated-data path for these same
# functions is covered by test_integration_end_to_end.py's real-app test;
# together the two datasets cover every line in orm_queries.py.
# ---------------------------------------------------------------------------

def test_orm_queries_return_safe_defaults_on_an_empty_table(test_database_url, test_db_dsn):
    session_factory = models.make_session_factory(database_url=test_database_url)
    with session_factory() as session:
        assert oq.q1_fall_2026_count(session) == 0
        assert oq.q2_percent_international(session) is None
        q3 = oq.q3_averages(session)
        assert q3 == {
            "avg_gpa": None, "avg_gre_quant": None,
            "avg_gre_verbal": None, "avg_gre_aw": None,
        }
        assert oq.q4_avg_gpa_american_fall_2026(session) is None
        assert oq.q5_fall_2025_acceptance_pct(session) is None
        assert oq.q6_avg_gpa_accepted_fall_2026(session) is None
        assert oq.q7_jhu_masters_cs_count(session) == 0
        assert oq.q8_fall_2026_phd_cs_acceptances_original_fields(session) == 0
        assert oq.q9_fall_2026_phd_cs_acceptances_llm_fields(session) == 0
        assert oq.original_gpa_bucket_acceptance(session) == []
        assert oq.original_degree_breakdown(session) == []


