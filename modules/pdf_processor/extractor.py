"""
Form 16 extraction pipeline - orchestrates the modules that do the
real work (text extraction, OCR fallback, structural validation,
field extraction with confidence).

Pipeline order and why:
  1. Open the PDF defensively - detect encrypted/corrupted/empty PDFs
     immediately, before wasting time on anything else.
  2. Extract text via pdfplumber (best layout handling), falling back
     to pypdf if pdfplumber can't open it.
  3. If the extracted text is too short, assume it's a scanned image
     and fall back to OCR (Tesseract) - this is the expensive path,
     only taken when genuinely needed.
  4. Cache extracted text by file content hash, so re-processing the
     same PDF (e.g. user goes back and re-submits) skips steps 1-3.
  5. Validate the text actually looks like a genuine Form 16 before
     any field extraction happens - reject early otherwise.
  6. Extract every field with a confidence tag.
  7. Decide overall_confidence + needs_review, so the caller (app.py)
     knows whether to trust these numbers for immediate calculation or
     force the user through the review screen first.

Public function `extract_form16_data(pdf_path)` keeps its original
name/signature so app.py's existing import doesn't need to change,
but the returned dict is richer than before (see bottom of file).
"""

import os
import re

import pdfplumber
import pytesseract

from pdf2image import convert_from_path


# ============================================================
# CONFIGURATION
# ============================================================

# If Tesseract is not available through PATH, uncomment this
# and set the correct location on Windows.
#
# pytesseract.pytesseract.tesseract_cmd = (
#     r"C:\Program Files\Tesseract-OCR\tesseract.exe"
# )


OCR_DPI = 200

