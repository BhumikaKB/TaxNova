"""
New Regime tax calculation (Section 115BAC - default regime).

Most Chapter VI-A deductions (80C, 80D, HRA, etc.) are NOT allowed
under this regime, so total_deductions is intentionally not accepted
here - only the standard deduction and employer NPS contribution
(80CCD(2)) remain valid, and this project doesn't yet collect the
latter from Form 16, so it's left at 0 with a clear comment for
where it plugs in later.
"""

from modules.tax_engine.constants import NEW_REGIME, CESS_RATE
from modules.tax_engine.slab_calculator import (
    compute_slab_tax, apply_rebate_87a, apply_cess, round_tax
)


def calculate_new_regime(gross_income, employer_nps_contribution=0):
    """
    gross_income: gross salary before any deductions.
    employer_nps_contribution: Section 80CCD(2) - one of the few
        deductions still allowed under the new regime. Defaults to 0
        until Form 16 extraction reliably pulls this figure.
    """
    standard_deduction = NEW_REGIME["standard_deduction"]

    taxable_income = max(
        gross_income - standard_deduction - employer_nps_contribution, 0
    )

    tax_before_rebate = compute_slab_tax(taxable_income, NEW_REGIME["slabs"])
    tax_after_rebate = apply_rebate_87a(
        tax_before_rebate, taxable_income, NEW_REGIME["rebate_87a"]
    )
    tax_with_cess = apply_cess(tax_after_rebate, CESS_RATE)
    final_tax = round_tax(tax_with_cess)

    return {
        "regime": "New Regime",
        "gross_income": gross_income,
        "standard_deduction": standard_deduction,
        "other_deductions": employer_nps_contribution,
        "taxable_income": int(taxable_income),
        "tax_before_rebate": round_tax(tax_before_rebate),
        "rebate_87a_applied": round_tax(tax_before_rebate - tax_after_rebate),
        "cess": round_tax(tax_with_cess - tax_after_rebate),
        "final_tax": final_tax,
    }
