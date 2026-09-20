"""
app.py

Flask application factory for the Grad Cafe admissions analysis page: a
single dynamic page that reads results from PostgreSQL through the
SQLAlchemy ORM (:mod:`models` / :mod:`orm_queries`), plus a "Pull Data"
button and an "Update Analysis" button.

Unlike Module 3 (which built one module-level ``app`` object), Module 4
exposes :func:`create_app`, a factory that takes every external dependency
as an argument:

- ``database_url`` -- which Postgres database to read from. Defaults to
  :func:`models.build_database_url`, i.e. ``DATABASE_URL`` from the
  environment.
- ``get_analysis_results_fn`` -- a zero-argument callable returning the
  results dict the template renders. Defaults to a real ORM query; tests
  inject a fake that returns canned data instantly, with no database at
  all.
- ``start_pull_fn`` / ``is_pull_running_fn`` / ``get_pull_status_fn`` --
  the "Pull Data" busy-state machinery. Defaults reproduce Module 3's
  subprocess + status-file behavior; tests inject fakes backed by a plain
  in-memory flag, so busy/idle states are set directly rather than
  simulated with ``time.sleep()``.

This dependency-injection shape is what lets the test suite exercise every
route -- including the busy-gating behavior of ``/pull-data`` and
``/update-analysis`` -- through nothing but ``app.test_client()``, with no
live network call, subprocess, or database required.

Run directly with::

    python app.py

then visit http://127.0.0.1:8080
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from flask import Flask, jsonify, render_template

from . import orm_queries as oq
from .models import make_session_factory

BASE_DIR = Path(__file__).resolve().parent


def _default_status_file(base_dir: Path) -> Path:
    return base_dir / "pull_status.json"


def _read_status_file(status_file: Path) -> dict:
    if status_file.exists():
        try:
            return json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"state": "idle", "message": "No Pull Data run has been started yet."}


def get_analysis_results(session_factory) -> dict:
    """Gathers every required analysis result via the SQLAlchemy ORM. This
    is the single source of truth the template renders from, and the
    default ``get_analysis_results_fn`` wired up by :func:`create_app`."""
    with session_factory() as session:
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


class _SubprocessPullRunner:
    """Default, production ``start_pull_fn`` / ``is_pull_running_fn``:
    launches ``pull_data_pipeline.py`` as a subprocess (exactly like
    Module 3) and tracks it. Kept as a small class (instead of module
    globals) so each Flask app instance created by :func:`create_app` gets
    its own independent process handle -- important because the test
    suite may create several ``app`` instances in the same test run."""

    def __init__(self, base_dir: Path, status_file: Path):
        self._base_dir = base_dir
        self._status_file = status_file
        self._process: subprocess.Popen | None = None

    def is_running(self) -> bool:  # pragma: no cover - real subprocess tracking, exercised only interactively
        if self._process is not None and self._process.poll() is None:
            return True
        return _read_status_file(self._status_file).get("state") == "running"

    def start(self) -> None:  # pragma: no cover - launches a real subprocess, exercised only interactively
        self._status_file.write_text(json.dumps(
            {"state": "running", "message": "Pull Data started...", "updated_at": ""}
        ))
        self._process = subprocess.Popen(
            [sys.executable, "pull_data_pipeline.py"],
            cwd=self._base_dir,
        )

    def status(self) -> dict:  # pragma: no cover - trivial passthrough, see _read_status_file's own tests
        return _read_status_file(self._status_file)


def create_app(
    *,
    database_url: str | None = None,
    get_analysis_results_fn: Callable[[], dict] | None = None,
    start_pull_fn: Callable[[], None] | None = None,
    is_pull_running_fn: Callable[[], bool] | None = None,
    get_pull_status_fn: Callable[[], dict] | None = None,
    secret_key: str | None = None,
    base_dir: Path | None = None,
) -> Flask:
    """Builds and returns a configured Flask app.

    Every keyword argument is optional. Left unset, each one falls back to
    the real, production implementation (a live ORM query against
    ``database_url`` / ``DATABASE_URL``, and a real subprocess-based Pull
    Data pipeline). The test suite overrides one or more of them with
    fakes -- e.g. ``get_analysis_results_fn=lambda: FAKE_RESULTS`` -- to
    isolate the route/template logic from the database and the scraper
    entirely.
    """
    app = Flask(
        __name__,
        template_folder=str((base_dir or BASE_DIR) / "templates"),
        static_folder=str((base_dir or BASE_DIR) / "static"),
    )
    app.config["DATABASE_URL"] = database_url or os.environ.get("DATABASE_URL")
    app.secret_key = secret_key or os.environ.get("FLASK_SECRET_KEY", "dev-only-secret-change-me")

    resolved_base_dir = base_dir or BASE_DIR
    status_file = _default_status_file(resolved_base_dir)
    session_factory = make_session_factory(database_url=app.config["DATABASE_URL"])
    runner = _SubprocessPullRunner(resolved_base_dir, status_file)

    app.config["GET_ANALYSIS_RESULTS_FN"] = get_analysis_results_fn or (
        lambda: get_analysis_results(session_factory)
    )
    app.config["START_PULL_FN"] = start_pull_fn or runner.start
    app.config["IS_PULL_RUNNING_FN"] = is_pull_running_fn or runner.is_running
    app.config["GET_PULL_STATUS_FN"] = get_pull_status_fn or runner.status

    @app.template_filter("fmt2")
    def fmt2(value):
        """Formats a nullable average to exactly two decimals, or 'N/A'
        when there simply isn't enough data yet (e.g. a fresh/small
        database with no GRE scores reported) -- avoids the whole page
        crashing on a None the way a raw '%.2f' format would."""
        return "N/A" if value is None else f"{value:.2f}"

    @app.template_filter("fmtpct")
    def fmtpct(value):
        return "N/A" if value is None else f"{value:.2f}%"

    @app.route("/")
    def index():
        results = app.config["GET_ANALYSIS_RESULTS_FN"]()
        status = app.config["GET_PULL_STATUS_FN"]()
        pull_running = app.config["IS_PULL_RUNNING_FN"]()
        return render_template(
            "index.html", results=results, pull_status=status, pull_running=pull_running
        )

    @app.route("/pull-data", methods=["POST"])
    def pull_data():
        """Starts a Pull Data run. Always returns JSON (never a redirect),
        so the contract is directly assertable with ``app.test_client()``:
        409 ``{"ok": false, "busy": true}`` while a pull is already running
        and no second pull is started; otherwise 202 ``{"ok": true,
        "busy": false}`` and the pull is (really, or via the injected
        ``start_pull_fn`` fake) started. The page's own JS calls this via
        ``fetch`` and reloads on success."""
        if app.config["IS_PULL_RUNNING_FN"]():
            return jsonify({
                "ok": False, "busy": True,
                "message": "A Pull Data request is already running -- please "
                           "wait for it to finish before starting another.",
            }), 409

        app.config["START_PULL_FN"]()
        return jsonify({
            "ok": True, "busy": False,
            "message": "Pull Data started: checking Grad Cafe for newly "
                       "submitted results and adding any new records to "
                       "the database.",
        }), 202

    @app.route("/update-analysis", methods=["POST"])
    def update_analysis():
        """Re-runs the analysis query and returns it as JSON. Performs no
        update and returns 409 ``{"ok": false, "busy": true}`` while a Pull
        Data run is in progress, so stale-looking "new" data is never
        shown mid-pull; otherwise 200 ``{"ok": true, "results": {...}}``."""
        if app.config["IS_PULL_RUNNING_FN"]():
            return jsonify({
                "ok": False, "busy": True,
                "message": "A Pull Data request is currently running, so the "
                           "data hasn't changed yet -- try Update Analysis "
                           "again once it finishes.",
            }), 409

        results = app.config["GET_ANALYSIS_RESULTS_FN"]()
        return jsonify({
            "ok": True, "busy": False,
            "message": "Analysis refreshed with the most current data in the database.",
            "results": results,
        }), 200

    return app


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app = create_app()
    app.run(host="0.0.0.0", port=8080, debug=True)
