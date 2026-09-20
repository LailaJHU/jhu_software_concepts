Testing Guide
==============

Running the suite
-------------------

.. code-block:: bash

   cd module_4
   pip install -r requirements.txt
   pytest

``pytest.ini`` already sets ``--cov=src --cov-report=term-missing
--cov-fail-under=100``, so a plain ``pytest`` run prints a coverage table
and fails the run if coverage drops below 100%. A saved passing run is
checked in at ``module_4/coverage_summary.txt``.

Run only one category with ``-m``::

   pytest -m web
   pytest -m "db or integration"

Test database
---------------

The ``db`` and ``integration`` tests need a real PostgreSQL server. By
default they connect to a throwaway ``gradcafe_test`` database (created
automatically the first time the suite runs, using the same ``DB_USER`` /
``DB_HOST`` credentials as the real app) -- **the real ``gradcafe``
database is never touched by the test suite.** In CI, ``tests.yml`` instead
sets ``DATABASE_URL`` to a fresh Postgres service container, so no local
setup is required there.

The five required test files
-------------------------------

``test_flask_page.py`` (marker ``web``)
   Renders ``GET /`` and checks the page's structure with BeautifulSoup:
   the right title, every required stat present under a stable
   ``data-testid``, and that the "pull running" banner only shows when a
   pull is actually in progress.

``test_buttons.py`` (marker ``buttons``)
   Exercises the Pull Data / Update Analysis busy-state contract:
   ``POST /pull-data`` returns 202 ``{"ok": true}`` when idle and starts a
   pull, or 409 ``{"busy": true}`` (starting nothing) if one is already
   running; ``POST /update-analysis`` returns 200 with fresh results when
   idle, or 409 and *never calls the results function* while busy. Busy
   state is set directly on a fake (``fake_pull_state.running = True``) --
   never with ``time.sleep()``.

``test_analysis_format.py`` (marker ``analysis``)
   Regex-checks that every average/percentage on the page renders with
   exactly two decimal places (``\d+\.\d{2}``, with a trailing ``%`` where
   applicable), and unit-tests :func:`src.app.get_analysis_results`
   directly against a fake session with monkeypatched query functions, to
   confirm it calls every required question and computes the Q9-minus-Q8
   difference correctly.

``test_db_insert.py`` (marker ``db``)
   Real-database tests for :mod:`src.load_data`: parsing helpers
   (``parse_date`` / ``parse_float`` / ``build_record``) plus the
   idempotency property the Pull Data button depends on -- loading the
   same file twice must never create duplicate rows, because every insert
   goes through ``ON CONFLICT (url) DO NOTHING``.

``test_integration_end_to_end.py`` (marker ``integration``)
   Ties pieces together the way a real user session would: Pull Data then
   Update Analysis through the same shared busy-state fake (confirming the
   gating holds *across* two separate requests, not just within one); the
   pipeline's step-sequencing logic with fake scrape/clean/load steps
   (stops at the first failure, never runs the steps after it); and a true
   end-to-end slice that loads real rows into the throwaway test database
   and reads them back out through a real (non-faked) ``create_app()``
   instance.

Why dependency injection, not mocking the database driver
-------------------------------------------------------------

:func:`src.app.create_app` takes every external dependency
(``get_analysis_results_fn``, ``start_pull_fn``, ``is_pull_running_fn``,
``get_pull_status_fn``) as a keyword argument. The ``web`` / ``buttons`` /
``analysis`` tests pass plain fakes for these -- not a mocked
``psycopg``/SQLAlchemy connection -- which keeps those tests fast, makes
the busy-state gating trivially controllable (set a boolean, no
``sleep()``), and keeps the route/template layer's tests independent of
whether a real Postgres server happens to be running. The ``db`` and
``integration`` tests then verify the *real* database-facing code
(:mod:`src.load_data`, and one full real-app slice) separately, against an
actual throwaway database -- so the ``ON CONFLICT`` idempotency guarantee
is proven for real, not assumed.

What's intentionally excluded from the 100% coverage target
-----------------------------------------------------------------

``.coveragerc`` omits ``src/scrape.py``, ``src/clean.py``, and
``src/llm_hosting/*``. These are Module 2's scraper/cleaner/local-LLM
tooling, reused unchanged here because the Pull Data button still needs
them at runtime -- but driving a real (or even a fully mocked) Selenium
Chrome session to 100% line coverage is out of scope for a module about
pytest and Sphinx, not about re-testing Module 2's scraping code. They are
still fully documented via autodoc (see :doc:`api`) and still run for
real when Pull Data is actually clicked.

Continuous integration
-------------------------

``.github/workflows/tests.yml`` (repository root) runs this exact suite on
every push/PR against a disposable ``postgres:16`` service container, and
uploads the HTML coverage report as a build artifact.
