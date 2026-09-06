"""
Entry point for the site.

Run with:

    python run.py

The app will be available at http://localhost:8080 (and on 0.0.0.0:8080, so
it's also reachable from other devices on the network / a VM host).
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # host="0.0.0.0" makes the server reachable via both localhost and any
    # network interface; port=8080 per the assignment requirement.
    app.run(host="0.0.0.0", port=8080, debug=True)
