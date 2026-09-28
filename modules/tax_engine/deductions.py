"""
Tax-saving suggestions, derived from a taxpayer's actual deduction
usage rather than static advice.

Uses SECTION_80C_LIMIT from constants.py (single source of truth for
all tax figures) instead of a locally duplicated constant, so a
Budget change to the 80C cap only needs updating in one place.
"""

from modules.tax_engine.constants import SECTION_80C_LIMIT


def calculate_remaining_80c(invested_amount):
    remaining = SECTION_80C_LIMIT - invested_amount
    return max(remaining, 0)


def get_tax_saving_suggestions(income, invested_amount, best_regime=None):
    """
    best_regime: when known, lets this skip 80C/80D suggestions for
    New Regime users, since those deductions don't apply there and
    suggesting them would be actively misleading.
    """
    suggestions = []

    if best_regime == "New Regime":
        suggestions.append(
            "You're on the New Regime, where most deductions (80C, 80D, HRA) "
            "don't apply. The main lever left is your employer's NPS "
            "contribution under Section 80CCD(2), which is still allowed."
        )
        return suggestions

    remaining_80c = calculate_remaining_80c(invested_amount)

    if remaining_80c > 0:
        suggestions.append(
            f"You can still invest ₹{remaining_80c:,} under Section 80C "
            f"(limit is ₹{SECTION_80C_LIMIT:,}/year) to lower your taxable income."
        )

    suggestions.append(
        "Consider health insurance under Section 80D for an additional deduction."
    )
    suggestions.append(
        "Investing in NPS under Section 80CCD(1B) can give a further ₹50,000 deduction."
    )
    suggestions.append(
        "Home loan interest under Section 24(b) may reduce taxable income further."
    )

    return suggestions
