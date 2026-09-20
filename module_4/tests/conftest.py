"""
conftest.py

Shared fixtures for the whole test suite.

Two different "worlds" are used across the five test files:

- ``web`` / ``buttons`` / ``analysis`` tests use the ``client`` fixture,
  which builds a Flask app entirely from fakes (``FAKE_RESULTS`` and a
  ``FakePullState``) via ``create_app``'s dependency injection. No real
  database, subprocess, or network call is ever touched by these tests.
- ``db`` / ``integration`` tests use ``test_db_dsn`` / ``db_session_factory``,
  which point at a real, throwaway PostgreSQL database (created
  automatically if it doesn't exist yet) so the actual ``ON CONFLICT (url)
  DO NOTHING`` idempotency behavior of :mod:`load_data` is exercised for
  real, not mocked away.

The throwaway test database is named ``gradcafe_test`` by default (never
the real ``gradcafe`` database a developer might have data in). In CI, the
``tests.yml`` workflow instead sets ``DATABASE_URL`` to point at a fresh
Postgres service container, and these fixtures use that directly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.app import create_app  # noqa: E402
from src.load_data import SCHEMA_SQL  # noqa: E402
from src.models import make_engine, make_session_factory  # noqa: E402


def _pg_conn_kwargs(dbname: str) -> dict:
    return {
        "dbname": dbname,
        "user": os.environ.get("DB_USER", os.environ.get("USER", "postgres")),
        "password": os.environ.get("DB_PASSWORD", ""),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
    }


def _build_test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    kwargs = _pg_conn_kwargs(os.environ.get("DB_NAME_TEST", "gradcafe_test"))
    auth = f"{kwargs['user']}:{kwargs['password']}" if kwargs["password"] else kwargs["user"]
    return f"postgresql+psycopg://{auth}@{kwargs['host']}:{kwargs['port']}/{kwargs['dbname']}"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Ensures a throwaway PostgreSQL database exists for the test session
    (creating it if necessary -- skipped when CI/an override already
    provides ``DATABASE_URL``/``TEST_DATABASE_URL``) and returns its URL."""
    url = _build_test_database_url()
    if os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        return url

    dbname = os.environ.get("DB_NAME_TEST", "gradcafe_test")
    admin_kwargs = _pg_conn_kwargs("postgres")
    try:
        with psycopg.connect(**admin_kwargs, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{dbname}"')
    except psycopg.OperationalError as exc:
        pytest.skip(f"No local PostgreSQL server reachable to create a test database: {exc}")
    return url


@pytest.fixture()
def test_db_dsn(test_database_url) -> str:
    """A plain psycopg DSN (no ``+psycopg`` SQLAlchemy suffix) for the
    throwaway test database, with the ``applicants`` table created and
    truncated so every test starts from a known-empty table."""
    dsn = test_database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute("TRUNCATE TABLE applicants RESTART IDENTITY")
        conn.commit()
    return dsn


@pytest.fixture()
def db_session_factory(test_database_url, test_db_dsn):
    """An SQLAlchemy session factory bound to the same (already-truncated)
    test database as ``test_db_dsn``, for ORM-level assertions."""
    engine = make_engine(test_database_url)
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))
    yield make_session_factory(engine=engine)
    engine.dispose()


FAKE_RESULTS = {
    "q1_fall_2026_count": 29637,
    "q2_percent_international": 46.36,
    "q3_avg_gpa": 3.77,
    "q3_avg_gre_quant": 165.83,
    "q3_avg_gre_verbal": 160.71,
    "q3_avg_gre_aw": 4.35,
    "q4_avg_gpa_american_fall_2026": 3.79,
    "q5_fall_2025_acceptance_pct": 47.92,
    "q6_avg_gpa_accepted_fall_2026": 3.76,
    "q7_jhu_masters_cs_count": 8,
    "q8_original_field_count": 28,
    "q9_llm_field_count": 0,
    "q9_minus_q8_diff": -28,
    "original_gpa_bucket": [("GPA < 3.8", 21100, 43.74), ("GPA >= 3.8", 8940, 39.29)],
    "original_degree_breakdown": [("PhD", 21243), ("Masters", 7640)],
}


class FakePullState:
    """A tiny, fully in-memory stand-in for the real subprocess-based Pull
    Data runner. Tests flip ``.running`` directly to simulate a busy pull
    -- no subprocess, no ``sleep()``."""

    def __init__(self, running: bool = False):
        self.running = running
        self.start_calls = 0

    def is_running(self) -> bool:
        return self.running

    def start(self) -> None:
        self.start_calls += 1
        self.running = True

    def status(self) -> dict:
        return {"state": "running" if self.running else "done", "message": "fake status"}


@pytest.fixture()
def fake_pull_state():
    return FakePullState()


@pytest.fixture()
def fake_results():
    return dict(FAKE_RESULTS)


@pytest.fixture()
def app(fake_pull_state, fake_results):
    """A Flask app wired entirely to fakes: no real database, subprocess,
    or network call. This is what every ``web``/``buttons``/``analysis``
    test uses."""
    application = create_app(
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        get_analysis_results_fn=lambda: dict(fake_results),
        start_pull_fn=fake_pull_state.start,
        is_pull_running_fn=fake_pull_state.is_running,
        get_pull_status_fn=fake_pull_state.status,
        secret_key="test-secret",
    )
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(app):
    return app.test_client()
