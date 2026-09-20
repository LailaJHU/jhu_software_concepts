"""
app.py

Flask application for Module 3, Part 8-10: a single dynamic analysis page
that reads results from PostgreSQL through the SQLAlchemy ORM (models.py /
orm_queries.py -- never raw SQL/psycopg in this file), plus a "Pull Data"
button (Part 9) and an "Update Analysis" button (Part 10).

Run with:
    python app.py
then visit http://127.0.0.1:8080
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, url_for

import orm_queries as oq
from models import SessionLocal

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret-change-me")

BASE_DIR = Path(__file__).resolve().parent
STATUS_FILE = BASE_DIR / "pull_status.json"

# Tracks the "Pull Data" subprocess launched by THIS Flask process. We also
# consult pull_status.json (written by pull_data_pipeline.py) so status is
# accurate even if this Flask process was restarted after a pull was kicked
# off previously.
_pull_process: subprocess.Popen | None = None


def _read_status_file() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"state": "idle", "message": "No Pull Data run has been started yet."}


def is_pull_running() -> bool:
    """A pull is considered 'running' if either this process still has a live
    subprocess handle, or the status file says so (covers a Flask restart)."""
    global _pull_process
    if _pull_process is not None and _pull_process.poll() is None:
        return True
    return _read_status_file().get("state") == "running"


def get_analysis_results() -> dict:
    """Gathers every required analysis result via the SQLAlchemy ORM. This is
    the single source of truth the template renders from."""
    with SessionLocal() as session:
        q3 = oq.q3_averages(session)
        results = {
            "q1_fall_2026_count": oq.q1_fall_2026_count(session),
            "q2_percent_international": oq.q2_percent_international(session),
            "q3_avg_gpa": q3["avg_gpa"],
            "q3_avg_gre_quant": q3["avg_gre_quant"],
            "q3_avg_gre_verbal": q3["avg_gre_verbal"],
            "q3_avg_gre_aw": q3["avg_gre_aw"],
            "q4_avg_gpa_american_fall_2026": oq.q4_avg_gpa_american_fall_2026(session),
            "q5_fall_2025_acceptance_pct": oq.q5_fall_2025_acceptance_pct(session),
            "q6_avg_gpa_accepted_fall_2026": oq.q6_avg_gpa_accepted_fall_2026(session),
            "q7_jhu_masters_cs_count": oq.q7_jhu_masters_cs_count(session),
            "q8_original_field_count": oq.q8_fall_2026_phd_cs_acceptances_original_fields(session),
            "q9_llm_field_count": oq.q9_fall_2026_phd_cs_acceptances_llm_fields(session),
            "original_gpa_bucket": oq.original_gpa_bucket_acceptance(session),
            "original_degree_breakdown": oq.original_degree_breakdown(session),
        }
    results["q9_minus_q8_diff"] = results["q9_llm_field_count"] - results["q8_original_field_count"]
    return results


@app.route("/")
def index():
    results = get_analysis_results()
    status = _read_status_file()
    return render_template("index.html", results=results, pull_status=status,
                            pull_running=is_pull_running())


@app.route("/pull-data", methods=["POST"])
def pull_data():
    global _pull_process
    if is_pull_running():
        flash("A Pull Data request is already running -- please wait for it "
              "to finish before starting another.", "warning")
        return redirect(url_for("index"))

    STATUS_FILE.write_text(json.dumps(
        {"state": "running", "message": "Pull Data started...", "updated_at": ""}
    ))
    _pull_process = subprocess.Popen(
        [sys.executable, "pull_data_pipeline.py"],
        cwd=BASE_DIR,
    )
    flash("Pull Data started: checking Grad Cafe for newly submitted results "
          "and adding any new records to the database. This can take a "
          "while -- feel free to keep browsing; use Update Analysis later "
          "to see new data once it's ready.", "info")
    return redirect(url_for("index"))


@app.route("/update-analysis", methods=["POST"])
def update_analysis():
    if is_pull_running():
        flash("A Pull Data request is currently running, so the data hasn't "
              "changed yet -- try Update Analysis again once it finishes.", "warning")
    else:
        flash("Analysis refreshed with the most current data in the database.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
