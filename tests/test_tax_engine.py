"""
Unit tests for modules/tax_engine.

Run with:  python -m pytest tests/test_tax_engine.py -v
(or:       python -m unittest tests.test_tax_engine)
"""

import unittest

from modules.tax_engine.old_regime import calculate_old_regime
from modules.tax_engine.new_regime import calculate_new_regime
from modules.tax_engine.tax_compare import compare_tax_regimes
from modules.tax_engine.slab_calculator import compute_slab_tax, apply_rebate_87a


class TestSlabCalculator(unittest.TestCase):

    def test_zero_income_is_zero_tax(self):
        slabs = [(250_000, 0.0), (500_000, 0.05), (None, 0.20)]
        self.assertEqual(compute_slab_tax(0, slabs), 0.0)

    def test_negative_income_is_zero_tax(self):
        slabs = [(250_000, 0.0), (None, 0.20)]
        self.assertEqual(compute_slab_tax(-1000, slabs), 0.0)

    def test_income_within_first_slab(self):
        slabs = [(250_000, 0.0), (500_000, 0.05), (None, 0.20)]
        self.assertEqual(compute_slab_tax(200_000, slabs), 0.0)

    def test_income_spanning_multiple_slabs(self):
        # 0-2.5L @0% + 2.5-5L @5% + remaining @20% on old-regime-style slabs
        slabs = [(250_000, 0.0), (500_000, 0.05), (1_000_000, 0.20), (None, 0.30)]
        # income 700,000 -> 0 + (250k*.05) + (200k*.20) = 12,500 + 40,000 = 52,500
        self.assertAlmostEqual(compute_slab_tax(700_000, slabs), 52_500)

    def test_rebate_87a_zeroes_tax_within_threshold(self):
        config = {"max_taxable_income": 500_000, "max_rebate": 12_500}
        self.assertEqual(apply_rebate_87a(10_000, 480_000, config), 0.0)

    def test_rebate_87a_not_applied_above_threshold_far_out(self):
        config = {"max_taxable_income": 500_000, "max_rebate": 12_500}
        # Income far above threshold and tax far exceeds the excess -> full tax stands
        result = apply_rebate_87a(200_000, 900_000, config)
        self.assertEqual(result, 200_000)

    def test_marginal_relief_just_above_threshold(self):
        config = {"max_taxable_income": 1_200_000, "max_rebate": 60_000}
        # Income is 10,000 over the 12L threshold; relief caps tax at that excess
        result = apply_rebate_87a(61_500, 1_210_000, config)
        self.assertEqual(result, 10_000)


class TestOldRegime(unittest.TestCase):

    def test_income_below_exemption_is_zero(self):
        result = calculate_old_regime(200_000)
        self.assertEqual(result["final_tax"], 0)

    def test_87a_rebate_zeroes_tax_at_5_lakh_taxable(self):
        # 5,00,000 gross - 50,000 standard deduction = 4,50,000 taxable -> well within 87A
        result = calculate_old_regime(500_000)
        self.assertEqual(result["final_tax"], 0)

    def test_breakdown_has_expected_keys(self):
        result = calculate_old_regime(900_000)
        for key in ("regime", "gross_income", "taxable_income", "final_tax"):
            self.assertIn(key, result)
        self.assertEqual(result["regime"], "Old Regime")

    def test_deductions_reduce_tax(self):
        no_deduction = calculate_old_regime(1_000_000, total_deductions=0)
        with_deduction = calculate_old_regime(1_000_000, total_deductions=150_000)
        self.assertLess(with_deduction["final_tax"], no_deduction["final_tax"])


class TestNewRegime(unittest.TestCase):

    def test_income_up_to_12_lakh_taxable_is_zero_after_rebate(self):
        # 12,75,000 gross - 75,000 standard deduction = 12,00,000 taxable -> fully rebated
        result = calculate_new_regime(1_275_000)
        self.assertEqual(result["final_tax"], 0)

    def test_income_above_12_lakh_taxable_has_marginal_relief(self):
        result = calculate_new_regime(1_285_000)  # taxable = 12,10,000
        # Marginal relief caps tax near the 10,000 excess over 12L threshold
        self.assertLessEqual(result["final_tax"], 10_400)  # excess + cess headroom

    def test_high_income_has_no_rebate(self):
        result = calculate_new_regime(2_000_000)
        self.assertGreater(result["final_tax"], 100_000)


class TestCompareTaxRegimes(unittest.TestCase):

    def test_picks_lower_tax_as_winner(self):
        old = calculate_old_regime(1_275_000, total_deductions=0)
        new = calculate_new_regime(1_275_000)
        result = compare_tax_regimes(old, new)
        self.assertEqual(result["best_regime"], "New Regime")
        self.assertGreaterEqual(result["savings"], 0)

    def test_reasoning_is_non_empty_and_mentions_savings(self):
        old = calculate_old_regime(900_000, total_deductions=150_000)
        new = calculate_new_regime(900_000)
        result = compare_tax_regimes(old, new)
        self.assertTrue(len(result["reasoning"]) >= 1)
        self.assertTrue(any("saves" in r.lower() for r in result["reasoning"]))

    def test_tie_does_not_falsely_crown_a_winner(self):
        # Low salary where both regimes legitimately land at ₹0 tax -
        # a real scenario (verified against an actual government
        # Form 16: ₹3,50,000 salary with ₹1,35,000 of 80C deductions).
        old = calculate_old_regime(350_000, total_deductions=135_000)
        new = calculate_new_regime(350_000)
        self.assertEqual(old["final_tax"], new["final_tax"])

        result = compare_tax_regimes(old, new)
        self.assertTrue(result["is_tie"])
        self.assertEqual(result["savings"], 0)
        # Reasoning must NOT claim one regime saves money when it doesn't
        for reason in result["reasoning"]:
            self.assertNotIn("saves ₹0", reason.lower().replace(",", ""))
        self.assertTrue(any("same tax" in r.lower() for r in result["reasoning"]))


if __name__ == "__main__":
    unittest.main()
