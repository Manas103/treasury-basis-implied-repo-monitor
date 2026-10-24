"""Standard semiannual-coupon bond pricing, yield solve and DV01.

Shared by the swap-curve extension: the CTD note's yield-to-maturity (used
to build the invoice spread) and its DV01 (used for DV01-neutral leg
sizing) both come from here. Uses the same whole-coupon-period
simplification as conversion_factor.py (remaining life rounded to the
nearest whole semiannual period; no stub-period adjustment, disclosed in
README).
"""
from __future__ import annotations


def bond_price(yield_: float, coupon_rate: float, years_to_maturity: float, freq: int = 2, face: float = 100.0) -> float:
    """Present value of a bullet bond's remaining coupons and face, at a
    flat annualized yield compounded `freq` times per year."""
    n = max(round(years_to_maturity * freq), 1)
    coupon = coupon_rate / freq * face
    period_yield = yield_ / freq
    pv = 0.0
    for k in range(1, n + 1):
        cashflow = coupon + (face if k == n else 0.0)
        pv += cashflow / (1.0 + period_yield) ** k
    return pv


def solve_ytm(price: float, coupon_rate: float, years_to_maturity: float, freq: int = 2, face: float = 100.0,
              lo: float = -0.05, hi: float = 0.30, tol: float = 1e-10, max_iter: int = 200) -> float:
    """Bisection solve for the flat yield that reprices `bond_price` to
    `price`. bond_price is strictly decreasing in yield_ (every cashflow is
    positive), so the root is unique and bisection is well-posed once
    bracketed."""
    f_lo = bond_price(lo, coupon_rate, years_to_maturity, freq, face) - price
    f_hi = bond_price(hi, coupon_rate, years_to_maturity, freq, face) - price
    if f_lo * f_hi > 0:
        raise ValueError("yield not bracketed in [lo, hi] for this price")
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = bond_price(mid, coupon_rate, years_to_maturity, freq, face) - price
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def bond_dv01(yield_: float, coupon_rate: float, years_to_maturity: float, freq: int = 2, face: float = 100.0,
              bump: float = 0.0001) -> float:
    """Dollar price change per 100 face for a 1bp parallel move in yield_,
    via a central difference (bump up and down by 1bp and halve the
    difference), not a closed-form duration formula, so it stays correct
    even though bond_price's whole-period rounding makes duration's clean
    closed form a poor fit near a period boundary."""
    p_dn = bond_price(yield_ - bump, coupon_rate, years_to_maturity, freq, face)
    p_up = bond_price(yield_ + bump, coupon_rate, years_to_maturity, freq, face)
    return (p_dn - p_up) / 2.0
