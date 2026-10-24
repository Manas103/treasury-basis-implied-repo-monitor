"""OIS-discounted swap curve bootstrap from 14 simulated par swap
instruments: annual-pay, tau=1-per-period tenors 1-10, 15, 20, 25, 30
years. Annual pay with tau=1 is a disclosed simplification of real OIS
quarterly compounding and day-count conventions (see README).

Bootstrap: discount factors are pinned exactly from the par-swap identity
(fixed-leg PV == 1 - DF(T), the standard single-curve par-swap condition)
walking tenors in increasing order. The 1..10-year block is contiguous, so
each new discount factor there is the only unknown in its own equation.
Tenors 15, 20, 25 and 30 are not adjacent to the last fully pinned integer
year, so every annual cashflow date strictly between the last known knot
and the new tenor is itself unknown, expressed as a log-linear
interpolation between the last known discount factor and the new
(still-unknown) one. That turns the par condition into one equation in one
unknown with a fractional exponent, not a closed form, so it is solved by
bisection (`_solve_unknown_df`), using the fact that the par-swap identity
is monotonically increasing in the unknown discount factor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

TENORS: list[int] = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 20, 25, 30]


@dataclass
class SwapCurve:
    par_rates: dict  # input tenor (int years) -> par rate (decimal)
    discount_factors: dict = field(default_factory=dict)  # every integer year 0..max(tenor) -> DF

    def df(self, t: int) -> float:
        return self.discount_factors[t]

    def pvbp(self, tenor: int) -> float:
        """Annuity sum sum_{k=1}^{tenor} DF(k): the PV of 1 unit of
        notional paid annually through `tenor`. One basis point of this,
        times notional, is the fixed leg's DV01 (the standard PVBP
        convention: a swap's DV01 is its own annuity factor, not a
        separate duration calculation)."""
        return sum(self.discount_factors[k] for k in range(1, tenor + 1))

    def par_rate_at(self, tenor: int) -> float:
        return self.par_rates[tenor]

    def implied_par_rate(self, tenor: int) -> float:
        """Recomputes the par rate the bootstrapped curve itself implies
        for `tenor`: (1 - DF(T)) / PVBP(T). Used by the repricing check;
        should equal the input par rate to solver tolerance, not by
        construction coincidence but because the discount factor at every
        input tenor was solved exactly from this identity."""
        return (1.0 - self.discount_factors[tenor]) / self.pvbp(tenor)


def _interp_weight(k: int, t_prev: int, t_new: int) -> float:
    return (k - t_prev) / (t_new - t_prev)


def _par_condition(df_new: float, t_prev: int, df_prev: float, t_new: int, par_rate: float, known_sum: float) -> float:
    """par_rate * (fixed-leg annuity PV) - (1 - df_new), with df_new as the
    only unknown. Its root is the discount factor at t_new. The annuity PV
    splits into `known_sum` (already-pinned integer years <= t_prev) plus
    every interpolated year strictly between t_prev and t_new, each a
    log-linear blend of df_prev and the unknown df_new."""
    unknown_sum = 0.0
    for k in range(t_prev + 1, t_new + 1):
        if k == t_new:
            unknown_sum += df_new
        else:
            w = _interp_weight(k, t_prev, t_new)
            unknown_sum += (df_prev ** (1.0 - w)) * (df_new ** w)
    return par_rate * (known_sum + unknown_sum) - (1.0 - df_new)


def _solve_unknown_df(t_prev: int, df_prev: float, t_new: int, par_rate: float, known_sum: float,
                       lo: float = 1e-6, hi: float = 1.5, tol: float = 1e-14, max_iter: int = 200) -> float:
    """Bisection on df_new. _par_condition is monotonically increasing in
    df_new (every term in unknown_sum, and the -(1-df_new) term, increases
    with df_new for df_new in (0, hi]), so the root is unique once
    bracketed."""
    f_lo = _par_condition(lo, t_prev, df_prev, t_new, par_rate, known_sum)
    f_hi = _par_condition(hi, t_prev, df_prev, t_new, par_rate, known_sum)
    if f_lo * f_hi > 0:
        raise ValueError(f"root not bracketed for tenor {t_new}")
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = _par_condition(mid, t_prev, df_prev, t_new, par_rate, known_sum)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def bootstrap(par_rates: dict) -> SwapCurve:
    """par_rates must have exactly the keys in TENORS. Returns a
    SwapCurve with discount_factors filled for every integer year from 0
    to max(TENORS), including the interpolated years inside the 15/20/25/30
    gaps."""
    if sorted(par_rates) != TENORS:
        raise ValueError(f"expected exactly the tenors {TENORS}, got {sorted(par_rates)}")

    dfs = {0: 1.0}
    t_prev, df_prev = 0, 1.0

    for t in TENORS:
        s = par_rates[t]
        known_sum = sum(dfs[k] for k in range(1, t_prev + 1))
        df_t = _solve_unknown_df(t_prev, df_prev, t, s, known_sum)
        for k in range(t_prev + 1, t):
            w = _interp_weight(k, t_prev, t)
            dfs[k] = (df_prev ** (1.0 - w)) * (df_t ** w)
        dfs[t] = df_t
        t_prev, df_prev = t, df_t

    return SwapCurve(par_rates=dict(par_rates), discount_factors=dfs)
