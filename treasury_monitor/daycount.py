"""Actual/Actual day-count helpers for semiannual-coupon Treasury notes.

Simplification (disclosed in README): every note is assumed to pay coupons
on a clean six-month cycle anchored to its maturity date (maturity day-of-month
held fixed, months stepped by six each time). Real Treasury coupon calendars
occasionally shift for weekends/holidays; this model ignores that shift.
"""
from __future__ import annotations

from datetime import date


def add_months(d: date, months: int) -> date:
    """Add a signed number of months to a date, clamping the day to the
    last valid day of the resulting month (handles Feb 30 -> Feb 28/29 etc.)."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # find last day of (year, month)
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    last_day = (next_month_first - date(year, month, 1)).days
    day = min(d.day, last_day)
    return date(year, month, day)


def coupon_bracket(as_of: date, maturity: date) -> tuple[date, date]:
    """Return (prev_coupon_date, next_coupon_date) bracketing as_of, walking
    backward from maturity in six-month steps. as_of must be <= maturity.

    Each candidate coupon date is computed as add_months(maturity, -6*k)
    directly from the original maturity date, not by chaining add_months
    on the previous (possibly already end-of-month-clamped) result. Found
    via the independent oracle diff: chaining loses the original
    day-of-month anchor the first time a step lands on a short month (e.g.
    a note maturing on the 30th, stepped back into February), and every
    subsequent step then clamps against the wrong day, silently shifting
    the whole earlier coupon schedule by up to a day in leap-year
    Februaries. See README findings for the full symptom-to-fix story."""
    if as_of > maturity:
        raise ValueError("as_of date is after maturity")
    k = 0
    while add_months(maturity, -6 * (k + 1)) > as_of:
        k += 1
    prev_date = add_months(maturity, -6 * (k + 1))
    next_date = add_months(maturity, -6 * k)
    return prev_date, next_date


def accrued_interest(coupon_rate: float, as_of: date, maturity: date, face: float = 100.0) -> float:
    """Actual/Actual accrued interest on a semiannual-coupon note as of as_of.

    accrued = (semiannual coupon) * (days since last coupon) / (days in period)
    """
    prev_date, next_date = coupon_bracket(as_of, maturity)
    days_in_period = (next_date - prev_date).days
    days_accrued = (as_of - prev_date).days
    semiannual_coupon = coupon_rate / 2.0 * face
    if days_in_period == 0:
        return 0.0
    return semiannual_coupon * days_accrued / days_in_period


def coupons_paid_between(coupon_rate: float, start: date, end: date, maturity: date, face: float = 100.0) -> float:
    """Total coupon cash paid strictly after `start` and on/before `end`,
    walking the same six-month coupon schedule anchored at maturity.
    start < end <= maturity is expected (holding-period income).

    Every candidate coupon date is computed as add_months(maturity, -6*k)
    directly from maturity (same anchor-from-original-date fix as
    coupon_bracket), not by chaining add_months forward step by step,
    for the same leap-year-February reason."""
    if start >= end:
        return 0.0
    semiannual_coupon = coupon_rate / 2.0 * face
    total = 0.0
    k = 0
    while add_months(maturity, -6 * k) > start:
        k += 1
    # k is now the smallest index with coupon date <= start; the first
    # coupon strictly after start is one index earlier (or maturity itself)
    j = k - 1
    while j >= 0:
        cd = add_months(maturity, -6 * j)
        if cd > end:
            break
        total += semiannual_coupon
        j -= 1
    return total
