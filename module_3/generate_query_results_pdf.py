"""
generate_query_results_pdf.py

One-off script that builds query_results.pdf (Part 4) from the verified
results and SQL text used in query_data.py. Not part of the required
deliverables list itself -- just the tool used to produce query_results.pdf.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, Table, TableStyle,
)

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Heading1"], spaceAfter=4)
h2 = ParagraphStyle("h2", parent=styles["Heading2"], spaceBefore=14, spaceAfter=4,
                     textColor=colors.HexColor("#1d4278"))
body = ParagraphStyle("body", parent=styles["Normal"], spaceAfter=4, leading=14)
result_style = ParagraphStyle("result", parent=styles["Normal"], spaceAfter=6,
                               fontName="Helvetica-Bold", textColor=colors.HexColor("#1c6b3a"))
code_style = ParagraphStyle(
    "code", parent=styles["Code"], fontSize=8.3, leading=10.5,
    backColor=colors.HexColor("#f4f5f8"), borderPadding=6,
)

QUESTIONS = [
    dict(
        number="Question 1",
        question="How many entries in the database are from applicants who applied for Fall 2026?",
        result="Fall 2026 applicant count: 29,637",
        sql="SELECT count(*) FROM applicants WHERE term ILIKE 'Fall 2026';",
        explanation="Counts every row whose term field matches 'Fall 2026', case-insensitively "
                    "(ILIKE) so capitalization differences in the scraped data don't cause misses.",
    ),
    dict(
        number="Question 2",
        question="Among entries that provide a nationality classification, what percentage are "
                 "international students?",
        result="Percent international: 46.36%",
        sql=("SELECT round(\n"
             "    100.0 * count(*) FILTER (WHERE lower(us_or_international) = 'international')\n"
             "    / NULLIF(count(*) FILTER (WHERE us_or_international IS NOT NULL\n"
             "                               AND btrim(us_or_international) <> ''), 0)\n"
             ", 2)\nFROM applicants;"),
        explanation="The denominator counts every entry with a non-blank nationality "
                    "classification (American, International, or Other); the numerator counts "
                    "only International. NULLIF guards against a divide-by-zero if no rows had "
                    "a usable classification.",
    ),
    dict(
        number="Question 3",
        question="What are the average GPA, GRE Quantitative, GRE Verbal, and GRE Analytical "
                 "Writing scores of applicants who provide each metric?",
        result="Average GPA: 3.77   |   Average GRE Quantitative: 165.83   |   "
               "Average GRE Verbal: 160.71   |   Average GRE Analytical Writing: 4.35",
        sql=("SELECT\n"
             "    round(avg(gpa)::numeric, 2) AS avg_gpa,\n"
             "    round(avg(gre)    FILTER (WHERE gre    BETWEEN 130 AND 170)::numeric, 2)"
             " AS avg_gre_quant,\n"
             "    round(avg(gre_v)  FILTER (WHERE gre_v  BETWEEN 130 AND 170)::numeric, 2)"
             " AS avg_gre_verbal,\n"
             "    round(avg(gre_aw) FILTER (WHERE gre_aw BETWEEN 0   AND 6)::numeric,   2)"
             " AS avg_gre_aw\nFROM applicants;"),
        explanation="Each average is computed independently over only the applicants who "
                    "provided that metric (SQL's avg() already ignores NULLs, so an applicant "
                    "missing GRE scores still contributes to the GPA average). The GRE "
                    "Quantitative and Verbal averages are restricted to the valid ETS 130-170 "
                    "scale: 1,416 of 2,373 raw 'GRE' values (60%) fell outside that range -- "
                    "almost certainly combined scores, percentile ranks, or typos rather than "
                    "genuine Quantitative scores. This is a real, disclosed data-quality "
                    "decision, discussed further in limitations.pdf.",
    ),
    dict(
        number="Question 4",
        question="What is the average GPA of American applicants who applied for Fall 2026?",
        result="Average GPA (American, Fall 2026): 3.79",
        sql=("SELECT round(avg(gpa)::numeric, 2)\nFROM applicants\n"
             "WHERE term ILIKE 'Fall 2026'\n"
             "  AND lower(us_or_international) = 'american'\n"
             "  AND gpa IS NOT NULL;"),
        explanation="Filters to Fall 2026, American applicants, and requires a non-null GPA "
                    "before averaging, satisfying all three stated conditions simultaneously.",
    ),
    dict(
        number="Question 5",
        question="What percentage of Fall 2025 entries are acceptances?",
        result="Fall 2025 acceptance percentage: 47.92%",
        sql=("SELECT round(\n"
             "    100.0 * count(*) FILTER (WHERE lower(status) = 'accepted')\n"
             "    / NULLIF(count(*), 0)\n"
             ", 2)\nFROM applicants\nWHERE term ILIKE 'Fall 2025';"),
        explanation="The denominator is every Fall 2025 entry regardless of status; the "
                    "numerator is the subset whose cleaned status is 'Accepted'.",
    ),
    dict(
        number="Question 6",
        question="What is the average GPA of accepted applicants who applied for Fall 2026?",
        result="Average GPA (Accepted, Fall 2026): 3.76",
        sql=("SELECT round(avg(gpa)::numeric, 2)\nFROM applicants\n"
             "WHERE term ILIKE 'Fall 2026'\n"
             "  AND lower(status) = 'accepted'\n"
             "  AND gpa IS NOT NULL;"),
        explanation="Same pattern as Question 4, but filtered on acceptance status instead of "
                    "nationality.",
    ),
    dict(
        number="Question 7",
        question="How many entries are from applicants who applied to Johns Hopkins University "
                 "for a master's degree in Computer Science?",
        result="JHU Masters Computer Science count: 8",
        sql=("SELECT count(*)\nFROM applicants\n"
             "WHERE (program ILIKE '%hopkins%' OR program ILIKE '%jhu%')\n"
             "  AND program ILIKE '%computer science%'\n"
             "  AND lower(degree) = 'masters';"),
        explanation="program stores the combined 'Department/Program, University' string (the "
                    "same original downloaded field convention used throughout Module 2). "
                    "Matching '%hopkins%' catches 'Johns Hopkins University', 'JHU', and the "
                    "'John Hopkins' typo variant seen in the raw data; degree is normalized to "
                    "the literal value 'Masters' by clean.py.",
    ),
    dict(
        number="Question 8",
        question="How many Fall 2026 entries are acceptances from applicants applying for a PhD "
                 "in Computer Science at Georgetown, MIT, Stanford, or Carnegie Mellon?",
        result="Original-field count: 28",
        sql=("SELECT count(*)\nFROM applicants\n"
             "WHERE term ILIKE 'Fall 2026'\n"
             "  AND lower(status) = 'accepted'\n"
             "  AND lower(degree) = 'phd'\n"
             "  AND program ILIKE '%computer science%'\n"
             "  AND (\n"
             "        program ILIKE '%georgetown%'\n"
             "     OR program ILIKE '%massachusetts institute of technology%'\n"
             "     OR program ~* '\\ymit\\y'\n"
             "     OR program ILIKE '%stanford%'\n"
             "     OR program ILIKE '%carnegie mellon%'\n"
             "  );"),
        explanation="All five conditions (term, status, degree, subject, and one of the four "
                    "universities) apply simultaneously via AND. MIT is matched with a "
                    "word-boundary regex (\\y...\\y) rather than a plain substring, since a "
                    "plain '%mit%' match would also catch unrelated programs like 'Committee on "
                    "Evolutionary Biology' -- confirmed by inspecting the actual data before "
                    "finalizing this query.",
    ),
    dict(
        number="Question 9",
        question="Repeat Question 8 using llm_generated_program / llm_generated_university "
                 "instead of the original downloaded fields.",
        result="Original-field count: 28   |   LLM-field count: 0   |   Difference: -28",
        sql=("SELECT count(*)\nFROM applicants\n"
             "WHERE term ILIKE 'Fall 2026'\n"
             "  AND lower(status) = 'accepted'\n"
             "  AND lower(degree) = 'phd'\n"
             "  AND llm_generated_program ILIKE '%computer science%'\n"
             "  AND (\n"
             "        llm_generated_university ILIKE '%georgetown%'\n"
             "     OR llm_generated_university ILIKE '%massachusetts institute of technology%'\n"
             "     OR llm_generated_university ~* '\\ymit\\y'\n"
             "     OR llm_generated_university ILIKE '%stanford%'\n"
             "     OR llm_generated_university ILIKE '%carnegie mellon%'\n"
             "  );"),
        explanation="term/degree/status still come from the original fields as instructed; only "
                    "the subject/university matching switches to the LLM-generated fields. The "
                    "LLM-field count is lower for a specific, documented reason: the local LLM "
                    "standardization pass (Module 2) only finished processing 60 of 30,060 "
                    "cleaned records before the deadline, so llm_generated_program/university "
                    "are NULL for the other 29,940 rows. This is a coverage gap in how much data "
                    "was standardized, not evidence that the LLM's matching disagrees with the "
                    "original fields -- with the full run complete, we would expect the two "
                    "counts to converge closely, since the LLM was only asked to standardize "
                    "spelling/naming, not to reinterpret program or university identity.",
    ),
    dict(
        number="Original Question 1",
        question="Does a higher undergraduate GPA correlate with a higher acceptance rate?",
        result="GPA < 3.8: 6,927 entries, 43.74% accepted   |   GPA >= 3.8: 11,136 entries, "
               "39.29% accepted",
        sql=("SELECT\n"
             "    CASE WHEN gpa >= 3.8 THEN 'GPA >= 3.8' ELSE 'GPA < 3.8' END AS gpa_bucket,\n"
             "    count(*) AS total,\n"
             "    round(100.0 * count(*) FILTER (WHERE lower(status) = 'accepted')"
             " / count(*), 2) AS pct_accepted\n"
             "FROM applicants\n"
             "WHERE gpa IS NOT NULL AND status IS NOT NULL\n"
             "GROUP BY 1\nORDER BY 1;"),
        explanation="Buckets every applicant with both a GPA and a decision into two groups and "
                    "computes each group's acceptance rate. Counterintuitively, the higher-GPA "
                    "group was accepted slightly less often -- most likely because applicants "
                    "with stronger GPAs disproportionately apply to more selective (and more "
                    "competitive) PhD programs, not because a higher GPA hurts admission odds. "
                    "This finding is discussed further in limitations.pdf as an example of why "
                    "raw correlations in self-submitted data can be misleading without "
                    "controlling for program selectivity.",
    ),
    dict(
        number="Original Question 2",
        question="How many entries are there for each degree type, and which is the most common?",
        result="PhD: 21,243   |   Masters: 7,640   |   MFA: 621   |   PsyD: 301   |   "
               "Other: 211   |   JD: 18   |   EdD: 17   |   MBA: 9",
        sql=("SELECT degree, count(*) AS total\nFROM applicants\n"
             "WHERE degree IS NOT NULL\nGROUP BY degree\nORDER BY total DESC;"),
        explanation="Groups all entries by their normalized degree type and counts each group, "
                    "ordered from most to least common. PhD applications dominate the dataset "
                    "(over 70% of all entries), which is itself a useful representativeness "
                    "signal discussed in limitations.pdf.",
    ),
]


def build_pdf(output_path: str = "query_results.pdf"):
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    )
    story = []

    story.append(Paragraph("Module 3 &ndash; SQL Query Analysis Results", styles["Title"]))
    story.append(Paragraph(
        "Laila Afmeged &mdash; JHED: lafmege1 &mdash; Grad Cafe Admissions Data "
        "(30,060 records)", body))
    story.append(Spacer(1, 10))

    for q in QUESTIONS:
        story.append(Paragraph(q["number"], h2))
        story.append(Paragraph(f"<b>Question:</b> {q['question']}", body))
        story.append(Paragraph(f"Result: {q['result']}", result_style))
        story.append(Paragraph("<b>SQL query:</b>", body))
        story.append(Preformatted(q["sql"], code_style))
        story.append(Spacer(1, 3))
        story.append(Paragraph(f"<b>Explanation:</b> {q['explanation']}", body))

    doc.build(story)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build_pdf()
