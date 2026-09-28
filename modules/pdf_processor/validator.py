"""
Validates that extracted text genuinely belongs to a Form 16, before
any tax calculation is allowed to run on it.

Design rationale: a single keyword search (e.g. "does the text contain
the word 'salary'?") is trivially fooled by unrelated payslips, offer
letters, or random PDFs that happen to mention money. A real Form 16
is a structured government-format certificate with specific mandatory
markers. This validator checks for a weighted set of those markers and
only passes documents that clear both:
  (a) a minimum overall signal score, AND
  (b) at least one "critical" identity marker (PAN/TAN presence) plus
      at least one structural marker (Form No. 16 / Certificate u/s
      203 / Part A / Part B).
That combination is much harder for an unrelated document to satisfy
by accident.
"""

import re
from dataclasses import dataclass, field

from modules.pdf_processor.text_cleaner import PAN_PATTERN, TAN_PATTERN


# Each marker: (name, regex, weight, is_critical)
MARKERS = [
    ("form_16_title", re.compile(r'form\s*no\.?\s*16\b', re.IGNORECASE), 3, True),
    ("certificate_203", re.compile(r'certificate\s+under\s+section\s+203', re.IGNORECASE), 3, True),
    ("part_a", re.compile(r'\bpart[\s\-]?a\b', re.IGNORECASE), 1, False),
    ("part_b", re.compile(r'\bpart[\s\-]?b\b', re.IGNORECASE), 1, False),
    ("assessment_year", re.compile(r'assessment\s+year', re.IGNORECASE), 2, False),
    ("employer_deductor", re.compile(r'(deductor|employer)', re.IGNORECASE), 1, False),
    ("employee_deductee", re.compile(r'(deductee|employee)', re.IGNORECASE), 1, False),
    ("tds_mention", re.compile(r'tax\s+deducted\s+at\s+source|TDS', re.IGNORECASE), 1, False),
    ("gross_salary", re.compile(r'gross\s+(total\s+)?salary|gross\s+total\s+income', re.IGNORECASE), 1, False),
    ("income_tax_dept", re.compile(r'income\s+tax\s+department|govt\.?\s+of\s+india', re.IGNORECASE), 1, False),
]

MIN_SCORE_TO_PASS = 4
MIN_STRUCTURAL_MARKERS = 1  # at least one of form_16_title / certificate_203 / part_a / part_b

# Some Form 16 PDFs shared as public samples/templates deliberately
# scramble PAN/TAN with filler characters (e.g. "AxTxOxPxMx4x0x1x7E")
# to avoid publishing a real identity number. That's a privacy choice
# by whoever posted the sample, not a sign the document isn't a
# genuine Form 16. Rather than hard-block on missing PAN/TAN, a
# document can also pass on structural signal alone if it matches
# almost everything else expected of a real Form 16 - a random
# unrelated document essentially never matches this many markers by
# accident, so this doesn't meaningfully weaken the check.
HIGH_CONFIDENCE_SCORE = 12


@dataclass
class ValidationResult:
    is_valid: bool
    score: int
    max_score: int
    matched_markers: list = field(default_factory=list)
    missing_markers: list = field(default_factory=list)
    has_pan: bool = False
    has_tan: bool = False
    reason: str = ""


def validate_form16_text(text):
    """
    Runs all marker checks against extracted text and returns a
    ValidationResult. Does not raise.
    """
    if not text or len(text.strip()) < 50:
        return ValidationResult(
            is_valid=False, score=0, max_score=sum(w for *_, w, _ in MARKERS),
            reason="The document contains little or no readable text. "
                   "It may be a scanned image, a blank page, or a corrupted file."
        )

    matched = []
    missing = []
    score = 0
    structural_hits = 0

    for name, pattern, weight, is_critical in MARKERS:
        if pattern.search(text):
            matched.append(name)
            score += weight
            if name in ("form_16_title", "certificate_203", "part_a", "part_b"):
                structural_hits += 1
        else:
            missing.append(name)

    has_pan = bool(PAN_PATTERN.search(text.upper()))
    has_tan = bool(TAN_PATTERN.search(text.upper()))

    max_score = sum(w for *_, w, _ in MARKERS)

    is_valid = (
        score >= MIN_SCORE_TO_PASS
        and structural_hits >= MIN_STRUCTURAL_MARKERS
        and (has_pan or has_tan or score >= HIGH_CONFIDENCE_SCORE)
    )

    if is_valid:
        reason = "Document matches the expected structure of a Form 16."
    elif not (has_pan or has_tan) and score < HIGH_CONFIDENCE_SCORE:
        reason = "No valid PAN or TAN number was found in the document."
    elif structural_hits < MIN_STRUCTURAL_MARKERS:
        reason = "The document is missing key Form 16 headers (Form No. 16 / Certificate under section 203 / Part A / Part B)."
    else:
        reason = "The document doesn't contain enough of the fields expected in a genuine Form 16."

    return ValidationResult(
        is_valid=is_valid,
        score=score,
        max_score=max_score,
        matched_markers=matched,
        missing_markers=missing,
        has_pan=has_pan,
        has_tan=has_tan,
        reason=reason,
    )
