"""
Application factory for the personal developer website.

Using the "application factory" pattern (create_app) plus Blueprints lets us
split the site into independent, self-contained page modules (home, contact,
projects) instead of cramming every route into one file. Each blueprint owns
its own routes.py and can later grow its own templates/static files if the
site gets bigger.
"""

from flask import Flask


def create_app():
    """Build and configure the Flask application.

    Returns:
        Flask: a fully configured Flask app instance, ready to run.
    """
    # template_folder / static_folder are relative to this file (app/),
    # so app/templates and app/static are picked up automatically.
    app = Flask(__name__)

    # --- Register blueprints -------------------------------------------------
    # Each blueprint represents one page (or group of pages) of the site.
    from app.home.routes import home_bp
    from app.contact.routes import contact_bp
    from app.projects.routes import projects_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(contact_bp)
    app.register_blueprint(projects_bp)

    return app
