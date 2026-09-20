"""
query_data.py

Answers all 11 analysis questions (Questions 1-9 from the assignment, plus
two original questions) using raw SQL executed through psycopg against the
`applicants` table. All numeric formatting follows the assignment's rules:
counts as whole numbers, percentages/averages to 2 decimal places with '%'
where applicable.

Run directly for console output:
    python query_data.py
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(
        dbname=os.environ.get("DB_NAME", "gradcafe"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", ""),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
    )


# ---------------------------------------------------------------------------
# Each question is (label, sql, formatter). formatter turns the raw row into
# the printed string, applying the required decimal/percent formatting.
# ---------------------------------------------------------------------------

Q1_SQL = """
SELECT count(*) FROM applicants WHERE term ILIKE 'Fall 2026';
"""

Q2_SQL = """
SELECT round(
    100.0 * count(*) FILTER (WHERE lower(us_or_international) = 'international')
    / NULLIF(count(*) FILTER (WHERE us_or_international IS NOT NULL
                               AND btrim(us_or_international) <> ''), 0)
, 2)
FROM applicants;
"""

# NOTE on Q3: the raw 'GRE' (Quantitative) and 'GRE V' (Verbal) fields contain
# a meaningful number of values outside the valid ETS 130-170 scale (some
# applicants appear to have entered a combined score, a percentile rank, or
# made a typo -- a real example of self-reported data unreliability, see
# limitations.pdf). Those averages are therefore computed only over values on
# the valid scale; GPA (0-4.33) and GRE AW (0-6) did not show this problem.
Q3_SQL = """
SELECT
    round(avg(gpa)::numeric, 2) AS avg_gpa,
    round(avg(gre)    FILTER (WHERE gre    BETWEEN 130 AND 170)::numeric, 2) AS avg_gre_quant,
    round(avg(gre_v)  FILTER (WHERE gre_v  BETWEEN 130 AND 170)::numeric, 2) AS avg_gre_verbal,
    round(avg(gre_aw) FILTER (WHERE gre_aw BETWEEN 0   AND 6)::numeric,   2) AS avg_gre_aw
FROM applicants;
"""

Q4_SQL = """
SELECT round(avg(gpa)::numeric, 2)
FROM applicants
WHERE term ILIKE 'Fall 2026'
  AND lower(us_or_international) = 'american'
  AND gpa IS NOT NULL;
"""

Q5_SQL = """
SELECT round(
    100.0 * count(*) FILTER (WHERE lower(status) = 'accepted')
    / NULLIF(count(*), 0)
, 2)
FROM applicants
WHERE term ILIKE 'Fall 2025';
"""

Q6_SQL = """
SELECT round(avg(gpa)::numeric, 2)
FROM applicants
WHERE term ILIKE 'Fall 2026'
  AND lower(status) = 'accepted'
  AND gpa IS NOT NULL;
"""

# Q7-Q9 match against `program`, which stores "Department/Program, University"
# (the same combined convention the instructor's LLM tool expects). MIT is
# matched with a word-boundary regex so it doesn't match "Committee",
# "commitment", etc.
Q7_SQL = """
SELECT count(*)
FROM applicants
WHERE (program ILIKE '%hopkins%' OR program ILIKE '%jhu%')
  AND program ILIKE '%computer science%'
  AND lower(degree) = 'masters';
"""

Q8_SQL = """
SELECT count(*)
FROM applicants
WHERE term ILIKE 'Fall 2026'
  AND lower(status) = 'accepted'
  AND lower(degree) = 'phd'
  AND program ILIKE '%computer science%'
  AND (
        program ILIKE '%georgetown%'
     OR program ILIKE '%massachusetts institute of technology%'
     OR program ~* '\\ymit\\y'
     OR program ILIKE '%stanford%'
     OR program ILIKE '%carnegie mellon%'
  );
