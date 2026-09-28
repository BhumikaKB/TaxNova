"""
Generic slab-tax math shared by both regimes.

Previously, old_regime.py and new_regime.py each had their own
copy-pasted if/elif slab ladder. That meant a bug fix or a rounding
change had to be made twice, and the two regimes could silently drift
out of sync. This module is the single implementation both regimes
call into, parameterized by the slab table in constants.py.
"""

from math import floor


def compute_slab_tax(taxable_income, slabs):
    """
    Applies a progressive slab table to taxable_income.

    slabs: list of (upper_limit_inclusive, rate) tuples, ordered
    ascending, with the last tuple's upper_limit as None meaning
    "no ceiling".
    """
    if taxable_income <= 0:
        return 0.0

    tax = 0.0
    lower = 0

    for upper, rate in slabs:
        if upper is None:
            tax += max(taxable_income - lower, 0) * rate
            break

        if taxable_income > upper:
            tax += (upper - lower) * rate
        else:
            tax += max(taxable_income - lower, 0) * rate
            break

        lower = upper

    return tax


def apply_rebate_87a(tax_before_rebate, taxable_income, rebate_config):
    """
    Applies Section 87A rebate, including marginal relief.

    Marginal relief matters here: without it, someone earning Rs.1 just
    over the rebate threshold could owe far more than Rs.1 in extra
    tax (a cliff-edge). Marginal relief caps the tax increase to the
    amount of income that crossed the threshold.
    """
    threshold = rebate_config["max_taxable_income"]
    max_rebate = rebate_config["max_rebate"]

    if taxable_income <= threshold:
        rebate = min(tax_before_rebate, max_rebate)
        return max(tax_before_rebate - rebate, 0.0)

    # Marginal relief zone: income is just above the threshold.
    # Standard rule: tax payable is capped at the amount of income
    # that crossed the threshold, so crossing by Rs.1 never costs
    # more than Rs.1 in extra tax.
    excess_income = taxable_income - threshold
    if tax_before_rebate > excess_income and excess_income < max_rebate:
        return excess_income

    return tax_before_rebate


def apply_cess(tax_after_rebate, cess_rate):
    return tax_after_rebate * (1 + cess_rate)


def round_tax(amount):
    """
    Indian tax computations round to the nearest rupee. Using floor
    here matches how tax software commonly truncates paise rather
    than rounding up, which avoids ever showing a payable amount
    higher than what's legally due.
    """
    return int(floor(amount + 0.5))
