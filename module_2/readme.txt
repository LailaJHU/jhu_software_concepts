# Module 2 — Grad Cafe Admissions Data Scraper

Name: Laila Afmeged — JHED: lafmege1
Module: Module 2 — "Web Scraping: Grad Cafe Applicant Data" — Due: 09/13/2026

---

## Approach

### robots.txt check

`https://www.thegradcafe.com/robots.txt` was fetched and reviewed before
writing any code (raw text saved as `robots_txt_evidence.txt`; screenshot
as `screenshot.jpg`). It confirms browser-like traffic is allowed on
every path that is scraped, including `/survey/` and the individual
`/result/<id>` pages. No `Crawl-delay` is specified, but the scraper
still throttles itself (see Politeness below).

Compliance is enforced in code, not just checked once by hand:
`check_robots_txt()` in `scrape.py` loads the live robots.txt via
`urllib.robotparser.RobotFileParser` at the start of every run and asks
it whether the target path is allowed for the scraper's user agent. If
the answer is ever "no" — because the file changed since the last
check — the run aborts before fetching a single page rather than
proceeding anyway.

### Fetch strategy

Chrome is launched by hand with remote debugging enabled
(`--remote-debugging-port=9222`), and the target page is loaded and the
session established manually, once. `scrape.py` then attaches to that
already-open tab over the Chrome DevTools protocol (Selenium's
`debugger_address` option) and drives navigation from there — for each
page it opens a tab, waits for the page to finish rendering
(`WebDriverWait`), reads `driver.page_source`, and closes the tab. URLs
are built and validated with `urllib.parse`.

### Parsing

`_parse_listing_page()` uses BeautifulSoup against the results table.
Each applicant entry spans 2-3 sibling `<tr>`s: a primary row (school,
program, degree, decision badge, permalink), a badge row (term,
nationality, GPA/GRE/GRE V/GRE AW), and an optional comment row.
Ad-placement rows are detected and skipped by `_is_ad_row()`. Raw row
text is kept in `raw_row_text`; degree is read from its own `<span>`
rather than parsed out of the program name.

### Pagination & resumability

The site paginates via an opaque base64 keyset cursor (`?cursor=...`),
not `?page=N` — confirmed by decoding a real "Next" link.
`_extract_next_url()` reads that link directly from each page rather than
reconstructing the cursor. `applicant_data.json` stores the growing
result array; `.scrape_checkpoint.json` tracks the next cursor URL, pages
completed, and seen result URLs, written after every page. Re-running the
same command resumes from the last saved cursor instead of restarting.

### Politeness

A delay (`--delay`, default 2.5s + jitter) runs between page fetches.
`_looks_blocked()` checks every page for challenge/block-page
fingerprints; if one is detected, the scraper stops immediately rather
than retrying or changing identity.

### Cleaning (`clean.py`)

`clean_data()` strips stray HTML, maps every missing-value spelling
(`""`, `"N/A"`, `"--"`, etc.) to a single `None`, splits
`"Program, University"` into separate fields (keeping the original in
`raw_program_text`), splits `"Accepted on 25 Mar"` into `status` +
`decision_date`, normalizes term/degree naming and GPA/GRE formatting,
and leaves out-of-range GPA values as-is rather than guessing a
correction.

### LLM standardization (`llm_hosting/`)

The instructor-provided `app.py` (unmodified) runs a local TinyLlama
model to standardize program/university names. It expects a single
combined `"Program, University"` string, but our data already has them
as separate fields — feeding it directly would mark every university
"Unknown". `run_standardize.py` reconstructs the combined string per row
just for the `_call_llm()` call, then attaches the two new fields
(`llm-generated-program`, `llm-generated-university`) back onto the
original row without touching `program`/`university`/`raw_program_text`.
It also parallelizes across worker processes (`--workers`, default up to
4), since each worker loads its own model copy — a single loaded model
isn't safe to share across threads.

```
cd llm_hosting
python run_standardize.py --in ../cleaned_applicant_data.json --out ../llm_extend_applicant_data.json --workers 4
```

No changes were made to any file inside `llm_hosting/` as provided
(`app.py`, `canon_programs.txt`, `canon_universities.txt`, its
`requirements.txt`) — all used exactly as downloaded from Canvas.
`run_standardize.py` is the only addition, and it sits alongside those
files rather than editing them.

---

## Environment / how to reproduce

```
python3 -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Python 3.10+ required (uses `from __future__ import annotations` and PEP 604
`X | None` unions).

To scrape:

1. Launch Chrome by hand with remote debugging enabled (see Fetch
   strategy above), and load `https://www.thegradcafe.com/survey/` once
   to establish the session.
2. `python scrape.py --max-pages 1500 --delay 2.5`
3. `python clean.py --in applicant_data.json --out cleaned_applicant_data.json`
4. Run the LLM standardization pass (see LLM standardization above).

If the run is interrupted at any point, re-issuing the same `scrape.py`
command resumes automatically from the checkpointed cursor rather than
starting over from page 1.

---

## Known Bugs

- Selector fragility: parsing is tied to the current markup by CSS
  class/position. If Grad Cafe redesigns the page, fix by re-capturing a
  live HTML sample and updating `_is_ad_row`, `_extract_primary_fields`,
  and `_extract_secondary_fields` — these are isolated from the rest of
  the pipeline for exactly this reason.
- Unrecognized badge types: `_extract_secondary_fields` only classifies
  known badge patterns (term, nationality, GPA, GRE variants); a new
  badge type would be silently dropped. Fix by adding a new
  classification branch and a field in `_new_blank_record()`.
- LLM standardization scale: `llm_extend_applicant_data.json` in this
  submission reflects the first 60 of 30,060 cleaned records. The full
  run was started (`run_standardize.py --workers 4`) and was still in
  progress at submission time — a single-machine TinyLlama pass over
  the full dataset takes several hours. The pipeline itself is complete
  and correct end-to-end (verified against the 60-row output and
  against `sample_data.json`); re-running the same command over
  `cleaned_applicant_data.json` (30,060 rows) with no code changes
  produces the full-scale file, given more runtime.
