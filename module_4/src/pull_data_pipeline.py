"""
pull_data_pipeline.py

The actual work behind the Flask "Pull Data" button. Runs, in sequence:

    1. scrape.py   -- reuses the Module 2 scraper (resumes from its own
                       checkpoint, so it only fetches pages not already seen)
    2. clean.py     -- reuses the Module 2 cleaning logic
    3. load_data.py -- inserts into PostgreSQL; ON CONFLICT (url) DO NOTHING
                       means only genuinely new records get added, so
                       re-running this never duplicates or corrupts existing
                       rows

Progress is written to ``pull_status.json`` as it goes, so the Flask app
(and the "Update Analysis" button) can report accurate status without
needing to share memory with this subprocess.

Each of the three steps is expressed as a small ``PipelineStep`` -- a label
plus a zero-argument callable that returns ``True`` on success. The default
steps shell out to the real scripts (``scrape.py`` / ``clean.py`` /
``load_data.py``) exactly as Module 3 did. The test suite instead builds a
:class:`Pipeline` with fake steps (plain functions, no subprocess, no
network, no ``sleep()``) to exercise the sequencing and error-handling
logic -- stop at the first failed step, write the right status at each
stage -- without touching a real browser or database.

IMPORTANT (inherited from Module 2): ``scrape.py`` attaches to an
already-open, manually-launched Chrome window
(``--remote-debugging-port=9222``) rather than driving its own browser, as
the hybrid Cloudflare-bypass approach requires a human to clear any
challenge once. This script cannot do that step for you -- Chrome must
already be open with remote debugging enabled and the Grad Cafe session
established before clicking "Pull Data". If Chrome isn't attached,
``scrape.py``'s own connection check fails fast and this script records
that as an error status rather than hanging.

Usage::

    python pull_data_pipeline.py [--max-pages N]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "pull_status.json"
LOG_FILE = BASE_DIR / "pull_data.log"


def write_status(state: str, message: str, status_file: Path | None = None) -> None:
    """Writes the pull's current state to ``status_file`` (or the module's
    default ``pull_status.json``) as JSON: ``{"state", "message",
    "updated_at"}``. ``state`` is one of "running" / "done" / "error"."""
    target = status_file or STATUS_FILE
    target.write_text(json.dumps({
        "state": state,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2))


@dataclass
class PipelineStep:
    """One stage of the pipeline: a human-readable label plus a
    zero-argument callable that does the work and returns True on success
    (or raises / returns False on failure)."""

    label: str
    run: Callable[[], bool]


def _subprocess_step(cmd: list[str], log) -> bool:  # pragma: no cover - real subprocess call, exercised only interactively
    log.write(f"$ {' '.join(cmd)}\n")
    log.flush()
    result = subprocess.run(cmd, cwd=BASE_DIR, stdout=log, stderr=subprocess.STDOUT)
    return result.returncode == 0


def default_steps(max_pages: int, log) -> list[PipelineStep]:  # pragma: no cover - thin wiring around subprocess, covered indirectly via fakes
    """The real, production pipeline steps: shell out to scrape.py ->
    clean.py -> load_data.py, exactly as Module 3 did."""
    return [
        PipelineStep(
            "Scraping new Grad Cafe entries",
            lambda: _subprocess_step(
                [sys.executable, "scrape.py", "--max-pages", str(max_pages)], log
            ),
        ),
        PipelineStep(
            "Cleaning scraped data",
            lambda: _subprocess_step(
                [sys.executable, "clean.py", "--in", "applicant_data.json",
                 "--out", "cleaned_applicant_data.json"], log
            ),
        ),
        PipelineStep(
            "Loading new records into PostgreSQL",
            lambda: _subprocess_step(
                [sys.executable, "load_data.py",
                 "--cleaned", "cleaned_applicant_data.json",
                 "--llm", "llm_extend_applicant_data.json"], log
            ),
        ),
    ]


def run_pipeline(steps: list[PipelineStep], status_file: Path | None = None) -> bool:
    """Runs ``steps`` in order, writing status after each one, and stops at
    the first failure. Returns True only if every step succeeded.

    This is the function the "integration" tests exercise directly, with a
    list of fake :class:`PipelineStep` objects standing in for the real
    scrape/clean/load steps -- so the sequencing and stop-on-first-failure
    behavior is verified without any real network call, browser, or
    database, and without any ``time.sleep()``.
    """
    for step in steps:
        write_status("running", f"{step.label}...", status_file)
        try:
            ok = step.run()
        except Exception as exc:  # noqa: BLE001 - surface any step's failure as a status, not a crash
            write_status("error", f"{step.label} failed: {exc}", status_file)
            return False
        if not ok:
            write_status(
                "error",
                f"{step.label} failed. See pull_data.log for details.",
                status_file,
            )
            return False

    write_status(
        "done",
        "Pull Data finished successfully -- new records (if any) have been "
        "added to the database.",
        status_file,
    )
    return True


def main():  # pragma: no cover - CLI entry point, exercised only interactively
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=50,
                         help="Cap on new pages to fetch this run (keeps 'Pull "
                              "Data' from running indefinitely).")
    args = parser.parse_args()

    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(f"\n\n### Pull Data run started {datetime.now(timezone.utc).isoformat()} ###\n")
        ok = run_pipeline(default_steps(args.max_pages, log))
        status = "finished successfully" if ok else "stopped after a failed step"
        log.write(f"### Pull Data run {status} {datetime.now(timezone.utc).isoformat()} ###\n")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
