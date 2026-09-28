import unittest
from modules.quality.db import _values_differ


class TestValuesDiffer(unittest.TestCase):

    def test_identical_numbers_not_flagged_as_corrected(self):
        self.assertFalse(_values_differ("800000", "800000"))

    def test_formatting_difference_not_flagged(self):
        # "800000" vs "800000.0" is the same value, just formatted
        # differently - shouldn't count as the user correcting anything.
        self.assertFalse(_values_differ("800000", "800000.0"))

    def test_comma_formatted_number_not_flagged(self):
        self.assertFalse(_values_differ("8,00,000", "800000"))

    def test_genuinely_different_numbers_flagged(self):
        self.assertTrue(_values_differ("800000", "850000"))

    def test_none_original_with_real_final_is_flagged(self):
        # Extraction found nothing (None), user typed in a real value -
        # that's a correction (extraction should have found it).
        self.assertTrue(_values_differ(None, "800000"))

    def test_none_original_with_empty_final_not_flagged(self):
        # Extraction found nothing, user also left it at 0/empty -
        # not a meaningful correction.
        self.assertFalse(_values_differ(None, "0"))
        self.assertFalse(_values_differ("", ""))

    def test_text_field_comparison_case_insensitive(self):
        self.assertFalse(_values_differ("Acme Corp", "acme corp"))
        self.assertTrue(_values_differ("Acme Corp", "Infosys"))


if __name__ == "__main__":
    unittest.main()
