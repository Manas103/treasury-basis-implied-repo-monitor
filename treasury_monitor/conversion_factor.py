"""Approximate CME-style conversion factor for a Treasury note deliverable
into a note futures contract.

This is a PV-at-6%-notional-yield approximation of the published CME
methodology, not a reconciliation against official CME conversion factor
tables (disclosed in README, "What this is NOT"). It assumes the note's
remaining life to the delivery date lands on a whole number of semiannual
coupon periods (no stub-period accrued-interest adjustment), which is a
deliberate simplification: real CME factors handle stub periods with an
extra discounting/accrued term.

Because the discount rate is exactly 3% per semiannual period (6% annual,
matching the note's own coupon rate case), a note with a 6.00% coupon must
price to exactly par: conversion_factor(0.06, anything) == 1.0. That
identity is used as a correctness test.
"""
from __future__ import annotations

NOTIONAL_SEMIANNUAL_YIELD = 0.03  # 6% annual notional coupon standard, per period


def periods_to_delivery(years_to_maturity: float) -> int:
    """Round remaining life to the nearest whole semiannual coupon period."""
    n = round(years_to_maturity * 2)
    return max(n, 1)


def conversion_factor(coupon_rate: float, years_to_maturity: float, face: float = 100.0) -> float:
    """Present value, per unit face, of the note's remaining cash flows
    discounted at 3% per semiannual period, assuming the remaining life
    lands on a whole number of coupon periods (see module docstring)."""
    n = periods_to_delivery(years_to_maturity)
    semiannual_coupon = coupon_rate / 2.0 * face
    pv = 0.0
    for k in range(1, n + 1):
        cashflow = semiannual_coupon
        if k == n:
            cashflow += face
        pv += cashflow / ((1.0 + NOTIONAL_SEMIANNUAL_YIELD) ** k)
    return pv / face
