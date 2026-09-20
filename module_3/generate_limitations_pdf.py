"""
generate_limitations_pdf.py

Builds limitations.pdf (Part 11): two substantive paragraphs on the
limitations of analyzing anonymous, self-submitted data like Grad Cafe,
connected to concrete results from this project's own analysis.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

styles = getSampleStyleSheet()
title_style = styles["Title"]
byline_style = ParagraphStyle("byline", parent=styles["Normal"], spaceAfter=16)
body_style = ParagraphStyle("body", parent=styles["Normal"], fontSize=11.5,
                             leading=17, spaceAfter=14, alignment=4)  # 4 = justify

PARAGRAPH_1 = """
Grad Cafe's dataset is built entirely from applicants who chose, unprompted, to visit the
site and type in their own results, which means every statistic computed from it describes
the population of people who self-select into reporting &mdash; not the population of everyone
who applied. That gap shows up directly in our own numbers: PhD entries outnumber Masters
entries by roughly three to one in this dataset (21,243 vs. 7,640), a ratio far more lopsided
than is plausible for actual national graduate admissions, where Masters programs enroll far
more students overall. The likeliest explanation isn't that fewer people pursue Masters
degrees; it's that Grad Cafe's userbase, culture, and word-of-mouth reach skew toward
research-track PhD applicants who are more invested in tracking admissions cycles closely and
comparing notes with peers. Missing values compound this problem rather than randomly
diluting it: GPA is present for only about 60% of entries and GRE scores for well under 10%,
and there is no way to know whether the applicants who omitted a GPA did so because it was
unremarkable, because they were embarrassed by it, or simply because the site's submission
form doesn't require it. Any average computed only over the applicants who did report a
value &mdash; which is what every average in this project necessarily is &mdash; may be
systematically shifted by whichever kind of person is more likely to fill in that field.
"""

PARAGRAPH_2 = """
Beyond who chooses to submit at all, self-reported values are also not always reliable once
entered, and our own data surfaced a concrete example of this: 1,416 of 2,373 raw GRE
Quantitative entries (roughly 60%) fell outside the valid 130-170 ETS scale, with values as
high as 999 and clusters in the 300-340 range that look like combined Quantitative-plus-Verbal
scores rather than a Quantitative score alone. We chose to exclude those out-of-scale values
from the reported average rather than let them distort it, but that decision itself illustrates
the limitation: we cannot know, from the data alone, whether a given entry is a genuine typo, a
deliberate combined score, or something else, and different plausible cleaning choices would
produce different published averages. A similar reliability question applies to outcomes
themselves &mdash; our analysis found that applicants with a GPA at or above 3.8 were accepted
at a very slightly lower rate (39.29%) than applicants below 3.8 (43.74%), a result that is
almost certainly confounded by which programs each group applied to (stronger applicants likely
target more selective PhD programs) rather than evidence that a higher GPA hurts admission
odds. It's also worth asking whether applicants with unusually good or unusually bad outcomes
are more likely to post in the first place, or to post with more detail and emotional
investment in the comments field, further skewing any statistic that treats every entry as an
equally representative data point. Taken together, this means our database can tell us, with
reasonable confidence, what Grad Cafe's self-selected posters reported and when &mdash; but it
cannot, on its own, support claims about the true admissions rates, average qualifications, or
experiences of the broader applicant population that never appears in this dataset at all.
"""


def build_pdf(output_path: str = "limitations.pdf"):
    doc = SimpleDocTemplate(
        output_path, pagesize=letter,
        leftMargin=1 * inch, rightMargin=1 * inch,
        topMargin=1 * inch, bottomMargin=1 * inch,
    )
    story = [
        Paragraph("Limitations of Self-Submitted Admissions Data", title_style),
        Paragraph("Laila Afmeged &mdash; JHED: lafmege1 &mdash; Module 3 Written Reflection",
                   byline_style),
        Spacer(1, 6),
        Paragraph(PARAGRAPH_1.replace("\n", " ").strip(), body_style),
        Paragraph(PARAGRAPH_2.replace("\n", " ").strip(), body_style),
    ]
    doc.build(story)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build_pdf()
