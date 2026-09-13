"""
clean.py
--------

Takes the raw records produced by scrape.py (applicant_data.json) and
normalizes them into the structured, analysis-ready shape required by the
assignment: HTML remnants stripped, a consistent representation for missing
values, and per-field normalization -- without destructively overwriting
the original applicant-provided program/university text (that raw text is
kept alongside the cleaned fields for traceability/reproducibility, and is
exactly what module_2/llm_hosting/app.py consumes in the next step to add
`llm-generated-program` / `llm-generated-university`).

Functions
---------
clean_data(records)  -> list[dict]   : the main entry point
save_data(records, path)             : write a valid JSON array
load_data(path)      -> list[dict]   : read a JSON array (or [] if missing)

Run directly to clean applicant_data.json -> cleaned_applicant_data.json:

    python clean.py --in applicant_data.json --out cleaned_applicant_data.json
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("gradcafe_cleaner")

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Values scraped as literal placeholder text that really mean "no data".
_MISSING_TOKENS = {"", "n/a", "na", "none", "--", "-", "null", "unknown"}


# --------------------------------------------------------------------------
# Low-level text cleanup
# --------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Remove HTML tags and decode HTML entities (e.g. &amp; -> &)."""
    unescaped = html.unescape(text)
    no_tags = _TAG_RE.sub("", unescaped)
    return _WHITESPACE_RE.sub(" ", no_tags).strip()


def _normalize_missing(value: Any) -> Any:
    """Map any of the many ways "no data" shows up in the raw scrape to a
    single, consistent representation: None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _strip_html(value)
        return cleaned if cleaned.strip().lower() not in _MISSING_TOKENS else None
    return value


# --------------------------------------------------------------------------
# Field-specific normalization
# --------------------------------------------------------------------------

_GPA_RE = re.compile(r"(\d\.\d{1,2})")
_GRE_RE = re.compile(r"(\d{2,3}(?:\.\d)?)")


def _normalize_gpa(raw: str | None) -> str | None:
    if not raw:
        return None
    match = _GPA_RE.search(raw)
    if not match:
        return None
    value = float(match.group(1))
    # Grad Cafe is a 4.0-scale self-report site; values outside a sane
    # range are almost always a mis-scraped fragment, not a real GPA. We
    # flag rather than silently drop, since altering applicant-reported
    # data isn't allowed -- we just don't fabricate a confident value.
    if not (0.0 <= value <= 4.33):
        return raw.strip()
    return f"{value:.2f}"


def _normalize_gre(raw: str | None) -> str | None:
    if not raw:
        return None
    match = _GRE_RE.search(raw)
    return match.group(1) if match else raw.strip()


def _normalize_status_and_date(status: str | None) -> tuple[str | None, str | None]:
    """Split a raw status string like "Accepted on 25 Mar" into
    ("Accepted", "25 Mar"). Falls back gracefully for statuses without a
    trailing date (e.g. plain "Wait listed").
    """
    if not status:
        return None, None
    status = status.strip()
    if " on " in status:
        label, _, date_part = status.partition(" on ")
        return label.strip().title(), date_part.strip(" .,") or None
    return status.title(), None


def _normalize_term(term: str | None) -> str | None:
    if not term:
        return None
    term = term.strip()
    match = re.match(r"(Fall|Spring|Summer|Winter)\s*(\d{4})", term, re.IGNORECASE)
    if match:
        season, year = match.groups()
        return f"{season.capitalize()} {year}"
    return term


def _normalize_degree(degree: str | None) -> str | None:
    if not degree:
        return None
    degree = degree.strip()
    aliases = {
        "ms": "Masters",
        "msc": "Masters",
        "m.s.": "Masters",
        "master's": "Masters",
        "masters": "Masters",
        "phd": "PhD",
        "ph.d.": "PhD",
        "doctorate": "PhD",
    }
    return aliases.get(degree.lower(), degree)


def _normalize_nationality(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().title()
    if value not in ("International", "American"):
        return value
    return value


def _normalize_gre_aw(raw: str | None) -> str | None:
    """Extract the numeric Analytical Writing score from a badge like
    'GRE AW 4.00' (AW is scored 0.0-6.0 in half-point increments).
    """
    if not raw:
        return None
    match = re.search(r"(\d(?:\.\d{1,2})?)", raw)
    if not match:
        return None
    value = float(match.group(1))
    if not (0.0 <= value <= 6.0):
        return raw.strip()
    return f"{value:.2f}"


def _split_program_university(raw_program: str | None, fallback_university: str | None) -> tuple[str | None, str | None]:
    """Grad Cafe's current site already reports School and Program as
    separate fields (see scrape.py's `_extract_primary_fields`), so this
    is normally just a pass-through. It's kept as a single seam -- rather
    than inlined into clean_data() -- in case an older/alternate capture
    ever hands this a combined "Program, University" string again; in
    that fallback case only, a comma-delimited split is attempted.
    """
    if not raw_program:
        return None, fallback_university

    if fallback_university:
        # University already known from its own field -- nothing to split.
        return raw_program.strip(), fallback_university

    if "," in raw_program:
        program_part, _, university_part = raw_program.rpartition(",")
        return program_part.strip() or None, university_part.strip() or None

    return raw_program.strip(), fallback_university


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def clean_data(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean a list of raw scrape.py records into the final structured
    shape. Every required assignment field is present on every output
    record (as None when unavailable).
    """
    cleaned: list[dict[str, Any]] = []

    for raw in records:
        raw_program_text = raw.get("program")  # preserved verbatim, never overwritten
        program, university = _split_program_university(
            raw_program_text, raw.get("university")
        )
        status_label, decision_date = _normalize_status_and_date(raw.get("status"))

        cleaned.append(
            {
                # Cleaned / convenience fields
                "program": _normalize_missing(program),
                "university": _normalize_missing(university),
                "comments": _normalize_missing(raw.get("comments")),
                "date_added": _normalize_missing(raw.get("date_added")),
                "url": _normalize_missing(raw.get("url")),
                "status": _normalize_missing(status_label),
                "decision_date": _normalize_missing(decision_date or raw.get("decision_date")),
                "term": _normalize_term(_normalize_missing(raw.get("term"))),
                "US/International": _normalize_nationality(_normalize_missing(raw.get("US/International"))),
                "GRE": _normalize_gre(_normalize_missing(raw.get("GRE"))),
                "GRE V": _normalize_gre(_normalize_missing(raw.get("GRE V"))),
                "GRE AW": _normalize_gre_aw(_normalize_missing(raw.get("GRE AW"))),
                "Degree": _normalize_degree(_normalize_missing(raw.get("Degree"))),
                "GPA": _normalize_gpa(_normalize_missing(raw.get("GPA"))),
                # Traceability: the untouched, applicant-entered text.
                "raw_program_text": _normalize_missing(raw_program_text),
                "raw_row_text": _normalize_missing(raw.get("raw_row_text")),
            }
        )

    logger.info("Cleaned %d records.", len(cleaned))
    return cleaned


def save_data(records: list[dict[str, Any]], path: Path) -> None:
    path = Path(path)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d records to %s", len(records), path)


def load_data(path: Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="in_path", default="applicant_data.json")
    parser.add_argument("--out", dest="out_path", default="cleaned_applicant_data.json")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    raw_records = load_data(Path(args.in_path))
    if not raw_records:
        logger.warning("No records found in %s -- nothing to clean.", args.in_path)
    cleaned_records = clean_data(raw_records)
    save_data(cleaned_records, Path(args.out_path))


if __name__ == "__main__":
    main()
