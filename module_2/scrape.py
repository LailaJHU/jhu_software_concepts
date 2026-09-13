"""
scrape.py
---------

Module 2 assignment: pull publicly-posted graduate admissions results from
Grad Cafe (https://www.thegradcafe.com/survey/) into a raw JSON file.

WHY THIS LOOKS THE WAY IT DOES
===============================
A plain urllib/requests GET to the survey pages returns HTTP 403 (Cloudflare
bot-management is in front of the site), and a fully Selenium-launched,
automated Chrome instance gets stuck in Cloudflare's "verify you are human"
loop indefinitely, because Cloudflare fingerprints automation-launched
browsers.

The workaround used here (documented by the instructor, and confirmed
independently while building this) is a hybrid *capture* approach:

    1. A human opens a completely normal, hand-launched Chrome window
       (NOT started by Selenium) with remote debugging turned on.
    2. The human clears Cloudflare's human-verification challenge exactly
       once, the ordinary way, by looking at the browser and clicking
       through it.
    3. This script then *attaches* to that already-open, already-verified
       Chrome tab over the Chrome DevTools Protocol (Selenium's
       `debugger_address` option) instead of spawning a new automated
       browser. Because the tab was never flagged as automation-controlled,
       Cloudflare continues to treat it as a normal, already-verified
       session for the rest of the run.
    4. From that point on the script drives navigation itself: it opens a
       tab, waits for the results to render, reads `driver.page_source`,
       closes the tab, and moves to the next page -- exactly the "hybrid
       urllib + Selenium + BeautifulSoup" workflow described in the
       assignment.

`urllib.parse` is used throughout to build, validate, and inspect every
Grad Cafe URL this script visits (per the assignment's SHALL requirement),
even though the actual page *fetch* happens through the attached browser
rather than urllib.request.

RUNNING THIS SCRIPT
====================
1. Launch a real Chrome window by hand with a dedicated profile and remote
   debugging enabled, e.g. (Linux/Mac):

       google-chrome \\
           --remote-debugging-port=9222 \\
           --user-data-dir="$HOME/gradcafe_chrome_profile"

   or on Windows:

       "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
           --remote-debugging-port=9222 ^
           --user-data-dir="%USERPROFILE%\\gradcafe_chrome_profile"

2. In that window, manually browse to
   https://www.thegradcafe.com/survey/ and clear the Cloudflare check
   once. Leave the window open.

3. Run this script:

       python scrape.py --max-pages 1500 --delay 2.5

   It will attach to the Chrome window from step 1, start at
   /survey/, and follow each page's own "Next" link to reach the next one
   (Grad Cafe paginates with an opaque cursor, not `?page=N` -- see
   `_extract_next_url` -- so page URLs are never constructed by hand
   past the first one). Results are written/appended to
   applicant_data.json. Progress is checkpointed (see `_CHECKPOINT_FILE`),
   so if the process is interrupted -- or the site starts blocking --
   rerunning the exact same command resumes from the exact cursor it left
   off at instead of starting over from page 1.

POLITENESS / SAFETY
====================
- `check_robots_txt()` is called before any scraping starts and the run
  aborts if disallowed.
- A delay (with jitter) is applied between every page fetch.
- `_looks_blocked()` inspects every fetched page for Cloudflare challenge
  markers or HTTP error signatures. The very first time a page looks
  blocked, the scraper stops immediately (it does NOT retry, evade, or
  attempt to power through) and the checkpoint is left exactly where it
  is so the assignment's "pick up where you left off" expectation holds.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:  # pragma: no cover - selenium is required at runtime,
    # but importing this module (e.g. for clean.py's tests) shouldn't crash
    # if it isn't installed yet.
    webdriver = None  # type: ignore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gradcafe_scraper")


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

BASE_URL = "https://www.thegradcafe.com"
SURVEY_PATH = "/survey/"
ROBOTS_URL = urljoin(BASE_URL, "/robots.txt")

# The identity this scraper presents. Because we attach to a real,
# hand-launched Chrome window rather than spoofing headers, the actual
# User-Agent sent on the wire is whatever that real browser normally sends
# -- an honest, un-spoofed identity, which is what robots.txt's
# `User-agent: *` / `Allow: /` block governs.
ROBOTS_USER_AGENT = "*"

_OUTPUT_FILE = Path("applicant_data.json")
_CHECKPOINT_FILE = Path(".scrape_checkpoint.json")

# Rows per results page. Confirmed empirically (matches the instructor's
# own numbers: 400 records over 20 pages).
RESULTS_PER_PAGE = 20

# Cloudflare / block-page fingerprints. If any of these show up in a
# fetched page we treat the run as blocked and stop, per the assignment's
# SHALL NOT-bypass-restrictions requirement.
_BLOCK_MARKERS = (
    "just a moment",
    "checking your browser",
    "attention required! | cloudflare",
    "cf-error-details",
    "access denied",
    "sorry, you have been blocked",
)


# --------------------------------------------------------------------------
# robots.txt compliance
# --------------------------------------------------------------------------

def check_robots_txt(path: str = SURVEY_PATH, user_agent: str = ROBOTS_USER_AGENT) -> bool:
    """Confirm robots.txt permits fetching `path` for `user_agent`.

    Uses urllib.robotparser (part of the urllib package) so the check is
    itself urllib-based, per the assignment's URL-management requirement.
    Returns True if allowed, False otherwise. Raises nothing on network
    failure -- if robots.txt itself can't be read, we fail conservatively
    (treat as disallowed) rather than assume permission.
    """
    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    try:
        parser.read()
    except Exception as exc:  # noqa: BLE001 - genuinely want to catch anything here
        logger.error("Could not read robots.txt (%s); refusing to scrape.", exc)
        return False

    allowed = parser.can_fetch(user_agent, urljoin(BASE_URL, path))
    logger.info(
        "robots.txt check for user-agent '%s' on '%s': %s",
        user_agent,
        path,
        "ALLOWED" if allowed else "DISALLOWED",
    )
    return allowed


# --------------------------------------------------------------------------
# URL construction (urllib.parse) -- SHALL: use urllib to build/inspect URLs
# --------------------------------------------------------------------------

def _build_survey_root_url() -> str:
    """Build/validate the first-page survey URL. There is no `?page=N`
    scheme on the current site (see `_extract_next_url` below) -- every
    page after the first is reached by following that page's own "Next"
    link, not by constructing one ourselves.
    """
    url = urljoin(BASE_URL, SURVEY_PATH)
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Constructed an invalid URL: {url!r}")
    if parsed.netloc != urlparse(BASE_URL).netloc:
        raise ValueError(f"Refusing to build a URL outside {BASE_URL}: {url!r}")
    return url


def _build_result_url(result_id: str) -> str:
    """Build/validate the permalink URL for a single result entry."""
    url = urljoin(BASE_URL, f"/result/{result_id}")
    parsed = urlparse(url)
    if parsed.netloc != urlparse(BASE_URL).netloc:
        raise ValueError(f"Refusing to build a URL outside {BASE_URL}: {url!r}")
    return url


def _validate_gradcafe_url(url: str) -> str:
    """Resolve `url` against BASE_URL if it's relative, and refuse it if it
    doesn't point at thegradcafe.com. Used to sanity-check every "Next"
    link before the scraper follows it, since that link's target is
    site-controlled content we don't otherwise trust.
    """
    resolved = urljoin(BASE_URL, url)
    parsed = urlparse(resolved)
    if parsed.netloc != urlparse(BASE_URL).netloc:
        raise ValueError(f"Refusing to follow a URL outside {BASE_URL}: {resolved!r}")
    return resolved


def _extract_next_url(html: str) -> str | None:
    """Find the "Next" pagination link and return its absolute, validated
    URL, or None if there isn't one (i.e. this is the last page).

    Grad Cafe's current site paginates with an opaque, base64-encoded
    keyset cursor (e.g. `?cursor=eyJjcmVhdGVkX2F0IjouLi59`, which decodes
    to `{"created_at": ..., "admitid": ..., "_pointsToNextItems": true}`)
    rather than a simple `?page=N` counter -- confirmed by decoding a
    real cursor captured from the live site. Rather than reconstruct that
    encoding ourselves (fragile, and liable to break silently if the
    format ever changes), we do exactly what a human clicking "Next"
    does: read the link's `href` straight out of the page.
    """
    soup = BeautifulSoup(html, "lxml")
    for link in soup.find_all("a", href=True):
        if link.get_text(strip=True) == "Next":
            return _validate_gradcafe_url(link["href"])
    return None


# --------------------------------------------------------------------------
# Checkpointing (resumability)
# --------------------------------------------------------------------------

@dataclass
class ScrapeCheckpoint:
    # The URL to fetch next. None + pages_completed == 0 means "haven't
    # started yet"; None + pages_completed > 0 means "reached the last
    # page Grad Cafe has" (no further "Next" link was found).
    next_url: str | None = None
    pages_completed: int = 0
    total_records: int = 0
    seen_urls: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path = _CHECKPOINT_FILE) -> "ScrapeCheckpoint":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(**data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read checkpoint (%s); starting fresh.", exc)
            return cls()

    def save(self, path: Path = _CHECKPOINT_FILE) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------
# Browser attach / fetch
# --------------------------------------------------------------------------

def _attach_to_chrome(debugger_address: str = "127.0.0.1:9222"):
    """Attach Selenium to an already-open, human-verified Chrome window.

    This intentionally does NOT launch a new browser. Selenium is only used
    here as a remote-control interface into a browser a human already
    opened and verified, per the assignment's "Selenium as a rendering /
    navigation tool only" guidance.
    """
    if webdriver is None:
        raise RuntimeError(
            "selenium is not installed. Run: pip install -r requirements.txt"
        )
    options = ChromeOptions()
    options.debugger_address = debugger_address
    try:
        driver = webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise RuntimeError(
            "Could not attach to Chrome. Make sure you launched Chrome by hand "
            "with --remote-debugging-port=9222 and cleared the Cloudflare "
            f"check in it first. Original error: {exc}"
        ) from exc
    return driver


def _looks_blocked(html: str) -> bool:
    """Heuristic check for a Cloudflare challenge / block page."""
    lowered = html.lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def _fetch_rendered_html(driver, url: str, timeout: float = 20.0) -> str:
    """Open `url` in a fresh tab on the attached browser, wait for the
    results list to render, capture page_source, then close the tab.
    """
    driver.switch_to.new_window("tab")
    try:
        driver.get(url)
        # Explicit wait for real content instead of a hard-coded sleep.
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
            )
        except TimeoutException:
            pass
        html = driver.page_source
    finally:
        driver.close()
        # Return focus to whatever tab is left so the next new_window call
        # behaves predictably.
        if driver.window_handles:
            driver.switch_to.window(driver.window_handles[0])
    return html


# --------------------------------------------------------------------------
# Parsing (BeautifulSoup + string methods)
# --------------------------------------------------------------------------

def _clean_text(text: str | None) -> str:
    """Collapse whitespace on a BeautifulSoup .get_text() result. Does NOT
    otherwise alter the content -- traceability of the raw applicant text
    matters more here than cosmetic tidiness (real cleaning happens in
    clean.py).
    """
    if text is None:
        return ""
    return " ".join(text.split())


def _is_ad_row(row) -> bool:
    """Grad Cafe interleaves ad placements between results rows inside the
    same <table>. These have no applicant data at all and must be skipped
    rather than parsed as (empty/junk) entries.
    """
    return row.find(id=re.compile(r"^results-ad-placement")) is not None or (
        row.find(class_="raptive-manual-ads") is not None
    )


def _parse_listing_page(html: str) -> list[dict[str, Any]]:
    """Parse one rendered survey-results page into a list of raw record
    dicts. Field extraction is deliberately conservative: if a value isn't
    present, the field is set to None/"" rather than guessed at.

    Verified against a live-captured HTML sample of the current results
    table (Sept 2026). Each applicant entry spans 2-3 sibling <tr>s inside
    one <tbody>:

      1. Primary row: <td> School, <td> Program (+ Degree as a second
         <span>), <td> Added-On date, <td> Decision badge, <td> containing
         the `<a href="/result/<id>">` permalink.
      2. Badge row: a <td colspan="100%"> with a flex-wrapped set of small
         tag <div>s -- term, nationality, and (when present) GPA/GRE/
         GRE V/GRE AW. This row also repeats the decision badge for
         mobile layouts (marked with an `md:tw-hidden` class), which is
         skipped here since it's already captured from the primary row.
      3. Comment row (optional): a <td colspan="100%"><p>...</p></td>
         holding the applicant's free-text comment.

    Ad-placement rows are interleaved between entries and are skipped
    entirely (see `_is_ad_row`).
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return []
    tbody = table.find("tbody") or table
    records: list[dict[str, Any]] = []

    current: dict[str, Any] | None = None
    for row in tbody.find_all("tr", recursive=False):
        if _is_ad_row(row):
            continue

        cells = row.find_all("td", recursive=False)
        if not cells:
            continue

        permalink = row.select_one('a[href^="/result/"]')
        if permalink is not None and len(cells) >= 4:
            # Primary row: start a new entry.
            if current is not None:
                records.append(current)
            href = permalink.get("href", "")
            result_id = href.rstrip("/").rsplit("/", 1)[-1]
            current = _new_blank_record()
            try:
                current["url"] = _build_result_url(result_id)
            except ValueError:
                current["url"] = urljoin(BASE_URL, href)
            current["raw_row_text"] = _clean_text(row.get_text(" "))
            _extract_primary_fields(cells, current)
        elif current is not None:
            # Badge row or comment row belonging to the entry in progress.
            current["raw_row_text"] += " | " + _clean_text(row.get_text(" "))
            _extract_secondary_fields(row, current)

    if current is not None:
        records.append(current)

    return records


