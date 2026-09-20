Architecture
============

Request flow
-------------

.. code-block:: text

   Browser
     |
     |  GET /
     v
   Flask app (src/app.py, create_app())
     |
     |  GET_ANALYSIS_RESULTS_FN()
     v
   src/orm_queries.py  --(SQLAlchemy Session)-->  src/models.py  --> PostgreSQL
                                                      (Applicant)

   Browser
     |
     |  POST /pull-data           POST /update-analysis
     v                              v
   IS_PULL_RUNNING_FN() ?          IS_PULL_RUNNING_FN() ?
     | no                            | no
     v                                v
   START_PULL_FN()                  GET_ANALYSIS_RESULTS_FN()
     |
     v
   src/pull_data_pipeline.py
     scrape.py -> clean.py -> load_data.py  (subprocess chain, real usage)

The dependency-injection seam
------------------------------

:func:`src.app.create_app` never hardwires a database connection or a
scraper into the Flask routes. Every route reads exactly four things out
of ``app.config``:

- ``GET_ANALYSIS_RESULTS_FN`` -- how to get the current analysis results.
- ``START_PULL_FN`` -- how to kick off a Pull Data run.
- ``IS_PULL_RUNNING_FN`` -- whether a pull is currently in progress.
- ``GET_PULL_STATUS_FN`` -- the last-known status message.

Left unset, ``create_app()`` wires these to the real implementations: a
live SQLAlchemy query (:func:`src.app.get_analysis_results`) and a
subprocess-based pull runner (``_SubprocessPullRunner``) that reproduces
Module 3's behavior exactly -- launch ``pull_data_pipeline.py`` in the
background, track it via a status file so state survives a Flask restart.

The test suite instead passes plain Python callables/fakes for one or more
of these four hooks (see :doc:`testing`), which is what lets the whole
route layer -- including the Pull Data / Update Analysis busy-state gating
-- be tested through nothing but ``app.test_client()``, with no real
database, subprocess, or network call anywhere in the ``web`` / ``buttons``
/ ``analysis`` test files.

The Pull Data pipeline
------------------------

:func:`src.pull_data_pipeline.run_pipeline` takes a list of
:class:`~src.pull_data_pipeline.PipelineStep` -- a label plus a
zero-argument callable -- and runs them in order, writing a status file
after each one, stopping at the first failure. The real pipeline's three
steps (:func:`src.pull_data_pipeline.default_steps`) shell out to
``scrape.py``, ``clean.py``, and ``load_data.py`` exactly as Module 3 did;
the ``integration`` tests instead pass three fake steps to verify the
sequencing/error-handling logic in isolation.

Data layer
----------

``applicants`` is a single flat table (schema in
:data:`src.load_data.SCHEMA_SQL`), with ``url`` as the natural unique key.
Every insert path -- the original bulk load and every subsequent Pull Data
run -- goes through the same ``ON CONFLICT (url) DO NOTHING`` insert, so
running the loader (or clicking Pull Data) twice is always safe: a
:doc:`testing`-covered property (``test_load_is_idempotent_on_conflict_url``).

Two ways of querying the same table exist side by side, carried over from
Module 3's Parts 2 and 6:

- **Raw SQL** (:mod:`src.query_data`) -- direct ``psycopg`` execution.
- **SQLAlchemy ORM** (:mod:`src.orm_queries`) -- ``select()`` / ``where()``
  against the :class:`src.models.Applicant` model. This is the version the
  Flask app actually uses.
