"""Routes for the Home / About page."""

from flask import Blueprint, render_template

# "home_bp" is this page's Blueprint. Registering it in app/__init__.py wires
# these routes into the main Flask app.
home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    """Render the homepage: name, position, bio, and photo."""

    # All of the homepage's content lives here as simple variables so it's
    # easy to find and edit without touching the template's HTML structure.
    name = "Laila Afmeged"
    position = "Associate Data Scientist, Defense Contractor  |  M.S. Data Science Candidate, Johns Hopkins University"
    bio = (
        "I'm an Associate Data Scientist at a defense contractor, where I support "
        "microelectronic devices and superconducting chip programs, building ETL "
        "pipelines, anomaly and failure detection tools, and dashboards that turn "
        "raw operational data into decisions. I hold a Bachelor's degree in Cloud "
        "Computing from Morgan State University, and I'm currently pursuing a "
        "Master's degree in Data Science with a concentration in AI and Machine "
        "Learning at Johns Hopkins University. This site tracks the Python "
        "projects I build throughout my coursework, starting with the project "
        "below from Module 1."
    )
    photo_filename = "profile.jpg"

    return render_template(
        "home.html",
        active_page="home",
        name=name,
        position=position,
        bio=bio,
        photo_filename=photo_filename,
    )
