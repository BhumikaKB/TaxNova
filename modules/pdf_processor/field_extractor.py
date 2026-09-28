"""
Extracts individual Form 16 fields from raw text, each tagged with a
confidence level.

WHY CONFIDENCE SCORING EXISTS (mentor requirement):
A regex match is not the same as a correct value. Two-column PDF
layouts, OCR noise, and employer-specific formatting can all produce
a match that looks plausible but is wrong or incomplete. Rather than
silently feeding a possibly-wrong number into a tax calculation, every
field here comes back with a confidence tag:

    HIGH   - matched a well-anchored label AND passed a sanity check
             (e.g. PAN matches the exact 10-char format, salary is a
             plausible positive number)
    MEDIUM - matched a looser/fallback pattern, or passed extraction
             but failed a secondary sanity check
    LOW    - a value was found but looks suspicious (e.g. absurdly
             small/large, or came from a weak generic pattern)
    NONE   - nothing matched; value is None

The extractor.py orchestrator uses these to decide whether to
auto-proceed to tax calculation or force the user to review the
review.html form before anything is calculated.
"""

import re
from dataclasses import dataclass
from typing import Optional

from modules.pdf_processor.text_cleaner import (
    clean_currency_to_int, clean_text_field, clean_pan, clean_tan,
)

HIGH, MEDIUM, LOW, NONE = "HIGH", "MEDIUM", "LOW", "NONE"


@dataclass
class ExtractedField:
    value: Optional[object]
    confidence: str
    raw_match: Optional[str] = None


def _first_match(text, patterns):
    """Tries each regex in order, returns (match_text, pattern_index) for the first hit."""
    for i, pattern in enumerate(patterns):
        m = pattern.search(text)
        if m:
            return (m.group(1) if m.groups() else m.group(0)), i
    return None, None


# ---------------- Identity fields ---------------- #

