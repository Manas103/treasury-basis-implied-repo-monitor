from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from treasury_monitor.swap_curve import TENORS, bootstrap


def test_flat_curve_matches_closed_form_discounting():
    """If every par rate equals the same flat rate r, the bootstrapped
    discount factor at every tenor, including the interpolated years
    inside the 15/20/25/30 gaps, must equal the closed-form (1+r)^-t
    exactly (to floating-point precision): a flat curve is the one case
    with an independent closed form to check the bootstrap against."""
    r = 0.0425
    curve = bootstrap({t: r for t in TENORS})
    for t in range(0, max(TENORS) + 1):
        expected = (1.0 + r) ** -t
        assert curve.df(t) == pytest.approx(expected, abs=1e-10)


def test_every_input_instrument_reprices_within_tolerance():
    """The repricing claim: every one of the 14 input par rates must be
    recoverable from the bootstrapped curve to within 0.02bp."""
    import math

    par_rates = {t: 0.03 + 0.012 * (1.0 - math.exp(-t / 8.0)) for t in TENORS}
    curve = bootstrap(par_rates)
    for t in TENORS:
        err_bp = abs(curve.implied_par_rate(t) - par_rates[t]) * 10000.0
        assert err_bp < 0.02


def test_rejects_wrong_tenor_set():
    with pytest.raises(ValueError):
        bootstrap({1: 0.04, 2: 0.041})


def test_discount_factors_are_monotonically_decreasing():
    import math

    par_rates = {t: 0.035 + 0.01 * (1.0 - math.exp(-t / 10.0)) for t in TENORS}
    curve = bootstrap(par_rates)
    years = sorted(curve.discount_factors)
    for a, b in zip(years, years[1:]):
        assert curve.df(b) < curve.df(a)


def test_pvbp_equals_sum_of_discount_factors():
    curve = bootstrap({t: 0.04 for t in TENORS})
    pvbp10 = curve.pvbp(10)
    direct_sum = sum(curve.df(k) for k in range(1, 11))
    assert pvbp10 == pytest.approx(direct_sum, abs=1e-12)
