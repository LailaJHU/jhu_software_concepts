"""
test_flask_page.py -- marker: web

Verifies the ``/`` route renders a real HTML page with the structure the
assignment requires: a 200 response, the expected title, and every
required-analysis stat present with a stable ``data-testid`` selector a
test (or a future UI) can rely on. Parsed with BeautifulSoup rather than
substring-matching raw HTML, so the assertions survive incidental
whitespace/markup changes.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

pytestmark = pytest.mark.web

REQUIRED_STAT_TESTIDS = [
    "stat-q1", "stat-q2", "stat-q3-gpa", "stat-q3-gre-quant",
    "stat-q3-gre-verbal", "stat-q3-gre-aw", "stat-q4", "stat-q5",
    "stat-q6", "stat-q7", "stat-q8", "stat-q9", "stat-q9-minus-q8",
]


def test_index_returns_200_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")


def test_index_has_expected_title_and_heading(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    assert soup.title is not None
    assert "Grad Cafe" in soup.title.text
    h1 = soup.find("h1")
    assert h1 is not None
    assert "Grad Cafe Admissions Analysis" in h1.text


def test_index_renders_every_required_stat(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    for testid in REQUIRED_STAT_TESTIDS:
        el = soup.find(attrs={"data-testid": testid})
        assert el is not None, f"missing data-testid={testid!r}"
        assert el.text.strip() != ""


def test_index_renders_both_original_question_tables(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    assert soup.find(attrs={"data-testid": "table-original-gpa-bucket"}) is not None
    assert soup.find(attrs={"data-testid": "table-original-degree-breakdown"}) is not None


def test_index_shows_running_banner_only_when_pull_is_running(client, fake_pull_state):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    banner = soup.find(attrs={"data-testid": "pull-running-banner"})
    assert banner is not None
    assert "display:none" in (banner.get("style") or "")

    fake_pull_state.running = True
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    banner = soup.find(attrs={"data-testid": "pull-running-banner"})
    assert "display:none" not in (banner.get("style") or "")


def test_index_calls_injected_results_function_not_a_real_database(app, fake_results):
    """Confirms the route is actually wired to the injected fake -- not
    quietly falling back to a real DB connection -- by changing the fake's
    return value and checking it shows up on the page."""
    fake_results["q1_fall_2026_count"] = 123456
    resp = app.test_client().get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    stat = soup.find(attrs={"data-testid": "stat-q1"})
    assert stat.text.strip() == "123,456"
