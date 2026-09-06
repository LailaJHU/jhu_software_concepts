====================================================================
 Personal Developer Website - Module 1
 JHU Software Concepts
 Author: Laila Afmeged
====================================================================

OVERVIEW
--------
A small Flask website with three pages:
  - Home     (/)          - name, position, bio, and photo
  - Projects (/projects)  - Module 1 project title, description, GitHub link
  - Contact  (/contact)   - email and LinkedIn

The site uses Flask Blueprints (one blueprint per page, under app/home,
app/contact, app/projects) and Jinja2 templates (app/templates) styled
with a single stylesheet (app/static/css/style.css). A colorized (forest
green) navigation bar appears in the top-right corner of every page, with
the current page highlighted.

REQUIREMENTS
------------
- Python 3.10 or newer
- pip

HOW TO RUN
----------
1. (Recommended) Create and activate a virtual environment:

     python3 -m venv venv
     source venv/bin/activate        (on Windows: venv\Scripts\activate)

2. Install dependencies:

     pip install -r requirements.txt

3. Start the site:

     python run.py

4. Open a browser to:

     http://localhost:8080
     (also reachable at http://0.0.0.0:8080)

   Press CTRL+C in the terminal to stop the server.

PROJECT STRUCTURE
------------------
module_1/
  run.py                  - application entry point ($ python run.py)
  requirements.txt        - pinned dependencies
  README.txt              - this file
  screenshots.pdf         - screenshots of the running site
  app/
    __init__.py           - Flask application factory, registers blueprints
    home/
      routes.py           - "/" route (Home page)
    contact/
      routes.py           - "/contact" route
    projects/
      routes.py           - "/projects" route
    templates/
      base.html           - shared layout + navigation bar
      home.html
      contact.html
      projects.html
    static/
      css/style.css       - all page styling, colors, and layout
      img/profile.jpg     - profile photo shown on the Home page

CUSTOMIZING CONTENT
--------------------
- Home page bio/name/position: edit the variables at the top of
  app/home/routes.py
- Contact info (email/LinkedIn): edit app/contact/routes.py
- Projects list: edit the `projects` list in app/projects/routes.py
  (add another dict to the list for each new module's project)
- Profile photo: replace app/static/img/profile.jpg with your own photo
  (keep the same filename, or update the filename in app/home/routes.py)
- Colors/spacing: edit app/static/css/style.css

NOTES
-----
- This repository is intended to live in a private GitHub repository named
  "jhu_software_concepts", with this project inside a "module_1" folder.
- Screenshots of the three running pages (Home, Projects, Contact) are
  included as screenshots.pdf in this folder.