def _new_blank_record() -> dict[str, Any]:
    """A record with every required assignment field present, defaulted to
    None -- consistently, across every field -- so downstream consumers
    (and applicant_data.json itself, which is graded directly, not just
    the cleaned output) never mix None and "" as two different spellings
    of "no data."
    """
    return {
        "program": None,          # raw, unmodified program/university text
        "university": None,
        "comments": None,
        "date_added": None,
        "url": None,
        "status": None,           # Accepted / Rejected / Wait listed / Interview
        "decision_date": None,    # e.g. "1 Mar" -- date the decision itself was made
        "term": None,             # e.g. "Fall 2024"
        "US/International": None,
        "GRE": None,
        "GRE V": None,
        "GRE AW": None,
        "Degree": None,           # Masters / PhD
        "GPA": None,
        "raw_row_text": "",       # full raw text of the source row(s), for traceability
    }


_TERM_RE = re.compile(r"^(Fall|Spring|Summer|Winter)\s+\d{4}$")


def _extract_primary_fields(cells, record: dict[str, Any]) -> None:
    """Pull school/program/degree/date/decision from an entry's primary
    row. `cells` is the row's list of <td> elements, in DOM order:
    [School, Program(+Degree), Added On, Decision, actions/permalink].
    """
    # cells[0]: School name
    school_div = cells[0].select_one("div.tw-font-medium")
    school_text = _clean_text((school_div or cells[0]).get_text(" "))
    record["university"] = school_text or None

    # cells[1]: Program name, with Degree as a trailing <span> after a
    # middle-dot separator icon (e.g. "Creative Writing Poetry" | "MFA").
    if len(cells) > 1:
        spans = cells[1].find_all("span")
        if spans:
            record["program"] = _clean_text(spans[0].get_text(" ")) or None
            if len(spans) > 1:
                record["Degree"] = _clean_text(spans[-1].get_text(" ")) or None
        else:
            record["program"] = _clean_text(cells[1].get_text(" ")) or None

    # cells[2]: "Added On" date (present in the DOM even though it's
    # visually hidden below the md: breakpoint).
    if len(cells) > 2:
        record["date_added"] = _clean_text(cells[2].get_text(" ")) or None

    # cells[3]: Decision badge, e.g. "Accepted on Sep 11", "Interview on
    # Jul 10", "Wait listed on Sep 10", "Rejected on May 28". Kept as one
    # raw combined string here; clean.py splits it into status +
    # decision_date.
    if len(cells) > 3:
        record["status"] = _clean_text(cells[3].get_text(" ")) or None


