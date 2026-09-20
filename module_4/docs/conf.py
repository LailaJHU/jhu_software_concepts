"""Sphinx configuration for the Grad Cafe Admissions Analysis project
(JHU EN.605 Software Concepts, Module 4)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# module_4/src must be importable as the "src" package for autodoc to pull
# in real docstrings/signatures from app.py, models.py, etc.
DOCS_DIR = Path(__file__).resolve().parent
MODULE_4_DIR = DOCS_DIR.parent
sys.path.insert(0, str(MODULE_4_DIR))

# Autodoc imports each module, and several of them call load_dotenv() /
# create_engine() at import time. create_engine() never actually connects
# until first used, so this is safe even with no database reachable during
# a documentation build (e.g. on Read the Docs).
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://docs:docs@localhost/docs_build_only")

project = "Grad Cafe Admissions Analysis"
copyright = "2026, Laila Afmeged"
author = "Laila Afmeged"
release = "Module 4"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_mock_imports = ["selenium"]
autodoc_typehints = "description"

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
