"""Routes for the Contact page."""

from flask import Blueprint, render_template

contact_bp = Blueprint("contact", __name__)


@contact_bp.route("/contact")
def index():
    """Render the contact page: email and LinkedIn."""

    email = "lafmeged01@gmail.com"
    linkedin_url = "https://www.linkedin.com/in/laila-a-023332226"
    linkedin_display = "linkedin.com/in/laila-a-023332226"

    return render_template(
        "contact.html",
        active_page="contact",
        email=email,
        linkedin_url=linkedin_url,
        linkedin_display=linkedin_display,
    )
