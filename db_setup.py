"""
Standalone helper to (re)initialize the database.

This is no longer required for the app to run - app.py calls
init_db() automatically on startup. Kept as a convenience script for
manually resetting/inspecting the database during development:

    python db_setup.py
"""

from modules.auth.db import init_db

if __name__ == '__main__':
    init_db()
    print("Database and 'users' table are ready (database/database.db).")
