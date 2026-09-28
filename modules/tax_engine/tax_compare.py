"""
Regime comparison + recommendation reasoning.

The old version of this module only compared two numbers and picked
the smaller one. That tells a user WHAT to pick but not WHY - which
is exactly the gap TaxNova exists to close (per the project's own
stated goal: "existing portals only calculate tax, they don't explain
decisions"). This module builds a short, specific reasoning trail
from the two tax breakdowns.
"""


def compare_tax_regimes(old_breakdown, new_breakdown):
    old_tax = old_breakdown["final_tax"]
    new_tax = new_breakdown["final_tax"]
    savings = abs(old_tax - new_tax)

    # A genuine tie (often ₹0 vs ₹0 at low income, but can happen at
    # any income level) needs its own honest path. Crowning a
    # "winner" and listing reasons like "higher deductions" or "lower
    # taxable income" when the actual bottom-line tax is identical is
    # misleading - those structural differences exist but didn't
    # translate into any real saving. Defaulting to New Regime on a
    # tie reflects a real, defensible reason: it needs no investment
    # proof or documentation to claim, so it's operationally simpler
    # when there's nothing to gain from Old Regime's deductions.
    if old_tax == new_tax:
        return {
            "best_regime": "New Regime",
            "savings": 0,
            "old_tax": old_tax,
            "new_tax": new_tax,
            "is_tie": True,
            "reasoning": [
                f"Both regimes result in the same tax (₹{old_tax:,}) at this income and deduction level.",
                "New Regime is suggested as the default since it needs no investment "
                "proof or documentation to claim - there's nothing to gain from Old "
                "Regime's deductions here, so the simpler option wins.",
            ],
        }

    if old_tax < new_tax:
        winner, loser = old_breakdown, new_breakdown
    else:
        winner, loser = new_breakdown, old_breakdown

    reasons = _build_reasons(winner, loser, savings)

    return {
        "best_regime": winner["regime"],
        "savings": savings,
        "old_tax": old_tax,
        "new_tax": new_tax,
        "is_tie": False,
        "reasoning": reasons,
    }


def _build_reasons(winner, loser, savings):
    reasons = []

    if winner["other_deductions"] > loser["other_deductions"]:
        reasons.append(
            f"Higher deductions claimed (₹{winner['other_deductions']:,}) "
            f"reduce taxable income more under {winner['regime']}."
        )

    if winner["taxable_income"] < loser["taxable_income"]:
        reasons.append(
            f"Taxable income is ₹{loser['taxable_income'] - winner['taxable_income']:,} "
            f"lower under {winner['regime']}."
        )

    if winner["rebate_87a_applied"] > 0:
        reasons.append(
            f"Section 87A rebate of ₹{winner['rebate_87a_applied']:,} fully or "
            f"partly cancels out tax under {winner['regime']}."
        )

    if winner["standard_deduction"] != loser["standard_deduction"]:
        reasons.append(
            f"{winner['regime']} allows a standard deduction of "
            f"₹{winner['standard_deduction']:,} (vs ₹{loser['standard_deduction']:,} "
            f"under {loser['regime']})."
        )

    reasons.append(f"Overall, {winner['regime']} saves ₹{savings:,} compared to {loser['regime']}.")

    return reasons
