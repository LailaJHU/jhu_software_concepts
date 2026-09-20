Overview and Setup
===================

What this project is
---------------------

A small full-stack application over a PostgreSQL database of scraped
Grad Cafe admissions results:

- **PostgreSQL** stores every applicant record in a single ``applicants``
  table (populated in Module 3, reused unchanged here).
- **Flask** (``src/app.py``) serves one page: a live analysis dashboard,
  plus two actions -- *Pull Data* (re-scrapes Grad Cafe for new records)
  and *Update Analysis* (re-runs the queries against whatever is currently
  in the database).
- **SQLAlchemy** (``src/models.py`` / ``src/orm_queries.py``) is the only
  thing the Flask app talks to the database through.
- **Selenium** (``src/scrape.py``) and a small cleaning pass
  (``src/clean.py``) are how new data gets into the database in the first
  place, reused from Module 2 with no behavioral changes.

What's new in Module 4 is not the application's behavior -- it's that the
whole thing is now built to be *tested*: a real dependency-injectable
Flask app factory, a pytest suite with 100% line coverage of the code this
module is actually responsible for, and this documentation site.

Local setup
-----------

1. **PostgreSQL.** Install locally (Postgres.app on macOS is simplest --
   no ``sudo`` needed). Create the database once::

       createdb gradcafe

   (``load_data.py`` creates the ``applicants`` table itself the first
   time it runs.)

2. **Python environment**::

       cd module_4
       python3 -m venv venv
       source venv/bin/activate
       pip install -r requirements.txt

3. **Configuration.** Copy ``.env.example`` to ``.env`` and set
   ``DATABASE_URL`` (or the individual ``DB_HOST`` / ``DB_USER`` / ...
   variables, which are still supported for backward compatibility with
   Module 3's ``.env`` layout). ``.env`` is gitignored and must never be
   committed.

4. **Load the data** (if the database is empty)::

       python -m src.load_data --cleaned cleaned_applicant_data.json --llm llm_extend_applicant_data.json

5. **Run the app**::

       python -m src.app

   then visit ``http://127.0.0.1:8080``.

Project layout
--------------

.. code-block:: text

   module_4/
   |-- src/                    # the application (see architecture.rst)
   |-- tests/                  # the pytest suite (see testing.rst)
   |-- docs/                   # this documentation site
   |-- pytest.ini              # markers + coverage configuration
   |-- .coveragerc             # coverage source/omit configuration
   |-- requirements.txt
   `-- coverage_summary.txt    # a saved terminal run at 100% coverage

See :doc:`architecture` for how the pieces fit together, and
:doc:`testing` for how (and why) the test suite is built the way it is.
