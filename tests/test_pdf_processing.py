import io
import unittest
from unittest.mock import MagicMock

from modules.pdf_processor.text_cleaner import (
    clean_currency_to_int, clean_pan, clean_tan, normalize_whitespace,
)
from modules.pdf_processor.validator import validate_form16_text
from modules.pdf_processor.field_extractor import extract_all_fields
from modules.security.file_guard import (
    has_allowed_extension, validate_upload, looks_like_real_pdf,
)


class TestCurrencyCleaning(unittest.TestCase):

    def test_handles_rupee_symbol_and_commas(self):
        self.assertEqual(clean_currency_to_int("₹ 8,00,000.00"), 800000)

    def test_handles_rs_prefix_and_slash_suffix(self):
        self.assertEqual(clean_currency_to_int("Rs.8,00,000/-"), 800000)

    def test_handles_newlines_and_spaces(self):
        self.assertEqual(clean_currency_to_int("8,00,000\n"), 800000)

    def test_handles_plain_int_input(self):
        self.assertEqual(clean_currency_to_int(500000), 500000)

    def test_returns_none_for_garbage(self):
        self.assertIsNone(clean_currency_to_int("Not Found"))

    def test_returns_none_for_none_input(self):
        self.assertIsNone(clean_currency_to_int(None))

    def test_never_raises_on_weird_input(self):
        for junk in ["", "###", "₹₹₹", "-", None, "12abc34"]:
            try:
                clean_currency_to_int(junk)
            except Exception as e:
                self.fail(f"clean_currency_to_int raised on {junk!r}: {e}")


class TestPanTanCleaning(unittest.TestCase):

    def test_valid_pan_extracted(self):
        self.assertEqual(clean_pan("PAN: ATOPM4017E "), "ATOPM4017E")

    def test_invalid_pan_returns_none(self):
        self.assertIsNone(clean_pan("not a pan"))
    def test_valid_tan_extracted(self):
        self.assertEqual(clean_tan("TAN HYDD01619C"), "HYDD01619C")


class TestForm16Validator(unittest.TestCase):

    GENUINE_TEXT = """
        FORM NO. 16
        PART A
        Certificate under Section 203 of the Income-tax Act, 1961
        PAN of the Employee: ATOPM4017E
        TAN of the Deductor: HYDD01619C
        Assessment Year: 2025-26
        Employer: Acme Pvt Ltd
        Gross Salary: 800000
        Tax Deducted at Source: 45000
    """

    def test_genuine_form16_passes(self):
        result = validate_form16_text(self.GENUINE_TEXT)
        self.assertTrue(result.is_valid)

    def test_empty_text_fails(self):
        result = validate_form16_text("")
        self.assertFalse(result.is_valid)

    def test_unrelated_document_fails(self):
        result = validate_form16_text("This is just a random letter about a meeting on Tuesday.")
        self.assertFalse(result.is_valid)

    def test_text_with_form16_words_but_no_pan_tan_fails(self):
        # Should not be fooled by a document that just mentions "Form 16" in passing
        text = "I need to submit my Form 16 for the loan application. Please find attached."
        result = validate_form16_text(text)
        self.assertFalse(result.is_valid)

    def test_masked_pan_tan_still_passes_on_strong_structural_score(self):
        # Real-world case: some publicly-shared Form 16 samples mask
        # PAN/TAN with filler characters for privacy (e.g.
        # "AxTxOxPxMx4x0x1x7E") while everything else about the
        # document is genuinely Form 16-shaped. That's a privacy
        # choice by whoever shared it, not evidence the document isn't
        # a real Form 16.
        text = """
            FORM NO. 16
            PART A
            PART B
            Certificate under Section 203 of the Income-tax Act, 1961
            PAN of the Employee: AxTxOxPxMx4x0x1x7E
            TAN of the Deductor: HxYxDxDx0x1x6x1x9C
            Assessment Year: 2025-26
            Employer Deductor: Acme Pvt Ltd
            Employee Deductee: Jane Doe
            Tax Deducted at Source: 45000
            Gross Salary: 800000
            Income Tax Department, Govt. of India
        """
        result = validate_form16_text(text)
        self.assertTrue(result.is_valid)
        self.assertFalse(result.has_pan)
        self.assertFalse(result.has_tan)


class FakeFileStorage:
    """Minimal stand-in for werkzeug's FileStorage, for testing without Flask."""
    def __init__(self, filename, content):
        self.filename = filename
        self.stream = io.BytesIO(content)


