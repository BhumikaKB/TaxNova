"""
Validates an uploaded file BEFORE it's touched by anything else -
PDF parsing, OCR, or the filesystem.

Kept separate from pdf_processor on purpose: this module answers
"is this a safe file to even look at?" while pdf_processor answers
"is this a genuine Form 16?". Mixing those two concerns into one
module makes it easy to accidentally run parsing logic on a file that
should have been rejected outright (e.g. a 400MB upload, or something
that isn't really a PDF despite the .pdf extension).
"""

import os
import uuid
from dataclasses import dataclass
from typing import Optional

from config import Config

ALLOWED_EXTENSIONS = {"pdf"}
PDF_MAGIC_BYTES = b"%PDF-"
MAX_UPLOAD_BYTES = Config.MAX_CONTENT_LENGTH


@dataclass
class UploadCheckResult:
    ok: bool
    reason: Optional[str] = None


def has_allowed_extension(filename):
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def looks_like_real_pdf(file_storage):
    """
    Checks the actual first bytes of the file rather than trusting the
    extension or the browser-supplied MIME type - both are trivial for
    a user (malicious or just confused) to fake by renaming a file.
    Reads a small header chunk only, then rewinds the stream so the
    rest of the pipeline can still read the full file.
    """
    try:
        position = file_storage.stream.tell()
        header = file_storage.stream.read(len(PDF_MAGIC_BYTES))
        file_storage.stream.seek(position)
        return header == PDF_MAGIC_BYTES
    except Exception:
        return False


def get_upload_size(file_storage):
    position = file_storage.stream.tell()
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(position)
    return size


def validate_upload(file_storage, max_bytes=MAX_UPLOAD_BYTES):
    """
    Runs every pre-flight check. Returns UploadCheckResult - never
    raises, so a single bad upload can't take down the request with an
    unhandled exception.
    """
    if file_storage is None or file_storage.filename == "":
        return UploadCheckResult(False, "No file was selected.")

    if not has_allowed_extension(file_storage.filename):
        return UploadCheckResult(False, "Only PDF files are accepted.")

    size = get_upload_size(file_storage)
    if size == 0:
        return UploadCheckResult(False, "The uploaded file is empty.")
    if size > max_bytes:
        mb = max_bytes / (1024 * 1024)
        return UploadCheckResult(False, f"File is too large. Maximum allowed size is {mb:.0f} MB.")

    if not looks_like_real_pdf(file_storage):
        return UploadCheckResult(
            False,
            "This file doesn't look like a genuine PDF (its content doesn't "
            "match the PDF format, even though the filename ends in .pdf)."
        )

    return UploadCheckResult(True)


def build_safe_storage_path(upload_folder, user_id, original_filename):
    """
    Builds a filesystem path that can never collide or escape the
    uploads folder, regardless of what the original filename contains.

    Two protections stacked here:
      1. A UUID replaces the original filename entirely, so path
         traversal sequences (../../etc/passwd) or null-byte tricks in
         the original name never reach the filesystem call.
      2. The user's id is embedded so uploads are trivially traceable
         per-account without needing to trust the original filename
         for anything, including display.
    """
    unique_name = f"user{user_id}_{uuid.uuid4().hex}.pdf"
    return os.path.join(upload_folder, unique_name)