PAN_LABELED = re.compile(
    r'PAN\s+of\s+the\s+Employee[^\n]{0,60}?([A-Z]{5}[0-9]{4}[A-Z])', re.IGNORECASE
)
PAN_GENERIC = re.compile(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b')

TAN_LABELED = re.compile(
    r'TAN\s+of\s+the\s+Deductor[^\n]{0,60}?([A-Z]{4}[0-9]{5}[A-Z])', re.IGNORECASE
)
TAN_GENERIC = re.compile(r'\b([A-Z]{4}[0-9]{5}[A-Z])\b')

ASSESSMENT_YEAR = re.compile(r'Assessment\s+Year[:\s]*?(\d{4}[-–]\d{2,4})', re.IGNORECASE)
FINANCIAL_YEAR = re.compile(r'Financial\s+Year[:\s]*?(\d{4}[-–]\d{2,4})', re.IGNORECASE)

EMPLOYER_NAME = re.compile(
    r'Name\s+and\s+address\s+of\s+the\s+Employer[^\n]*\n([A-Z][A-Za-z0-9 &.,\'\-]{3,80})',
    re.IGNORECASE
)

# ---------------- Money fields (label variants seen across Tally / SAP / HRMS / govt exports) ---------------- #
#
# GAP is the regex fragment used between a label and its value. It is
# deliberately NOT a simple "any non-digit character" class, because
# real Form 16 Part B is full of formula references that contain
# digits right next to the label - e.g. "Gross total income (6+8)",
# "Total taxable income (9-11)", "Tax payable (13+15+16-14)",
# "[10(d)+10(e)+10(f)+10(g)...]". A naive [^\d]{0,20} gap stops the
# instant it hits the "6" in "(6+8)" and then happily matches that "6"
# as if it were the real value - which is exactly how a real upload
# of a genuine government-issued Form 16 previously produced a "gross
# salary" of ₹6. GAP treats an entire (...) or [...] group as one
# skippable unit, digits and all, so the match lands on the real
# trailing number instead.
GAP = r'(?:\[[^\]\n]{0,80}\]|\([^)\n]{0,80}\)|\d{1,2}\.\s+|[^\d₹]){0,40}'

MONEY_FIELDS = {
    "gross_salary": [
        # Most specific / most reliable first - these are fixed-wording
        # line items in the government TRACES-generated Part B, not
        # loose keyword guesses.
        #
        # "Salary as per provisions contained in section 17(1)" (the
        # raw, pre-exemption figure) is prioritized over "Total amount
        # of salary received from current employer [1(d)-2(h)]" (which
        # has already had Section 10 exemptions like HRA subtracted).
        # Our calculator applies one gross-salary figure uniformly to
        # BOTH regimes, but New Regime doesn't legally allow most
        # Section 10 exemptions - feeding it the already-HRA-reduced
        # figure would silently understate New Regime tax and could
        # steer someone toward the wrong regime. The raw figure instead
        # slightly overstates Old Regime tax (HRA isn't modeled yet,
        # a documented limitation) - overstating is the safer direction
        # of error than understating what's actually owed.
        #
        # Deliberately does NOT include "Gross Total Income" or "Total
        # Income" - those are computed even later (line 9, after BOTH
        # Section 10 exemptions AND Section 16 deductions), which would
        # make our calculator double-subtract standard deduction.
        re.compile(r'Salary\s+as\s+per\s+provisions\s+contained\s+in\s+section\s+17' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Total\s+amount\s+of\s+salary\s+received\s+from\s+current\s+employer' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Gross\s+Salary' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "basic_salary": [
        re.compile(r'Basic\s+Salary' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'\bBasic' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "hra": [
        re.compile(r'House\s+[Rr]ent\s+[Aa]llowance' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'\bHRA\b' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "special_allowance": [
        re.compile(r'Special\s+Allowance' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "professional_tax": [
        re.compile(r'Professional\s+Tax' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Tax\s+on\s+[Ee]mployment' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "standard_deduction": [
        re.compile(r'Standard\s+deduction\s+under\s+section\s+16' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Standard\s+Deduction' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "section_80c": [
        # Handles a real, recurring PDF-extraction quirk: when a wrapped
        # label breaks across a row/column boundary, pdfplumber can
        # emit the row's number BEFORE the tail end of its own label
        # text - e.g. "...contributions to\n(a) 135000.00\nprovident
        # fund etc. under section 80C". A forward-only "label -> value"
        # search misses this because the value already went by. This
        # pattern looks for the number immediately preceding the
        # standard fixed closing phrase instead.
        re.compile(r'([\d,]+(?:\.\d+)?)\s*\n?\s*provident\s+fund\s+etc\.?\s*under\s+section\s+80C', re.IGNORECASE),
        re.compile(r'life\s+insurance\s+premia.{0,150}?under\s+section\s+80C' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE | re.DOTALL),
        re.compile(r'Total\s+deduction\s+under\s+section\s+80C,?\s*80CCC\s+and\s+80CCD\(1\)' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'(?:Section\s+)?80\s*C\b(?!\s*,)' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "section_80d": [
        re.compile(r'health\s+insurance\s+premia\s+under\s+section\s+80D' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'(?:Section\s+)?80\s*D\b' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "taxable_income": [
        re.compile(r'Total\s+taxable\s+income' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Taxable\s+Income' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
    "tds": [
        # The Verification paragraph's fixed wording ("a sum of Rs. X
        # ... has been deducted") is present on virtually every
        # TRACES-generated Form 16 Part A and is far less ambiguous
        # than hunting through the quarterly summary table.
        re.compile(r'sum\s+of\s+Rs\.?\s*([\d,]+(?:\.\d+)?)\s*\[Rs\.[^\]]*?\]\s*has\s+been\s+deducted', re.IGNORECASE),
        re.compile(r'Tax\s+Deducted\s+at\s+Source' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'\bTDS\b' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        # Quarterly summary "Total (Rs.)" row has three numbers in a
        # row: amount paid/credited, tax deducted, tax deposited - the
        # middle one is what we want.
        re.compile(r'Total\s*\(Rs\.?\)\s*[\d,]+(?:\.\d+)?\s+([\d,]+(?:\.\d+)?)\s+[\d,]+(?:\.\d+)?', re.IGNORECASE),
    ],
    "net_tax": [
        re.compile(r'Net\s+[Tt]ax\s+[Pp]ayable' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
        re.compile(r'Total\s+[Tt]ax\s+[Pp]ayable' + GAP + r'([\d,]+(?:\.\d+)?)', re.IGNORECASE),
    ],
}

# Sanity ranges used to downgrade confidence on implausible numbers
# (e.g. a mis-anchored regex grabbing a page number or a year).
SANITY_RANGES = {
    "gross_salary": (10_000, 100_000_000),
    "basic_salary": (5_000, 60_000_000),
    "hra": (0, 40_000_000),
    "special_allowance": (0, 40_000_000),
    "professional_tax": (0, 5_000),
    "standard_deduction": (0, 100_000),
    "section_80c": (0, 150_000),
    "section_80d": (0, 100_000),
    "taxable_income": (0, 100_000_000),
    "tds": (0, 50_000_000),
    "net_tax": (0, 50_000_000),
}


def _extract_money_field(field_name, text):
    patterns = MONEY_FIELDS[field_name]
    low, high = SANITY_RANGES.get(field_name, (0, float("inf")))

    candidates = []  # (value, pattern_index, raw_text)
    for i, pattern in enumerate(patterns):
        for m in pattern.finditer(text):
            raw = m.group(1) if m.groups() else m.group(0)
            value = clean_currency_to_int(raw)
            if value is not None:
                candidates.append((value, i, raw))

    if not candidates:
        return ExtractedField(value=None, confidence=NONE)

    in_range = [c for c in candidates if low <= c[0] <= high]
    pool = in_range or candidates

    # Cross-validation: if two DIFFERENT patterns (not just two hits of
    # the same one) independently agree on the same value, that's a
    # real signal the number is correct - not just that one regex
    # happened to fire twice. This is worth more than "which pattern
    # was listed first."
    value_to_pattern_indexes = {}
    for value, idx, _raw in pool:
        value_to_pattern_indexes.setdefault(value, set()).add(idx)

    cross_validated = [v for v, idxs in value_to_pattern_indexes.items() if len(idxs) >= 2]
    if cross_validated and in_range:
        chosen = cross_validated[0]
        return ExtractedField(value=chosen, confidence=HIGH, raw_match=str(chosen))

    # No cross-validation - fall back to the first in-range match,
    # weighted by how specific/reliable its pattern was (earlier in
    # the list = more specific label match, per field definitions above).
    best = min(pool, key=lambda c: c[1])
    value, pattern_index, raw = best

    if not in_range:
        return ExtractedField(value=value, confidence=LOW, raw_match=raw)
    if pattern_index == 0:
        return ExtractedField(value=value, confidence=HIGH, raw_match=raw)
    return ExtractedField(value=value, confidence=MEDIUM, raw_match=raw)


def extract_all_fields(text):
    """
    Runs every field extractor against the given text and returns a
    dict of field_name -> ExtractedField. Never raises - a field that
    can't be found simply comes back as NONE confidence with value None,
    which the caller (extractor.py) uses to decide whether to force a
    manual review.
    """
    fields = {}

    # --- Identity fields ---
    pan_raw, pan_idx = _first_match(text, [PAN_LABELED, PAN_GENERIC])
    pan_value = clean_pan(pan_raw) if pan_raw else None
    fields["pan"] = ExtractedField(
        value=pan_value,
        confidence=(HIGH if pan_value and pan_idx == 0 else MEDIUM if pan_value else NONE),
        raw_match=pan_raw,
    )

    tan_raw, tan_idx = _first_match(text, [TAN_LABELED, TAN_GENERIC])
    tan_value = clean_tan(tan_raw) if tan_raw else None
    fields["tan"] = ExtractedField(
        value=tan_value,
        confidence=(HIGH if tan_value and tan_idx == 0 else MEDIUM if tan_value else NONE),
        raw_match=tan_raw,
    )

    ay_raw, _ = _first_match(text, [ASSESSMENT_YEAR])
    fields["assessment_year"] = ExtractedField(
        value=clean_text_field(ay_raw, max_length=12) if ay_raw else None,
        confidence=HIGH if ay_raw else NONE,
        raw_match=ay_raw,
    )

    fy_raw, _ = _first_match(text, [FINANCIAL_YEAR])
    fields["financial_year"] = ExtractedField(
        value=clean_text_field(fy_raw, max_length=12) if fy_raw else None,
        confidence=HIGH if fy_raw else NONE,
        raw_match=fy_raw,
    )

    employer_raw, _ = _first_match(text, [EMPLOYER_NAME])
    employer_value = clean_text_field(employer_raw) if employer_raw else None
    # Employer/employee names sit in the part of a Form 16 most prone
    # to two-column text jumbling - never mark this HIGH confidence
    # even on a match, so the UI always invites a quick human check.
    fields["employer_name"] = ExtractedField(
        value=employer_value,
        confidence=MEDIUM if employer_value else NONE,
        raw_match=employer_raw,
    )

    # --- Money fields ---
    for field_name in MONEY_FIELDS:
        fields[field_name] = _extract_money_field(field_name, text)

    return fields


def overall_confidence(fields):
    """
    Rolls per-field confidence up into one overall signal, keyed off
    the fields tax calculation actually depends on: gross_salary and
    tds. Everything else informs the UI but isn't calculation-critical.
    """
    critical = [fields.get("gross_salary"), fields.get("tds")]

    if any(f is None or f.confidence == NONE for f in critical):
        return NONE
    if any(f.confidence == LOW for f in critical):
        return LOW
    if any(f.confidence == MEDIUM for f in critical):
        return MEDIUM
    return HIGH