class TestUploadSecurity(unittest.TestCase):

    def test_rejects_non_pdf_extension(self):
        self.assertFalse(has_allowed_extension("form16.exe"))
        self.assertTrue(has_allowed_extension("form16.pdf"))

    def test_rejects_fake_pdf_with_wrong_magic_bytes(self):
        fake = FakeFileStorage("form16.pdf", b"not a real pdf at all")
        result = validate_upload(fake)
        self.assertFalse(result.ok)

    def test_accepts_genuine_pdf_header(self):
        fake = FakeFileStorage("form16.pdf", b"%PDF-1.4\n%fake but has real header\n" + b"x" * 100)
        result = validate_upload(fake)
        self.assertTrue(result.ok)

    def test_rejects_empty_file(self):
        fake = FakeFileStorage("form16.pdf", b"")
        result = validate_upload(fake)
        self.assertFalse(result.ok)

    def test_rejects_oversized_file(self):
        fake = FakeFileStorage("form16.pdf", b"%PDF-1.4" + b"x" * 10)
        result = validate_upload(fake, max_bytes=5)
        self.assertFalse(result.ok)

    def test_rejects_no_file(self):
        result = validate_upload(None)
        self.assertFalse(result.ok)


class TestGrossSalaryExtraction(unittest.TestCase):
    """
    Regression tests for two real bugs found against an actual
    government-issued (TRACES) Form 16 PDF, both stemming from the
    same root cause: a bare number sitting between a label and its
    real value, which the old "skip non-digit characters" gap logic
    couldn't get past.
    """

    def test_line_item_number_does_not_poison_the_match(self):
        # Real excerpt: "3." here is the line's item number, not part
        # of the value. Before the fix, GAP stopped at the "3" and
        # captured it as if it were the salary figure.
        text = (
            "Total amount of salary received from current employer\n"
            "3. 2377833.00\n"
            "[1(d)-2(h)]\n"
        )
        fields = extract_all_fields(text)
        self.assertEqual(fields["gross_salary"].value, 2377833)

    def test_does_not_pick_post_deduction_gross_total_income(self):
        # "Gross total income (6+8)" is a real Form 16 field, but it's
        # computed AFTER Section 10 exemptions and Section 16
        # deductions - feeding it into our own calculator (which
        # subtracts standard deduction again) would double-deduct.
        # The true gross salary label must win instead.
        text = (
            "Salary as per provisions contained in section 17(1) 2557983.00\n"
            "...\n"
            "9. Gross total income (6+8) 2325433.00\n"
        )
        fields = extract_all_fields(text)
        self.assertEqual(fields["gross_salary"].value, 2557983)


class TestOcrErrorPropagation(unittest.TestCase):
    """
    Regression test for a real bug: when Poppler/Tesseract are missing
    (very common on a fresh Windows machine that never separately
    installed these system binaries), OCR correctly detects and
    reports this - but the calling code was discarding that specific
    error and falling through to a generic "document has no readable
    text" message that wrongly implied the PDF itself was broken.
    """

    def test_missing_poppler_error_is_specific_not_generic(self):
        from unittest.mock import patch
        from pdf2image.exceptions import PopplerNotInstalledError
        from modules.pdf_processor.ocr_extractor import extract_text_via_ocr

        with patch('pdf2image.convert_from_path', side_effect=PopplerNotInstalledError("x")):
            text, err = extract_text_via_ocr("uploads/nonexistent.pdf")

        self.assertEqual(text, "")
        self.assertIn("Poppler", err)
        self.assertIn("Tesseract", err)
        self.assertNotIn("corrupted", err.lower())


class TestImplausibleSalaryRejection(unittest.TestCase):
    """
    Regression test for a real bug found against an actual near-blank
    Form 16 template (placeholder text like "<Taxpayer Name>", no real
    filled-in values). Regex extraction still "found" a gross_salary
    of ₹16, scavenged from a stray digit in a label - a value below
    the sanity range gets LOW confidence, but was still being passed
    through as a usable (if flagged) result instead of being treated
    as effectively not-found. No real Indian salary is ₹16.
    """

    def test_implausibly_small_salary_value_falls_below_sanity_floor(self):
        from modules.pdf_processor.field_extractor import extract_all_fields, SANITY_RANGES

        # Same shape of text a scavenged-digit bug produces: a real
        # regex match, but the value itself is nonsense for a salary.
        text = "Gross Salary\n16\n"
        fields = extract_all_fields(text)

        min_plausible, _ = SANITY_RANGES["gross_salary"]
        # This is exactly the condition modules/pdf_processor/extractor.py
        # now checks before accepting a salary value as usable.
        self.assertIsNotNone(fields["gross_salary"].value)
        self.assertLess(fields["gross_salary"].value, min_plausible)


if __name__ == "__main__":
    unittest.main()
