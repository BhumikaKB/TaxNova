"""
OCR fallback path for scanned Form 16 PDFs.

This is deliberately NOT the first thing tried. OCR is slow (seconds
per page) and less accurate than a PDF's real text layer, so the
extractor only calls into this module when direct text extraction
comes back empty/too short - i.e. the PDF is very likely a scanned
image with no embedded text layer.
"""

import logging

logger = logging.getLogger(__name__)

MIN_CHARS_TO_SKIP_OCR = 200  # below this, direct extraction is considered "empty"

MISSING_DEPENDENCY_MESSAGE = (
    "This looks like a scanned Form 16, which needs OCR to read - but the "
    "OCR tools (Tesseract OCR and Poppler) aren't installed on this machine. "
    "These are separate system installs, not something 'pip install' covers. "
    "Install Tesseract OCR and Poppler and add them to your PATH, then try "
    "again, or use 'Enter your details manually' below in the meantime."
)


def needs_ocr(direct_extracted_text):
    return len(direct_extracted_text or "") < MIN_CHARS_TO_SKIP_OCR


def extract_text_via_ocr(pdf_path, max_pages=4, dpi=200):
    """
    Renders PDF pages to images and runs Tesseract OCR on each.
    Capped at max_pages - Form 16 Part A/B is always in the first few
    pages, and OCR-ing an entire large PDF is expensive for no benefit.

    Returns (text, error). error is None on success, or a short
    user-facing message on failure - this function never raises.

    Distinguishes "OCR tools aren't installed" from "this specific
    file is corrupted/blank" - they look similar from the exception
    site but need completely different messages. Telling someone
    their genuine Form 16 is corrupted when the real issue is a
    missing Poppler install on their machine sends them chasing the
    wrong problem.
    """
    try:
        from pdf2image import convert_from_path
        from pdf2image.exceptions import PopplerNotInstalledError, PDFInfoNotInstalledError
        import pytesseract
    except ImportError as e:
        logger.error("OCR dependencies missing: %s", e)
        return "", MISSING_DEPENDENCY_MESSAGE

    try:
        pages = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=max_pages)
    except (PopplerNotInstalledError, PDFInfoNotInstalledError) as e:
        logger.error("Poppler not installed: %s", e)
        return "", MISSING_DEPENDENCY_MESSAGE
    except Exception as e:
        logger.error("PDF-to-image conversion failed: %s", e)
        return "", "Could not read this PDF as an image for OCR. It may be corrupted."

    text_chunks = []
    tesseract_missing = False
    for i, page_image in enumerate(pages):
        try:
            page_text = pytesseract.image_to_string(page_image)
            text_chunks.append(page_text)
        except pytesseract.pytesseract.TesseractNotFoundError as e:
            logger.error("Tesseract not installed: %s", e)
            tesseract_missing = True
            break
        except Exception as e:
            logger.warning("OCR failed on page %d: %s", i + 1, e)
            continue

    if tesseract_missing:
        return "", MISSING_DEPENDENCY_MESSAGE

    combined = "\n".join(text_chunks)

    if len(combined.strip()) < 20:
        return "", "This looks like a scanned document, but OCR could not read any text from it. Try a clearer scan."

    return combined, None
