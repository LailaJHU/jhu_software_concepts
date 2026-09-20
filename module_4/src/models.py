"""
models.py

SQLAlchemy 2.x model plus Engine/Session helpers for the ``applicants``
table. This maps to the same PostgreSQL table that :mod:`load_data`
populates via raw ``psycopg`` -- there is no second copy of the data for
SQLAlchemy to use.

Unlike Module 3, connection configuration is centered on a single
``DATABASE_URL`` environment variable (the standard 12-factor convention,
and what the test suite / CI overrides per-environment). The old
``DB_HOST`` / ``DB_USER`` / ... variables are still honored as a fallback
so a developer's existing ``.env`` keeps working.
"""

from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import Date, Float, Integer, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in this project."""


class Applicant(Base):
    """Maps to the existing ``applicants`` table created by :mod:`load_data`."""

    __tablename__ = "applicants"

    p_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    date_added: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(Text, unique=True)
    status: Mapped[str | None] = mapped_column(Text)
    term: Mapped[str | None] = mapped_column(Text)
    us_or_international: Mapped[str | None] = mapped_column(Text)
    gpa: Mapped[float | None] = mapped_column(Float)
    gre: Mapped[float | None] = mapped_column(Float)
    gre_v: Mapped[float | None] = mapped_column(Float)
    gre_aw: Mapped[float | None] = mapped_column(Float)
    degree: Mapped[str | None] = mapped_column(Text)
    llm_generated_program: Mapped[str | None] = mapped_column(Text)
    llm_generated_university: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Applicant p_id={self.p_id} program={self.program!r} term={self.term!r}>"


def build_database_url() -> str:
    """Returns the connection string this project should use.

    ``DATABASE_URL`` (if set) always wins -- this is what CI and the test
    suite set. Otherwise the individual ``DB_*`` variables are assembled
    into the same URL shape, for backward compatibility with the Module 3
    ``.env`` layout.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "gradcafe")
    auth = f"{user}:{password}" if password else user
    return f"postgresql+psycopg://{auth}@{host}:{port}/{name}"


def make_engine(database_url: str | None = None) -> Engine:
    """Builds a fresh SQLAlchemy Engine for ``database_url`` (or the
    environment's default). Building an Engine does not open a connection
    until it is actually used, so this is safe to call even when no
    database is reachable yet (e.g. during test collection)."""
    return create_engine(database_url or build_database_url(), future=True)


def make_session_factory(engine: Engine | None = None, database_url: str | None = None):
    """Builds a ``sessionmaker`` bound to ``engine`` (or a fresh engine for
    ``database_url``). This is what :func:`app.create_app` calls, so every
    Flask app instance can be pointed at its own database (production vs.
    a throwaway test database) without any module-level global state."""
    return sessionmaker(bind=engine or make_engine(database_url), future=True)


# Module-level engine/session, built lazily against the environment's
# default DATABASE_URL. Kept for backward compatibility with orm_queries.py
# / models.py being run as standalone scripts (``python orm_queries.py``);
# the Flask app itself always uses make_session_factory() instead, so this
# global is never touched by the test suite.
engine = make_engine()
SessionLocal = make_session_factory(engine)