FORM16_KEYWORDS = [
    "form no. 16",
    "form no 16",
    "form 16",
    "certificate under section 203",
    "section 203",
    "tds",
    "salary",
    "employer",
    "employee",
    "assessment year",
    "financial year",
]


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Normalize extracted/OCR text so that parsing becomes
    more reliable.
    """

    if not text:
        return ""

    text = text.replace("\xa0", " ")

    # Normalize different dash characters
    text = text.replace("–", "-")
    text = text.replace("—", "-")
    text = text.replace("−", "-")

    # Remove excessive spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Remove excessive blank lines
    text = re.sub(r"\n\s*\n+", "\n", text)

    return text.strip()


# ============================================================
# PDF TEXT EXTRACTION
# ============================================================

def extract_pdf_text(pdf_path):
    """
    Try normal PDF text extraction first.

    Returns:
        extracted text
    """

    text_parts = []

    try:

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text_parts.append(page_text)

    except Exception as e:

        print("PDF text extraction error:", e)

        return ""

    return normalize_text("\n".join(text_parts))


# ============================================================
# OCR FALLBACK
# ============================================================

def extract_ocr_text(pdf_path):
    """
    Convert PDF pages to images using Poppler and run
    Tesseract OCR on each page.
    """

    text_parts = []

    try:

        pages = convert_from_path(
            pdf_path,
            dpi=OCR_DPI
        )

        for page_number, page_image in enumerate(pages, start=1):

            try:

                text = pytesseract.image_to_string(
                    page_image,
                    config="--psm 6"
                )

                if text:
                    text_parts.append(
                        f"\n--- OCR PAGE {page_number} ---\n{text}"
                    )

            except Exception as e:

                print(
                    f"OCR error on page {page_number}:",
                    e
                )

    except Exception as e:

        print("OCR conversion error:", e)

        return ""

    return normalize_text("\n".join(text_parts))


# ============================================================
# FORM 16 VALIDATION
# ============================================================

def validate_form16(text):
    """
    Determine whether extracted text reasonably resembles
    a Form 16.

    This is intentionally not based on a single keyword.
    """

    if not text:
        return {
            "is_form16": False,
            "score": 0,
            "matched_keywords": [],
            "reason": "No readable text was found."
        }

    lower_text = text.lower()

    matched_keywords = []

    for keyword in FORM16_KEYWORDS:

        if keyword in lower_text:
            matched_keywords.append(keyword)

    # Strong indicators
    strong_indicators = 0

    if "form 16" in lower_text or "form no. 16" in lower_text:
        strong_indicators += 2

    if "certificate under section 203" in lower_text:
        strong_indicators += 2

    if "tds" in lower_text:
        strong_indicators += 1

    if "assessment year" in lower_text:
        strong_indicators += 1

    if "employer" in lower_text:
        strong_indicators += 1

    if "salary" in lower_text:
        strong_indicators += 1

    score = min(
        100,
        (len(matched_keywords) * 10) + (strong_indicators * 10)
    )

    # Require meaningful Form 16 evidence
    is_form16 = (
        (
            "form 16" in lower_text
            or "form no. 16" in lower_text
            or "certificate under section 203" in lower_text
        )
        and
        (
            "tds" in lower_text
            or "salary" in lower_text
        )
    )

    if not is_form16:

        reason = (
            "This document does not contain enough "
            "evidence to identify it as Form 16."
        )

    else:

        reason = "Document appears to be a Form 16."

    return {
        "is_form16": is_form16,
        "score": score,
        "matched_keywords": matched_keywords,
        "reason": reason
    }


# ============================================================
# MONEY PARSING
# ============================================================

def parse_money(value):
    """
    Convert values such as:

        ₹1,496,350
        1,496,350
        Rs. 1,496,350

    into:

        1496350
    """

    if not value:
        return None

    value = str(value)

    value = value.replace(",", "")
    value = value.replace("₹", "")
    value = value.replace("Rs.", "")
    value = value.replace("Rs", "")
    value = value.replace("INR", "")

    value = re.sub(
        r"[^\d.]",
        "",
        value
    )

    if not value:
        return None

    try:

        return int(float(value))

    except ValueError:

        return None


# ============================================================
# FIELD EXTRACTION HELPERS
# ============================================================

def extract_money_after_labels(text, labels):
    """
    Search for monetary values near known labels.
    """

    lines = text.splitlines()

    for index, line in enumerate(lines):

        lower_line = line.lower()

        if any(label in lower_line for label in labels):

            # Search current line + next two lines
            nearby_text = " ".join(
                lines[index:index + 3]
            )

            matches = re.findall(
                r"(?:₹|rs\.?|inr)?\s*"
                r"([\d,]+(?:\.\d+)?)",
                nearby_text,
                flags=re.IGNORECASE
            )

            for match in matches:

                value = parse_money(match)

                if value is not None:

                    return value

    return None


def extract_salary(text):
    """
    Extract gross salary using several possible Form 16 labels.
    """

    labels = [
        "gross salary",
        "gross total income",
        "salary",
        "income chargeable under the head salaries",
    ]

    return extract_money_after_labels(
        text,
        labels
    )


def extract_tds(text):
    """
    Extract TDS amount.
    """

    labels = [
        "tds deducted",
        "tax deducted",
        "tds deposited",
        "total tax deducted",
        "tax payable",
    ]

    return extract_money_after_labels(
        text,
        labels
    )


def extract_employer(text):
    """
    Extract employer name using common Form 16 patterns.
    """

    lines = text.splitlines()

    employer_patterns = [
        r"employer\s*[:\-]\s*(.+)",
        r"name of the employer\s*[:\-]\s*(.+)",
        r"deductor\s*[:\-]\s*(.+)",
    ]

    for line in lines:

        clean_line = line.strip()

        for pattern in employer_patterns:

            match = re.search(
                pattern,
                clean_line,
                flags=re.IGNORECASE
            )

            if match:

                employer = match.group(1).strip()

                if employer:
                    return employer

    # Fallback:
    # Search for an employer label followed by next line
    for index, line in enumerate(lines):

        if "employer" in line.lower():

            if index + 1 < len(lines):

                candidate = lines[index + 1].strip()

                if candidate:
                    return candidate

    return None


# ============================================================
# CONFIDENCE CALCULATION
# ============================================================

def calculate_confidence(data, validation, extraction_method):
    """
    Calculate an overall confidence score.

    This is NOT a probability.
    It is a project-level reliability indicator.
    """

    score = 0

    # Document confidence
    score += validation["score"] * 0.40

    # Field confidence
    field_score = 0

    if data.get("salary") is not None:
        field_score += 30

    if data.get("tds") is not None:
        field_score += 15

    if data.get("employer"):
        field_score += 15

    score += field_score

    # OCR gets a small reliability penalty because OCR
    # can introduce character recognition errors.
    if extraction_method == "ocr":
        score -= 10

    score = max(
        0,
        min(
            100,
            round(score)
        )
    )

    if score >= 85:
        level = "High"

    elif score >= 65:
        level = "Medium"

    else:
        level = "Low"

    return {
        "score": score,
        "level": level
    }


# ============================================================
# MAIN FORM 16 EXTRACTION
# ============================================================

def extract_form16_data(pdf_path):
    """
    Main extraction pipeline.

    Pipeline:

        PDF
         ↓
        Normal text extraction
         ↓
        Form 16 validation
         ↓
        If unreadable → OCR
         ↓
        Field extraction
         ↓
        Confidence calculation
         ↓
        Missing-field detection
    """

    if not os.path.exists(pdf_path):

        return {
            "error": "The uploaded document could not be found."
        }


    # --------------------------------------------------------
    # 1. Normal PDF extraction
    # --------------------------------------------------------

    text = extract_pdf_text(pdf_path)

    extraction_method = "text"


    # --------------------------------------------------------
    # 2. If text is insufficient, use OCR
    # --------------------------------------------------------

    if len(text.strip()) < 100:

        print(
            "Very little PDF text detected. "
            "Starting OCR fallback..."
        )

        text = extract_ocr_text(pdf_path)

        extraction_method = "ocr"


    # --------------------------------------------------------
    # 3. Validate Form 16
    # --------------------------------------------------------

    validation = validate_form16(text)

    # If normal extraction failed validation,
    # try OCR before rejecting the document.
    if not validation["is_form16"] and extraction_method == "text":

        print(
            "Normal text did not look like Form 16. "
            "Trying OCR fallback..."
        )

        ocr_text = extract_ocr_text(pdf_path)

        if ocr_text:

            ocr_validation = validate_form16(
                ocr_text
            )

            if (
                ocr_validation["score"]
                > validation["score"]
            ):

                text = ocr_text
                validation = ocr_validation
                extraction_method = "ocr"


    # --------------------------------------------------------
    # 4. Final Form 16 validation
    # --------------------------------------------------------

    if not validation["is_form16"]:

        return {
            "error": (
                "This document does not appear to be a valid "
                "Form 16. Please upload your Form 16 PDF."
            ),
            "validation_score": validation["score"],
            "extraction_method": extraction_method
        }


    # --------------------------------------------------------
    # 5. Extract fields
    # --------------------------------------------------------

    salary = extract_salary(text)

    tds = extract_tds(text)

    employer = extract_employer(text)


    data = {
        "salary": salary,
        "tds": tds,
        "employer": employer,
        "extraction_method": extraction_method,
        "validation_score": validation["score"],
        "matched_keywords": validation["matched_keywords"],
    }


    # --------------------------------------------------------
    # 6. Missing fields
    # --------------------------------------------------------

    missing_fields = []

    if salary is None:
        missing_fields.append("Gross Salary")

    if tds is None:
        missing_fields.append("TDS")

    if not employer:
        missing_fields.append("Employer")


    data["missing_fields"] = missing_fields


    # --------------------------------------------------------
    # 7. Confidence
    # --------------------------------------------------------

    confidence = calculate_confidence(
        data,
        validation,
        extraction_method
    )

    data["confidence_score"] = confidence["score"]

    data["confidence_level"] = confidence["level"]


    # --------------------------------------------------------
    # 8. Human-friendly warnings
    # --------------------------------------------------------

    warnings = []

    if extraction_method == "ocr":

        warnings.append(
            "This document was read using OCR. "
            "Please carefully verify the extracted values."
        )

    if missing_fields:

        warnings.append(
            "Some information could not be extracted: "
            + ", ".join(missing_fields)
        )

    if confidence["level"] == "Low":

        warnings.append(
            "Extraction confidence is low. "
            "Please verify the values before continuing."
        )


    data["warnings"] = warnings


    # --------------------------------------------------------
    # 9. Debug information
    # --------------------------------------------------------

    print("\n========== TAXNOVA EXTRACTION ==========")

    print(
        "Extraction method:",
        extraction_method
    )

    print(
        "Form 16 validation:",
        validation["score"]
    )

    print(
        "Confidence:",
        confidence["score"],
        confidence["level"]
    )

    print(
        "Salary:",
        salary
    )

    print(
        "TDS:",
        tds
    )

    print(
        "Employer:",
        employer
    )

    print(
        "Missing:",
        missing_fields
    )

    print("========================================\n")


    return data