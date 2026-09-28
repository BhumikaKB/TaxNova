"""
Cleans raw text pulled from a PDF (or OCR) into safe, typed values.

Real Form 16 PDFs produce strings like "₹ 8,00,000.00", "Rs.8,00,000/-",
"8,00,000\\n", or OCR garbage like "8,OO,OOO" (letter O instead of
zero). Every function here is defensive: it never raises, it returns
None (or a sensible default) when a value truly can't be parsed, so a
formatting quirk in one field never crashes the whole request.
"""

import re


def normalize_whitespace(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def clean_currency_to_int(raw_value):
    """
    Turns '₹ 8,00,000.50', 'Rs. 8,00,000/-', '8,00,000' etc. into an
    int (paise/decimals dropped - Form 16 salary figures are whole
    rupees for this app's purposes). Returns None if nothing numeric
    could be salvaged.
    """
    if raw_value is None:
        return None

    text = str(raw_value)

    # Common OCR misreads of digits inside a number-like string.
    ocr_fixes = {'O': '0', 'o': '0', 'l': '1', 'I': '1', 'S': '5'}

    # Only apply OCR character fixes if the string looks numeric-ish
    # (has at least 2 real digits) - otherwise we'd mangle real words.
    digit_count = sum(ch.isdigit() for ch in text)
    if digit_count >= 2:
        text = ''.join(ocr_fixes.get(ch, ch) for ch in text)

    # Strip currency symbols and thousands separators, but handle a
    # trailing decimal portion (paise) explicitly first - stripping
    # '.' as just another separator would concatenate "8,00,000.00"
    # into "80000000" (100x too large) instead of dropping the ".00".
    text = re.sub(r'[₹]|Rs\.?|INR', '', text, flags=re.IGNORECASE)
    text = text.strip()
    text = re.sub(r'\.\d+$', '', text)  # drop trailing .00 / .50 paise portion
    text = re.sub(r'[,/\-\s]', '', text)

    match = re.search(r'\d+', text)
    if not match:
        return None

    try:
        return int(match.group())
    except (ValueError, TypeError):
        return None


def clean_text_field(raw_value, max_length=120):
    """
    Cleans a name/employer/PAN-style text field: collapses whitespace,
    strips stray punctuation from the edges, caps length so a
    mis-matched regex can't dump an entire page into one field.
    """
    if raw_value is None:
        return None

    text = normalize_whitespace(str(raw_value))
    text = text.strip(' :-\u2013\u2014')

    if not text:
        return None

    return text[:max_length]


PAN_PATTERN = re.compile(r'\b[A-Z]{5}[0-9]{4}[A-Z]\b')
TAN_PATTERN = re.compile(r'\b[A-Z]{4}[0-9]{5}[A-Z]\b')


def clean_pan(raw_value):
    if not raw_value:
        return None
    # Deliberately NOT stripping spaces before matching: removing them
    # can merge a preceding label straight into the value (e.g. "PAN "
    # + "ATOPM4017E" -> "PANATOPM4017E"), which destroys the \b word
    # boundary the regex relies on to isolate the actual code.
    match = PAN_PATTERN.search(str(raw_value).upper())
    return match.group() if match else None


def clean_tan(raw_value):
    if not raw_value:
        return None
    match = TAN_PATTERN.search(str(raw_value).upper())
    return match.group() if match else None