"""

Q9_SQL = """
SELECT count(*)
FROM applicants
WHERE term ILIKE 'Fall 2026'
  AND lower(status) = 'accepted'
  AND lower(degree) = 'phd'
  AND llm_generated_program ILIKE '%computer science%'
  AND (
        llm_generated_university ILIKE '%georgetown%'
     OR llm_generated_university ILIKE '%massachusetts institute of technology%'
     OR llm_generated_university ~* '\\ymit\\y'
     OR llm_generated_university ILIKE '%stanford%'
     OR llm_generated_university ILIKE '%carnegie mellon%'
  );
"""

# --- Original Question 1: does a higher GPA correlate with a higher
# acceptance rate? ---------------------------------------------------------
ORIG_A_SQL = """
SELECT
    CASE WHEN gpa >= 3.8 THEN 'GPA >= 3.8' ELSE 'GPA < 3.8' END AS gpa_bucket,
    count(*) AS total,
    round(100.0 * count(*) FILTER (WHERE lower(status) = 'accepted') / count(*), 2) AS pct_accepted
FROM applicants
WHERE gpa IS NOT NULL AND status IS NOT NULL
GROUP BY 1
ORDER BY 1;
"""

# --- Original Question 2: how many entries are there per degree type? -----
ORIG_B_SQL = """
SELECT degree, count(*) AS total
FROM applicants
WHERE degree IS NOT NULL
GROUP BY degree
ORDER BY total DESC;
"""


def run(cur, sql: str):
    cur.execute(sql)
    return cur.fetchall()


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            print("=" * 70)
            print("Question 1: Fall 2026 applicant count")
            (count1,) = run(cur, Q1_SQL)[0]
            print(f"Fall 2026 applicant count: {count1:,}")

            print("\nQuestion 2: Percent international")
            (pct_intl,) = run(cur, Q2_SQL)[0]
            print(f"Percent international: {pct_intl:.2f}%")

            print("\nQuestion 3: Average GPA / GRE Quant / GRE Verbal / GRE AW")
            avg_gpa, avg_q, avg_v, avg_aw = run(cur, Q3_SQL)[0]
            print(f"Average GPA: {avg_gpa:.2f}")
            print(f"Average GRE Quantitative: {avg_q:.2f}")
            print(f"Average GRE Verbal: {avg_v:.2f}")
            print(f"Average GRE Analytical Writing: {avg_aw:.2f}")

            print("\nQuestion 4: Average GPA, American applicants, Fall 2026")
            (avg_gpa_amer,) = run(cur, Q4_SQL)[0]
            print(f"Average GPA (American, Fall 2026): {avg_gpa_amer:.2f}")

            print("\nQuestion 5: Fall 2025 acceptance percentage")
            (pct_accept_25,) = run(cur, Q5_SQL)[0]
            print(f"Fall 2025 acceptance percentage: {pct_accept_25:.2f}%")

            print("\nQuestion 6: Average GPA, accepted applicants, Fall 2026")
            (avg_gpa_accept,) = run(cur, Q6_SQL)[0]
            print(f"Average GPA (Accepted, Fall 2026): {avg_gpa_accept:.2f}")

            print("\nQuestion 7: JHU Masters Computer Science count")
            (count7,) = run(cur, Q7_SQL)[0]
            print(f"JHU Masters Computer Science count: {count7}")

            print("\nQuestion 8: Fall 2026 PhD CS acceptances (original fields)")
            (count8,) = run(cur, Q8_SQL)[0]
            print(f"Original-field count: {count8}")

            print("\nQuestion 9: Same as Question 8, using LLM-generated fields")
            (count9,) = run(cur, Q9_SQL)[0]
            print(f"LLM-field count: {count9}")
            diff = count9 - count8
            sign = "+" if diff >= 0 else ""
            print(f"Difference: {sign}{diff}")

            print("\nOriginal Question 1: Does GPA >= 3.8 correlate with a higher "
                  "acceptance rate than GPA < 3.8?")
            for bucket, total, pct in run(cur, ORIG_A_SQL):
                print(f"  {bucket}: {total:,} entries, {pct:.2f}% accepted")

            print("\nOriginal Question 2: How many entries are there per degree type?")
            for degree, total in run(cur, ORIG_B_SQL):
                print(f"  {degree}: {total:,}")

            print("=" * 70)


if __name__ == "__main__":
    main()