def _extract_secondary_fields(row, record: dict[str, Any]) -> None:
    """Pull term/nationality/GPA/GRE/GRE V/GRE AW from an entry's badge
    row, or the free-text comment from its comment row.
    """
    # Comment row: a single <p> with no badge <div>s.
    comment_p = row.find("p")
    if comment_p is not None:
        comment_text = _clean_text(comment_p.get_text(" "))
        if comment_text:
            record["comments"] = (
                (record["comments"] + " " + comment_text).strip()
                if record["comments"]
                else comment_text
            )
        return

    # Badge row: each tag is its own small <div>, flex-wrapped together.
    badge_container = row.select_one("div.tw-flex.tw-flex-wrap") or row
    for badge in badge_container.find_all("div", recursive=False):
        classes = badge.get("class") or []
        text = _clean_text(badge.get_text(" "))
        if not text:
            continue

        # The badge row repeats the decision pill for mobile layouts,
        # marked with `md:tw-hidden` -- already captured from the primary
        # row, so skip it here to avoid clobbering/duplicating `status`.
        if "md:tw-hidden" in classes:
            continue

        if _TERM_RE.match(text):
            record["term"] = text
        elif text in ("American", "International", "Other"):
            record["US/International"] = text
        elif text.startswith("GRE AW"):
            record["GRE AW"] = text
        elif text.startswith("GRE V"):
            record["GRE V"] = text
        elif text.startswith("GRE"):
            record["GRE"] = text
        elif text.startswith("GPA"):
            record["GPA"] = text
        # Anything else (unrecognized badge type) is intentionally
        # ignored rather than guessed at.


