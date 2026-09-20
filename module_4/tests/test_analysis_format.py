"""
test_analysis_format.py -- marker: analysis

Two concerns:

1. Presentation formatting -- every average/percentage on the rendered page
   must show exactly two decimal places (``\\d+\\.\\d{2}``), and percentages
   must carry a trailing ``%``. Checked with a regex over the parsed page
   text, not a hand count of characters.
2. The ``get_analysis_results`` aggregation itself (``app.py``) -- given a
   fake session and monkeypatched ``orm_queries`` functions, it must call
   every required question function exactly once and compute
   ``q9_minus_q8_diff`` correctly. This exercises ``get_analysis_results``
   directly (not through the Flask route), which is what brings that
   function to full coverage independent of the ``web`` tests.
"""

from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from src import app as app_module

pytestmark = pytest.mark.analysis

TWO_DECIMAL_PERCENT_RE = re.compile(r"\d+\.\d{2}%")
TWO_DECIMAL_RE = re.compile(r"\b\d+\.\d{2}\b")


def test_percentages_render_with_exactly_two_decimals(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    q2 = soup.find(attrs={"data-testid": "stat-q2"}).text.strip()
    q5 = soup.find(attrs={"data-testid": "stat-q5"}).text.strip()
    assert TWO_DECIMAL_PERCENT_RE.fullmatch(q2), q2
    assert TWO_DECIMAL_PERCENT_RE.fullmatch(q5), q5


def test_averages_render_with_exactly_two_decimals(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    for testid in ("stat-q3-gpa", "stat-q3-gre-quant", "stat-q3-gre-verbal",
                    "stat-q3-gre-aw", "stat-q4", "stat-q6"):
        value = soup.find(attrs={"data-testid": testid}).text.strip()
        assert TWO_DECIMAL_RE.fullmatch(value), f"{testid} = {value!r}"


def test_original_gpa_bucket_table_percentages_have_two_decimals(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    table = soup.find(attrs={"data-testid": "table-original-gpa-bucket"})
    pct_cells = [row.find_all("td")[2].text.strip() for row in table.find("tbody").find_all("tr")]
    assert pct_cells, "expected at least one GPA-bucket row"
    for cell in pct_cells:
        assert TWO_DECIMAL_PERCENT_RE.fullmatch(cell), cell


def test_counts_use_thousands_separators_not_decimals(client):
    resp = client.get("/")
    soup = BeautifulSoup(resp.data, "html.parser")
    q1 = soup.find(attrs={"data-testid": "stat-q1"}).text.strip()
    assert "," in q1
    assert "." not in q1


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_get_analysis_results_calls_every_question_and_computes_diff(monkeypatch):
    calls = []

    def record(name, value):
        def fn(session):
            calls.append(name)
            return value
        return fn

    monkeypatch.setattr(app_module.oq, "q1_fall_2026_count", record("q1", 100))
    monkeypatch.setattr(app_module.oq, "q2_percent_international", record("q2", 50.0))
    monkeypatch.setattr(app_module.oq, "q3_averages", record(
        "q3", {"avg_gpa": 3.5, "avg_gre_quant": 160.0, "avg_gre_verbal": 155.0, "avg_gre_aw": 4.0}
    ))
    monkeypatch.setattr(app_module.oq, "q4_avg_gpa_american_fall_2026", record("q4", 3.6))
    monkeypatch.setattr(app_module.oq, "q5_fall_2025_acceptance_pct", record("q5", 40.0))
    monkeypatch.setattr(app_module.oq, "q6_avg_gpa_accepted_fall_2026", record("q6", 3.7))
    monkeypatch.setattr(app_module.oq, "q7_jhu_masters_cs_count", record("q7", 3))
    monkeypatch.setattr(app_module.oq, "q8_fall_2026_phd_cs_acceptances_original_fields", record("q8", 10))
    monkeypatch.setattr(app_module.oq, "q9_fall_2026_phd_cs_acceptances_llm_fields", record("q9", 4))
    monkeypatch.setattr(app_module.oq, "original_gpa_bucket_acceptance", record("gpa_bucket", []))
    monkeypatch.setattr(app_module.oq, "original_degree_breakdown", record("degree", []))

    session_factory = lambda: _FakeSession()  # noqa: E731 - trivial test double
    results = app_module.get_analysis_results(session_factory)

    assert results["q9_minus_q8_diff"] == 4 - 10
    assert results["q1_fall_2026_count"] == 100
    assert sorted(calls) == sorted(
        ["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "gpa_bucket", "degree"]
    )
