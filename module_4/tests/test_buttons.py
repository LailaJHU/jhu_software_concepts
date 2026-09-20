"""
test_buttons.py -- marker: buttons

Exercises the Pull Data / Update Analysis busy-state contract entirely
through ``app.test_client()``:

- ``POST /pull-data`` starts a pull and returns 202 ``{"ok": true}`` when
  idle, or 409 ``{"ok": false, "busy": true}`` (and starts nothing) when a
  pull is already running.
- ``POST /update-analysis`` returns 200 with the refreshed results when
  idle, or 409 ``{"busy": true}`` (and never calls the results function)
  while a pull is running.

Busy state is set directly on ``fake_pull_state.running`` rather than
simulated with a real subprocess or ``time.sleep()``, per the assignment's
testing requirements.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from src.app import _read_status_file

pytestmark = pytest.mark.buttons


def test_read_status_file_missing_file_returns_idle_default(tmp_path):
    missing = tmp_path / "pull_status.json"
    assert _read_status_file(missing) == {
        "state": "idle", "message": "No Pull Data run has been started yet."
    }


def test_read_status_file_reads_valid_json(tmp_path):
    status_file = tmp_path / "pull_status.json"
    status_file.write_text('{"state": "done", "message": "all good"}')
    assert _read_status_file(status_file) == {"state": "done", "message": "all good"}


def test_read_status_file_falls_back_on_corrupt_json(tmp_path):
    status_file = tmp_path / "pull_status.json"
    status_file.write_text("{not valid json")
    result = _read_status_file(status_file)
    assert result["state"] == "idle"


def test_pull_data_starts_when_idle(client, fake_pull_state):
    assert fake_pull_state.start_calls == 0
    resp = client.post("/pull-data")
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["ok"] is True
    assert body["busy"] is False
    assert fake_pull_state.start_calls == 1
    assert fake_pull_state.is_running() is True


def test_pull_data_returns_409_and_does_not_start_a_second_pull(client, fake_pull_state):
    fake_pull_state.running = True
    resp = client.post("/pull-data")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["busy"] is True
    assert isinstance(body["message"], str) and body["message"] != ""
    assert fake_pull_state.start_calls == 0


def test_update_analysis_returns_results_when_idle(client, fake_results):
    resp = client.post("/update-analysis")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["results"]["q1_fall_2026_count"] == fake_results["q1_fall_2026_count"]


def test_update_analysis_returns_409_and_skips_the_query_while_busy(app, fake_pull_state):
    calls = []

    def counting_results_fn():
        calls.append(1)
        return {}

    app.config["GET_ANALYSIS_RESULTS_FN"] = counting_results_fn
    fake_pull_state.running = True

    resp = app.test_client().post("/update-analysis")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["busy"] is True
    assert calls == [], "update-analysis must not query while a pull is running"


def test_pull_data_button_disabled_in_html_while_running(client, fake_pull_state):
    fake_pull_state.running = True
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    btn = soup.find(attrs={"data-testid": "pull-data-btn"})
    assert btn.has_attr("disabled")


def test_pull_data_button_enabled_when_idle(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    btn = soup.find(attrs={"data-testid": "pull-data-btn"})
    assert not btn.has_attr("disabled")


def test_update_analysis_button_present_with_testid(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    assert soup.find(attrs={"data-testid": "update-analysis-btn"}) is not None
