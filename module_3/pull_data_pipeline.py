"""
pull_data_pipeline.py

The actual work behind the Flask "Pull Data" button (Part 9). Runs, in
sequence:

    1. scrape.py   -- reuses the Module 2 scraper (resumes from its own
                       checkpoint, so it only fetches pages not already seen)
    2. clean.py     -- reuses the Module 2 cleaning logic
    3. load_data.py -- inserts into PostgreSQL; ON CONFLICT (url) DO NOTHING
                       means only genuinely new records get added, so
                       re-running this never duplicates or corrupts existing
                       rows

Progress is written to pull_status.json as it goes, so the Flask app (and
the "Update Analysis" button) can report accurate status without needing to
share memory with this subprocess.

IMPORTANT (inherited from Module 2): scrape.py attaches to an already-open,
manually-launched Chrome window (--remote-debugging-port=9222) rather than
driving its own browser, as the hybrid Cloudflare-bypass approach requires a
human to clear any challenge once. This script cannot do that step for you --
Chrome must already be open with remote debugging enabled and the Grad Cafe
session established before clicking "Pull Data", exactly as in Module 2. If
Chrome isn't attached, scrape.py's own robots.txt/connection check will fail
fast and this script records that as an error status rather than hanging.

Usage:
    python pull_data_pipeline.py [--max-pages N]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "pull_status.json"
LOG_FILE = BASE_DIR / "pull_data.log"


def write_status(state: str, message: str) -> None:
    STATUS_FILE.write_text(json.dumps({
        "state": state,  # "running" | "done" | "error" | "idle"
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


def run_step(label: str, cmd: list[str], log) -> bool:
    log.write(f"\n=== {label} ===\n")
    log.write(f"$ {' '.join(cmd)}\n")
    log.flush()
    write_status("running", f"{label}...")
    result = subprocess.run(cmd, cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode != 0:
        write_status("error", f"{label} failed (exit code {result.returncode}). "
                               f"See pull_data.log for details.")
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=50,
                         help="Cap on new pages to fetch this run (keeps 'Pull "
                              "Data' from running indefinitely).")
    args = parser.parse_args()

    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"\n\n### Pull Data run started {datetime.now(timezone.utc).isoformat()} ###\n")

        ok = run_step(
            "Scraping new Grad Cafe entries",
            [sys.executable, "scrape.py", "--max-pages", str(args.max_pages)],
            log,
        )
        if not ok:
            return

        ok = run_step(
            "Cleaning scraped data",
            [sys.executable, "clean.py", "--in", "applicant_data.json",
             "--out", "cleaned_applicant_data.json"],
            log,
        )
        if not ok:
            return

        ok = run_step(
            "Loading new records into PostgreSQL",
            [sys.executable, "load_data.py",
             "--cleaned", "cleaned_applicant_data.json",
             "--llm", "llm_extend_applicant_data.json"],
            log,
        )
        if not ok:
            return

        write_status("done", "Pull Data finished successfully -- new records "
                              "(if any) have been added to the database.")
        log.write(f"### Pull Data run finished {datetime.now(timezone.utc).isoformat()} ###\n")


if __name__ == "__main__":
    main()
