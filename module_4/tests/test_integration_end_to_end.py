"""
test_integration_end_to_end.py -- marker: integration

Ties multiple pieces together, the way a single real user action would:

1. Clicking "Pull Data" then "Update Analysis" while the pull is still
   running -- through the Flask test client, using the same shared
   ``fake_pull_state`` both routes read from, so the busy-gating actually
   has to hold across two separate requests (not just within one).
2. The pipeline's step-sequencing logic (:func:`pull_data_pipeline.run_pipeline`)
   with fake scrape/clean/load steps standing in for the real ones --
   verifying it stops at the first failure and never runs the steps after
   it, with no subprocess, network call, or ``sleep()`` involved.
3. A true end-to-end slice against a real (throwaway) database: load two
   applicants with :func:`load_data.load`, then read them back out through
   a *real* ``create_app`` instance (no injected results function) and
   confirm the live page reflects what's actually in the database.
"""

from __future__ import annotations

import json

import pytest

from src import load_data
from src.app import create_app
from src.pull_data_pipeline import PipelineStep, run_pipeline

pytestmark = pytest.mark.integration


def test_pull_then_update_analysis_busy_gating_holds_across_requests(client, fake_pull_state):
    pull_resp = client.post("/pull-data")
    assert pull_resp.status_code == 202
    assert fake_pull_state.is_running() is True

    update_resp = client.post("/update-analysis")
    assert update_resp.status_code == 409
    assert update_resp.get_json()["busy"] is True

    fake_pull_state.running = False
    update_resp = client.post("/update-analysis")
    assert update_resp.status_code == 200
    assert update_resp.get_json()["ok"] is True


def test_run_pipeline_succeeds_through_every_step(tmp_path):
    status_file = tmp_path / "pull_status.json"
    calls = []
    steps = [
        PipelineStep("scrape", lambda: (calls.append("scrape") or True)),
        PipelineStep("clean", lambda: (calls.append("clean") or True)),
        PipelineStep("load", lambda: (calls.append("load") or True)),
    ]

    ok = run_pipeline(steps, status_file=status_file)

    assert ok is True
    assert calls == ["scrape", "clean", "load"]
    status = json.loads(status_file.read_text())
    assert status["state"] == "done"


def test_run_pipeline_stops_at_first_failure(tmp_path):
    status_file = tmp_path / "pull_status.json"
    calls = []
    steps = [
        PipelineStep("scrape", lambda: (calls.append("scrape") or True)),
        PipelineStep("clean", lambda: (calls.append("clean") or False)),
        PipelineStep("load", lambda: (calls.append("load") or True)),
    ]

    ok = run_pipeline(steps, status_file=status_file)

    assert ok is False
    assert calls == ["scrape", "clean"], "load must never run after clean fails"
    status = json.loads(status_file.read_text())
    assert status["state"] == "error"
    assert "clean" in status["message"]


def test_run_pipeline_records_error_status_when_a_step_raises(tmp_path):
    status_file = tmp_path / "pull_status.json"
    steps = [PipelineStep("scrape", lambda: (_ for _ in ()).throw(RuntimeError("no chrome attached")))]

    ok = run_pipeline(steps, status_file=status_file)

    assert ok is False
    status = json.loads(status_file.read_text())
    assert status["state"] == "error"
    assert "no chrome attached" in status["message"]


def test_end_to_end_load_then_view_through_a_real_app(test_database_url, test_db_dsn, tmp_path):
    rows = [
        {"program": "Computer Science", "university": "Stanford",
         "url": "https://example.com/e2e/1", "status": "Accepted",
         "term": "Fall 2026", "US/International": "American", "GPA": "3.95",
         "Degree": "PhD", "date_added": "Sep 1, 2026"},
        {"program": "Computer Science", "university": "Carnegie Mellon",
         "url": "https://example.com/e2e/2", "status": "Accepted",
         "term": "Fall 2025", "US/International": "International", "GPA": "3.5",
         "Degree": "Masters", "date_added": "Aug 1, 2025"},
    ]
    cleaned_path = tmp_path / "cleaned_applicant_data.json"
    cleaned_path.write_text(json.dumps(rows))

    load_stats = load_data.load(str(cleaned_path), None, dsn=test_db_dsn)
    assert load_stats["total_in_table"] == 2

    real_app = create_app(database_url=test_database_url, secret_key="test-secret")
    real_app.config.update(TESTING=True)

    resp = real_app.test_client().get("/")
    assert resp.status_code == 200

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.data, "html.parser")
    q1 = soup.find(attrs={"data-testid": "stat-q1"}).text.strip()
    assert q1 == "1"  # exactly one Fall 2026 row was loaded
