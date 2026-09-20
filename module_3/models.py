"""
models.py

SQLAlchemy 2.x model + Engine/Session configuration for the `applicants`
table. This maps to the SAME PostgreSQL table that load_data.py populates
via raw psycopg -- there is no second copy of the data for SQLAlchemy to use.

Connection settings come from the same environment variables as
load_data.py / query_data.py (see README.md / .env.example).
"""

from __future__ import annotations

import os
from datetime import date

from dotenv import load_dotenv
from sqlalchemy import Float, Integer, Text, Date, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    pass


class Applicant(Base):
    """Maps to the existing `applicants` table created by load_data.py."""

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


def _build_db_url() -> str:
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "gradcafe")
    auth = f"{user}:{password}" if password else user
    return f"postgresql+psycopg://{auth}@{host}:{port}/{name}"


# Engine + Session, configured once and imported wherever the ORM is needed
# (orm_queries.py and the Flask app both import `SessionLocal` from here,
# rather than each opening their own separate connection setup).
engine = create_engine(_build_db_url(), future=True)
SessionLocal = sessionmaker(bind=engine, future=True)
