"""
Stores each completed tax calculation so a user can see their history
instead of the result disappearing the moment they navigate away.

Kept as its own module (not bolted onto modules/auth/db.py) because it's
a different concern: auth is about who you are, this is about what
you've calculated. Reuses the same SQLite connection helper so there's
one place that knows how to open the database.
"""

import logging
from modules.auth.db import db_connection

logger = logging.getLogger(__name__)


def init_history_table():
    with db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                employer TEXT,
                salary INTEGER NOT NULL,
                tds INTEGER,
                invested_amount INTEGER,
                old_tax INTEGER,
                new_tax INTEGER,
                best_regime TEXT,
                savings INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # Every history/dashboard query filters on user_id - without
        # this index it's a full table scan on every request once the
        # table has any real volume of rows.
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_calculations_user_id
            ON calculations(user_id)
        ''')
        conn.commit()


def save_calculation(user_id, employer, salary, tds, invested_amount,
                      old_tax, new_tax, best_regime, savings):
    with db_connection() as conn:
        conn.execute('''
            INSERT INTO calculations
                (user_id, employer, salary, tds, invested_amount, old_tax, new_tax, best_regime, savings)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, employer, salary, tds, invested_amount, old_tax, new_tax, best_regime, savings))
        conn.commit()
    logger.info("Calculation saved for user_id=%s, best_regime=%s", user_id, best_regime)


def get_history_for_user(user_id, limit=25):
    with db_connection() as conn:
        return conn.execute('''
            SELECT * FROM calculations
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()


def get_latest_for_user(user_id):
    with db_connection() as conn:
        return conn.execute('''
            SELECT * FROM calculations
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        ''', (user_id,)).fetchone()
