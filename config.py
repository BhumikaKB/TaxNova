import os
from datetime import timedelta

# Base directory of the project
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """
    Central place for all app-wide settings.

    Why this file exists:
    Hardcoding secret keys, folder paths, and limits directly inside
    app.py makes them easy to forget about and hard to change per
    environment (dev vs production). Keeping them here means changing
    a limit or key is a one-line edit, not a hunt through app.py.
    """

    # Debug mode is OFF by default and only turns on via an explicit
    # environment variable - never hardcoded True. Flask's debug mode
    # exposes the Werkzeug interactive debugger, which allows remote
    # code execution if it's ever reachable outside localhost. Treat
    # this as something that should be structurally hard to leave on
    # by accident, not just a convention to remember.
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # Secret key is read from an environment variable first so it is
    # never committed to source control. Falls back to a dev-only key
    # so the app still runs locally without extra setup.
    SECRET_KEY = os.environ.get('TAXNOVA_SECRET_KEY', 'dev-only-not-for-production')

    # A session that never expires means a logged-in browser (e.g. a
    # shared or public computer) stays logged in forever. 7 days
    # balances real convenience against that risk; "Remember me"
    # unchecked on login uses a browser-session-only cookie instead.
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Only send the session cookie over HTTPS once deployed behind
    # TLS. Forced off in local dev (no HTTPS on localhost) via the
    # same FLASK_DEBUG-style env convention, so this doesn't need
    # manual toggling per environment.
    SESSION_COOKIE_SECURE = os.environ.get('TAXNOVA_HTTPS', 'False').lower() == 'true'

    # CSRF tokens don't expire mid-session - a token becoming invalid
    # while someone is mid-way through filling out the review form
    # (which can take a while if they're editing several fields) would
    # be a confusing, unnecessary failure.
    WTF_CSRF_TIME_LIMIT = None

    # --- Uploads ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    ALLOWED_EXTENSIONS = {'pdf'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload size

    # --- Database ---
    DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'database.db')

    # --- Tax engine (moved here in a later step so slabs aren't
    # buried inside calculation logic) ---
    MAX_80C_LIMIT = 150000

    # Bump this string on every deploy/update. It's appended as a
    # query string to CSS/JS URLs so browsers fetch the new file
    # instead of serving a stale cached copy under the old filename -
    # otherwise someone who replaces their code can keep seeing an
    # old cached design-system.css indefinitely.
    ASSET_VERSION = "2026-07-19-6"
