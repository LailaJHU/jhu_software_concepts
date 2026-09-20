"""
orm_queries.py

Repeats Questions 1, 4, 5, 8, 9, and one original question (degree-type
breakdown) using SQLAlchemy 2.x -- select(), where(), func, and_(), or_(),
and Session -- with NO raw SQL / text() / psycopg cursors, per the
assignment's requirement that this section not bypass the ORM.

Where a question is equivalent to its raw-SQL counterpart in query_data.py,
the results should match exactly, since both read the same `applicants`
table.

Run directly for console output:
    python orm_queries.py
"""

from __future__ import annotations

from sqlalchemy import and_, case, func, or_, select

from models import Applicant, SessionLocal


def q1_fall_2026_count(session) -> int:
    stmt = select(func.count()).select_from(Applicant).where(
        Applicant.term.ilike("Fall 2026")
    )
    return session.execute(stmt).scalar_one()


def q4_avg_gpa_american_fall_2026(session) -> float | None:
    stmt = select(func.avg(Applicant.gpa)).where(
        Applicant.term.ilike("Fall 2026"),
        func.lower(Applicant.us_or_international) == "american",
        Applicant.gpa.is_not(None),
    )
    result = session.execute(stmt).scalar_one()
    return round(float(result), 2) if result is not None else None


def q5_fall_2025_acceptance_pct(session) -> float | None:
    total = session.execute(
        select(func.count()).select_from(Applicant).where(Applicant.term.ilike("Fall 2025"))
    ).scalar_one()
    if not total:
        return None
    accepted = session.execute(
        select(func.count()).select_from(Applicant).where(
            Applicant.term.ilike("Fall 2025"),
            func.lower(Applicant.status) == "accepted",
        )
    ).scalar_one()
    return round(100.0 * accepted / total, 2)


def _target_school(field) -> "ColumnElement[bool]":  # noqa: F821 - typing convenience only
    """Shared OR-clause for the 4 target universities, reused by Q8 and Q9
    against whichever column (original vs. LLM-generated) is passed in.
    MIT is matched with a word-boundary regex so it doesn't match
    "Committee", "commitment", etc."""
    return or_(
        field.ilike("%georgetown%"),
        field.ilike("%massachusetts institute of technology%"),
        field.op("~*")(r"\ymit\y"),
        field.ilike("%stanford%"),
        field.ilike("%carnegie mellon%"),
    )


def q8_fall_2026_phd_cs_acceptances_original_fields(session) -> int:
    stmt = select(func.count()).select_from(Applicant).where(
        and_(
            Applicant.term.ilike("Fall 2026"),
            func.lower(Applicant.status) == "accepted",
            func.lower(Applicant.degree) == "phd",
            Applicant.program.ilike("%computer science%"),
            _target_school(Applicant.program),
        )
    )
    return session.execute(stmt).scalar_one()


def q9_fall_2026_phd_cs_acceptances_llm_fields(session) -> int:
    stmt = select(func.count()).select_from(Applicant).where(
        and_(
            Applicant.term.ilike("Fall 2026"),
            func.lower(Applicant.status) == "accepted",
            func.lower(Applicant.degree) == "phd",
            Applicant.llm_generated_program.ilike("%computer science%"),
            _target_school(Applicant.llm_generated_university),
        )
    )
    return session.execute(stmt).scalar_one()


def original_degree_breakdown(session) -> list[tuple[str, int]]:
    """Original Question 2: how many entries are there per degree type?"""
    stmt = (
        select(Applicant.degree, func.count().label("total"))
        .where(Applicant.degree.is_not(None))
        .group_by(Applicant.degree)
        .order_by(func.count().desc())
    )
    return list(session.execute(stmt).all())


# ---------------------------------------------------------------------------
# The functions below are not part of Part 6's required repeat set (Q1, 4, 5,
# 8, 9, one original), but are included so the Flask webpage (Part 8) can
# display the FULL analysis -- all 9 required questions plus both original
# questions -- using SQLAlchemy exclusively, as required.
# ---------------------------------------------------------------------------

def q2_percent_international(session) -> float | None:
    numerator = session.execute(
        select(func.count()).select_from(Applicant).where(
            func.lower(Applicant.us_or_international) == "international"
        )
    ).scalar_one()
    denominator = session.execute(
        select(func.count()).select_from(Applicant).where(
            Applicant.us_or_international.is_not(None),
            func.length(func.btrim(Applicant.us_or_international)) > 0,
        )
    ).scalar_one()
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 2)


