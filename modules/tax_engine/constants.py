"""
Tax constants for FY 2025-26 (AY 2026-27).

WHY THIS FILE EXISTS:
Tax slabs, standard deduction, and rebate limits change almost every
Union Budget. Before this file existed, these numbers were hardcoded
inline inside old_regime.py / new_regime.py, which meant "the budget
changed" required hunting through calculation logic to update a
number. Now it's a one-place, versioned update.

Source of truth for this iteration (verified against Finance Act 2025
provisions carried into FY 2025-26, effective for income earned
1 Apr 2025 - 31 Mar 2026, filed by 31 Jul 2026):
  - New regime: Section 87A rebate raised to Rs.60,000, effectively
    making taxable income up to Rs.12,00,000 tax-free.
  - New regime standard deduction: Rs.75,000.
  - Old regime standard deduction: Rs.50,000 (unchanged for years).
  - Old regime 87A rebate: Rs.12,500 up to Rs.5,00,000 taxable income
    (unchanged for years).
  - Health & Education Cess: 4% on tax after rebate, both regimes.

IMPORTANT: When a new Union Budget changes these numbers, update this
file only. Do not touch old_regime.py / new_regime.py.
"""

TAX_YEAR_LABEL = "FY 2025-26 (AY 2026-27)"

CESS_RATE = 0.04  # Health & Education Cess, applies to both regimes

SECTION_80C_LIMIT = 150000  # Chapter VI-A cap, old regime only

# ---------------- OLD REGIME ---------------- #

OLD_REGIME = {
    "standard_deduction": 50000,
    "slabs": [
        # (upper_limit_inclusive, rate). None = no upper limit.
        (250000, 0.00),
        (500000, 0.05),
        (1000000, 0.20),
        (None, 0.30),
    ],
    "rebate_87a": {
        "max_taxable_income": 500000,
        "max_rebate": 12500,
    },
}

# ---------------- NEW REGIME (default regime under Section 115BAC) ---------------- #

NEW_REGIME = {
    "standard_deduction": 75000,
    "slabs": [
        (400000, 0.00),
        (800000, 0.05),
        (1200000, 0.10),
        (1600000, 0.15),
        (2000000, 0.20),
        (2400000, 0.25),
        (None, 0.30),
    ],
    "rebate_87a": {
        "max_taxable_income": 1200000,
        "max_rebate": 60000,
    },
}
