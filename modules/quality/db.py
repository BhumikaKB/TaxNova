"""
Tracks how often our own extraction was actually right, by comparing
what the regex pipeline read from a PDF against what the user
ultimately confirmed on the review screen.

WHY THIS EXISTS:
"Train a model on our extraction" sounds appealing but has a hard
blocker today: there is no labeled dataset of Form 16s to train on,
and there never ethically will be one scraped from strangers' tax
documents. What we DO have, once this ships, is something better and
completely legitimate - every time a real user corrects a wrong
salary/TDS/employer on the review page, that's a free, ethically
sourced, real-world labeled example: "the model said X, the truth
was Y." This module is what captures that signal instead of throwing
it away the moment the form submits.

This is deliberately NOT training anything yet. It's the data
collection step that has to happen first - a confidence model trained
today would just memorize the handful of sample PDFs used during
development, not generalize to real documents. Revisit this once
there's a meaningful volume of real corrections logged (hundreds, not
a handful) - at that point `get_accuracy_by_field()` below tells you
directly whether there's even a real problem worth training a model
to solve, versus just tuning the existing regex confidence heuristics.
"""

import logging
from modules.auth.db import db_connection

logger = logging.getLogger(__name__)

TRACKED_FIELDS = ["salary", "tds", "employer", "invested_amount"]


def init_feedback_table():
    with db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS extraction_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                extracted_value TEXT,
                extracted_confidence TEXT,
                final_value TEXT,
                was_corrected INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_extraction_feedback_field
            ON extraction_feedback(field_name)
        ''')
        conn.commit()


def _values_differ(extracted, final):
    """
    Loose comparison so a formatting difference (e.g. '800000' vs
    '800000.0') isn't counted as a "correction" when the user didn't
    actually change anything meaningful.
    """
    if extracted is None or extracted == "":
        return final not in (None, "", "0")

    extracted_str = str(extracted).strip().lower()
    final_str = str(final).strip().lower()

    try:
        return float(extracted_str.replace(",", "")) != float(final_str.replace(",", ""))
    except (ValueError, TypeError):
        return extracted_str != final_str


def log_extraction_feedback(user_id, extracted, final):
    """
    Compares each tracked field between what extraction originally
    produced and what the user ultimately confirmed, and logs a row
    per field. Only called when the review came from an actual PDF
    upload (manual entry has no "original" to compare against, so
    there's nothing to learn from there).

    extracted: dict like {"salary": {"value": ..., "confidence": ...}, ...}
    final: dict like {"salary": ..., "tds": ..., ...} (post-user-edit)
    """
    with db_connection() as conn:
        for field_name in TRACKED_FIELDS:
            extracted_info = extracted.get(field_name) or {}
            extracted_value = extracted_info.get("value")
            confidence = extracted_info.get("confidence", "NONE")
            final_value = final.get(field_name)

            corrected = _values_differ(extracted_value, final_value)

            conn.execute('''
                INSERT INTO extraction_feedback
                    (user_id, field_name, extracted_value, extracted_confidence, final_value, was_corrected)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id, field_name,
                str(extracted_value) if extracted_value is not None else None,
                confidence,
                str(final_value) if final_value is not None else None,
                1 if corrected else 0,
            ))
        conn.commit()

    logger.info("Extraction feedback logged for user_id=%s", user_id)


def get_accuracy_by_field():
    """
    Returns {field_name: {"total": N, "corrected": N, "accuracy": 0.0-1.0}}
    - the first real signal for whether extraction is actually
    reliable in practice, versus just in the handful of sample PDFs
    used during development. This is the number to watch before ever
    considering a trained model: if accuracy is already high, there's
    nothing for a model to improve on. If a specific field is
    consistently wrong, that's a concrete, evidence-based reason to
    invest in either better regex patterns or, eventually, a trained
    classifier - not a guess.
    """
    with db_connection() as conn:
        rows = conn.execute('''
            SELECT field_name,
                   COUNT(*) as total,
                   SUM(was_corrected) as corrected
            FROM extraction_feedback
            GROUP BY field_name
        ''').fetchall()

    return {
        row['field_name']: {
            "total": row['total'],
            "corrected": row['corrected'],
            "accuracy": round(1 - (row['corrected'] / row['total']), 3) if row['total'] else None,
        }
        for row in rows
    }