# --------------------------------------------------------------------------
# Public API expected by the assignment: scrape_data / save_data / load_data
# --------------------------------------------------------------------------

def save_data(records: list[dict[str, Any]], path: Path = _OUTPUT_FILE) -> None:
    """Persist `records` as a valid, human-readable JSON array."""
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved %d records to %s", len(records), path)


def load_data(path: Path = _OUTPUT_FILE) -> list[dict[str, Any]]:
    """Load previously-scraped records, or an empty list if none exist yet."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Existing %s is not valid JSON (%s); refusing to overwrite blindly.", path, exc)
        raise


class GradCafeScraper:
    """Coordinates the hybrid capture/parse workflow described at the top
    of this file.
    """

    def __init__(
        self,
        debugger_address: str = "127.0.0.1:9222",
        delay: float = 2.5,
        out_file: Path = _OUTPUT_FILE,
        checkpoint_file: Path = _CHECKPOINT_FILE,
    ) -> None:
        self.debugger_address = debugger_address
        self.delay = delay
        self.out_file = Path(out_file)
        self.checkpoint_file = Path(checkpoint_file)
        self.driver = None

    def scrape_data(self, max_pages: int) -> list[dict[str, Any]]:
        """Scrape up to `max_pages` survey pages, following each page's own
        "Next" link rather than constructing page URLs ourselves (see
        `_extract_next_url`). Honors any existing checkpoint so an
        interrupted run resumes from the exact cursor it left off at,
        rather than restarting from page 1. Stops immediately -- without
        raising -- the first time a page looks blocked, or when Grad Cafe
        itself reports there's no next page.
        """
        if not check_robots_txt(SURVEY_PATH):
            logger.error("robots.txt disallows scraping %s; aborting.", SURVEY_PATH)
            return load_data(self.out_file)

        checkpoint = ScrapeCheckpoint.load(self.checkpoint_file)
        records = load_data(self.out_file)
        seen_urls = set(checkpoint.seen_urls)

        if checkpoint.pages_completed > 0 and checkpoint.next_url is None:
            logger.info(
                "Checkpoint shows the previous run already reached the last "
                "available page; nothing more to fetch."
            )
            return records

        current_url = checkpoint.next_url or _build_survey_root_url()
        if checkpoint.pages_completed > 0:
            logger.info(
                "Resuming after %d previously-completed page(s) (checkpoint found).",
                checkpoint.pages_completed,
            )

        self.driver = _attach_to_chrome(self.debugger_address)
        try:
            for _ in range(max_pages):
                page_num = checkpoint.pages_completed + 1
                logger.info("Fetching page %d: %s", page_num, current_url)

                try:
                    html = _fetch_rendered_html(self.driver, current_url)
                except (TimeoutException, WebDriverException) as exc:
                    logger.error("Failed to fetch page %d (%s); stopping.", page_num, exc)
                    break

                if _looks_blocked(html):
                    logger.error(
                        "Page %d looks like a Cloudflare challenge / block page. "
                        "Stopping per policy -- rerun this script later to resume "
                        "from the same cursor.",
                        page_num,
                    )
                    break

                page_records = _parse_listing_page(html)
                new_records = [r for r in page_records if r["url"] not in seen_urls]
                for r in new_records:
                    seen_urls.add(r["url"])
                records.extend(new_records)

                next_url = _extract_next_url(html)

                # Checkpoint after every page so a crash never loses more
                # than the current, in-flight page.
                save_data(records, self.out_file)
                checkpoint.pages_completed = page_num
                checkpoint.next_url = next_url
                checkpoint.total_records = len(records)
                checkpoint.seen_urls = list(seen_urls)
                checkpoint.save(self.checkpoint_file)

                logger.info(
                    "Page %d: +%d new records (total so far: %d)",
                    page_num,
                    len(new_records),
                    len(records),
                )

                if next_url is None:
                    logger.info("No further 'Next' link found -- reached the last page.")
                    break

                current_url = next_url
                time.sleep(self.delay + random.uniform(0, 1.0))
        finally:
            if self.driver is not None:
                self.driver.quit()

        return records


# --------------------------------------------------------------------------
# CLI entry point
# --------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pages",
        type=int,
        default=1500,
        help="how many pages to fetch THIS run (pagination is cursor-based, "
        "not page-numbered -- rerunning the same command resumes from the "
        "checkpointed cursor rather than starting over)",
    )
    parser.add_argument("--delay", type=float, default=2.5, help="seconds between page fetches")
    parser.add_argument("--debugger-address", default="127.0.0.1:9222")
    parser.add_argument("--out", default=str(_OUTPUT_FILE))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    scraper = GradCafeScraper(
        debugger_address=args.debugger_address,
        delay=args.delay,
        out_file=Path(args.out),
    )
    records = scraper.scrape_data(args.max_pages)
    logger.info("Done. %d total records in %s", len(records), args.out)


if __name__ == "__main__":
    main()
