"""
Old Regime tax calculation (Section 115BAC opt-out).

Applies: standard deduction -> Chapter VI-A deductions (80C, 80D, etc.)
-> slab tax -> Section 87A rebate (with marginal relief) -> 4% cess.
"""

from modules.tax_engine.constants import OLD_REGIME, CESS_RATE
from modules.tax_engine.slab_calculator import (
    compute_slab_tax, apply_rebate_87a, apply_cess, round_tax
)


def calculate_old_regime(gross_income, total_deductions=0):
    """
    gross_income: gross salary before any deductions.
    total_deductions: sum of all Chapter VI-A deductions the taxpayer
        is claiming (80C + 80D + others). Standard deduction is
        applied separately/automatically and should NOT be included
        here.

    Returns a breakdown dict (not just a number) so the UI and the
    recommendation engine can explain *how* the figure was reached.
    """
    standard_deduction = OLD_REGIME["standard_deduction"]

    taxable_income = max(
        gross_income - standard_deduction - total_deductions, 0
    )

    tax_before_rebate = compute_slab_tax(taxable_income, OLD_REGIME["slabs"])
    tax_after_rebate = apply_rebate_87a(
        tax_before_rebate, taxable_income, OLD_REGIME["rebate_87a"]
    )
    tax_with_cess = apply_cess(tax_after_rebate, CESS_RATE)
    final_tax = round_tax(tax_with_cess)

    return {
        "regime": "Old Regime",
        "gross_income": gross_income,
        "standard_deduction": standard_deduction,
        "other_deductions": total_deductions,
        "taxable_income": int(taxable_income),
        "tax_before_rebate": round_tax(tax_before_rebate),
        "rebate_87a_applied": round_tax(tax_before_rebate - tax_after_rebate),
        "cess": round_tax(tax_with_cess - tax_after_rebate),
        "final_tax": final_tax,
    }
