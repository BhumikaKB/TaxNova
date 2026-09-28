import sqlite3
import os
import logging
from contextlib import contextmanager
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

logger = logging.getLogger(__name__)


def get_connection():
    """
    Opens a new SQLite connection.

    A fresh connection per call (instead of one shared global connection)
    avoids the classic Flask + SQLite bug where requests handled on
    different threads crash because a connection was created on a
    different thread than the one using it.
    """
    os.makedirs(os.path.dirname(Config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    # SQLite does not enforce FOREIGN KEY constraints unless this is
    # set on every connection - without it, the FOREIGN KEY
    # declarations below are purely decorative and a calculations/
    # password_resets row could silently reference a user_id that
    # doesn't exist.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_connection():
    """
    Guarantees the connection is closed even if the query raises.

    The previous pattern here was manual `conn = get_connection()` ...
    `conn.close()` at the end of each function. If the query itself
    raised (locked database, disk full, malformed SQL), close() never
    ran and the connection leaked. Under real concurrent load this
    exhausts available connections over time - exactly the kind of
    bug that's invisible in manual testing and shows up as
    intermittent failures in production. Every function below now
    goes through this instead of managing conn.close() by hand.
    """
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """
    Creates the users table if it doesn't already exist.

    Also handles migrating away from the old schema (which had a plain
    'password' column instead of 'password_hash') if an older copy of
    the database is present. Since that table was never actually
    written to by the old app.py (register() only printed values), it
    is safe to drop and recreate rather than write a full migration.
    """
    with db_connection() as conn:
        existing_columns = {
            row['name'] for row in
            conn.execute("PRAGMA table_info(users)").fetchall()
        }

        if existing_columns and 'password_hash' not in existing_columns:
            conn.execute('DROP TABLE users')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS password_resets (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        conn.commit()
        logger.info("Database tables verified/created.")


def create_password_reset_token(email, lifetime_minutes=30):
    """
    Returns a fresh reset token for the given email, or None if no
    account exists with that email. Deliberately doesn't distinguish
    "no such account" from "token created" in what's shown to the
    user afterward (the caller should show the same generic message
    either way) - confirming which emails are registered is a real
    account-enumeration risk otherwise.
    """
    import secrets
    from datetime import datetime, timedelta

    user = get_user_by_email(email)
    if user is None:
        return None

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=lifetime_minutes)

    with db_connection() as conn:
        conn.execute(
            'INSERT INTO password_resets (token, user_id, expires_at) VALUES (?, ?, ?)',
            (token, user['id'], expires_at)
        )
        conn.commit()

    logger.info("Password reset token issued for user_id=%s", user['id'])
    return token


def verify_reset_token(token):
    """Returns the user row for a valid, unused, unexpired token - else None."""
    from datetime import datetime

    with db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM password_resets WHERE token = ? AND used = 0',
            (token,)
        ).fetchone()

        if row is None:
            return None

        if datetime.fromisoformat(row['expires_at']) < datetime.utcnow():
            return None

        return conn.execute('SELECT * FROM users WHERE id = ?', (row['user_id'],)).fetchone()


def reset_password_with_token(token, new_password):
    """Sets a new password and burns the token. Returns True if it succeeded."""
    user = verify_reset_token(token)
    if user is None:
        return False

    with db_connection() as conn:
        password_hash = generate_password_hash(new_password)
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user['id']))
        conn.execute('UPDATE password_resets SET used = 1 WHERE token = ?', (token,))
        conn.commit()

    logger.info("Password reset completed for user_id=%s", user['id'])
    return True


def create_user(name, email, password):
    """
    Inserts a new user with a hashed password.
    Returns (success: bool, message: str).
    """
    with db_connection() as conn:
        try:
            password_hash = generate_password_hash(password)
            conn.execute(
                'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                (name, email.lower().strip(), password_hash)
            )
            conn.commit()
            logger.info("New user registered: %s", email.lower().strip())
            return True, "Account created successfully."
        except sqlite3.IntegrityError:
            # UNIQUE constraint on email failed
            return False, "An account with this email already exists."


def get_user_by_email(email):
    with db_connection() as conn:
        return conn.execute(
            'SELECT * FROM users WHERE email = ?',
            (email.lower().strip(),)
        ).fetchone()


def verify_user(email, password):
    """
    Checks credentials.
    Returns the user row if valid, otherwise None.
    """
    user = get_user_by_email(email)
    if user is None:
        return None
    if check_password_hash(user['password_hash'], password):
        return user
    return None
