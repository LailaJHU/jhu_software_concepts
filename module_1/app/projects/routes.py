"""Routes for the Projects page."""

from flask import Blueprint, render_template

projects_bp = Blueprint("projects", __name__)


@projects_bp.route("/projects")
def index():
    """Render the projects page with a list of project entries.

    Each project is a small dictionary so that adding a new project later
    (Module 2, Module 3, ...) is just a matter of appending another dict to
    this list -- no template changes required.
    """

    projects = [
        {
            "title": "Module 1 Assignment: Personal Website",
            "description": (
                "This site itself is the Module 1 project: a personal developer "
                "website built with Flask, using the application factory pattern "
                "and Blueprints to separate the Home, Projects, and Contact pages "
                "into independent modules. Jinja2 templates share a common layout "
                "and navigation bar, and a single stylesheet controls all colors, "
                "spacing, and the two-column bio/photo layout on the homepage."
            ),
            "github_url": "https://github.com/LailaJHU/jhu_software_concepts",
        },
    ]

    return render_template("projects.html", active_page="projects", projects=projects)