def q3_averages(session) -> dict:
    """Average GPA / GRE Quant / GRE Verbal / GRE AW. GRE Quant and Verbal
    are restricted to the valid 130-170 ETS scale, and AW to 0-6, matching
    the same documented data-quality filter used in query_data.py."""
    avg_gpa, avg_q, avg_v, avg_aw = session.execute(
        select(
            func.avg(Applicant.gpa),
            func.avg(Applicant.gre).filter(Applicant.gre.between(130, 170)),
            func.avg(Applicant.gre_v).filter(Applicant.gre_v.between(130, 170)),
            func.avg(Applicant.gre_aw).filter(Applicant.gre_aw.between(0, 6)),
        )
    ).one()
    return {
        "avg_gpa": round(float(avg_gpa), 2) if avg_gpa is not None else None,
        "avg_gre_quant": round(float(avg_q), 2) if avg_q is not None else None,
        "avg_gre_verbal": round(float(avg_v), 2) if avg_v is not None else None,
        "avg_gre_aw": round(float(avg_aw), 2) if avg_aw is not None else None,
    }


def q6_avg_gpa_accepted_fall_2026(session) -> float | None:
    result = session.execute(
        select(func.avg(Applicant.gpa)).where(
            Applicant.term.ilike("Fall 2026"),
            func.lower(Applicant.status) == "accepted",
            Applicant.gpa.is_not(None),
        )
    ).scalar_one()
    return round(float(result), 2) if result is not None else None


def q7_jhu_masters_cs_count(session) -> int:
    stmt = select(func.count()).select_from(Applicant).where(
        or_(Applicant.program.ilike("%hopkins%"), Applicant.program.ilike("%jhu%")),
        Applicant.program.ilike("%computer science%"),
        func.lower(Applicant.degree) == "masters",
    )
    return session.execute(stmt).scalar_one()


def original_gpa_bucket_acceptance(session) -> list[tuple[str, int, float]]:
    """Original Question 1: does GPA >= 3.8 correlate with a higher
    acceptance rate than GPA < 3.8?"""
    bucket = case(
        (Applicant.gpa >= 3.8, "GPA >= 3.8"),
        else_="GPA < 3.8",
    ).label("gpa_bucket")
    stmt = (
        select(
            bucket,
            func.count().label("total"),
            100.0 * func.count().filter(func.lower(Applicant.status) == "accepted") / func.count(),
        )
        .where(Applicant.gpa.is_not(None), Applicant.status.is_not(None))
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = session.execute(stmt).all()
    return [(b, t, round(float(p), 2)) for b, t, p in rows]


def main():
    with SessionLocal() as session:
        print("=" * 70)
        print("Question 1 (ORM): Fall 2026 applicant count")
        print(f"Fall 2026 applicant count: {q1_fall_2026_count(session):,}")

        print("\nQuestion 4 (ORM): Average GPA, American applicants, Fall 2026")
        avg_gpa = q4_avg_gpa_american_fall_2026(session)
        print(f"Average GPA (American, Fall 2026): {avg_gpa:.2f}")

        print("\nQuestion 5 (ORM): Fall 2025 acceptance percentage")
        pct = q5_fall_2025_acceptance_pct(session)
        print(f"Fall 2025 acceptance percentage: {pct:.2f}%")

        print("\nQuestion 8 (ORM): Fall 2026 PhD CS acceptances (original fields)")
        count8 = q8_fall_2026_phd_cs_acceptances_original_fields(session)
        print(f"Original-field count: {count8}")

        print("\nQuestion 9 (ORM): Same as Question 8, using LLM-generated fields")
        count9 = q9_fall_2026_phd_cs_acceptances_llm_fields(session)
        print(f"LLM-field count: {count9}")
        diff = count9 - count8
        sign = "+" if diff >= 0 else ""
        print(f"Difference: {sign}{diff}")

        print("\nOriginal Question 2 (ORM): entries per degree type")
        for degree, total in original_degree_breakdown(session):
            print(f"  {degree}: {total:,}")

        print("=" * 70)


if __name__ == "__main__":
    main()
