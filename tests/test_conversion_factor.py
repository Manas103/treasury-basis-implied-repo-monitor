from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor.conversion_factor import conversion_factor
from treasury_monitor.oracle import oracle_conversion_factor


def test_six_percent_coupon_prices_to_par():
    """At exactly the 6% notional yield, a 6% coupon note must have
    conversion factor 1.0 for any maturity: this is a closed-form identity,
    not a fitted result."""
    for years in [1.0, 5.0, 8.8, 9.5, 9.9, 15.0]:
        cf = conversion_factor(0.06, years)
        assert abs(cf - 1.0) < 1e-9, f"expected CF=1.0 at 6% coupon, got {cf} for years={years}"


def test_higher_coupon_means_higher_conversion_factor():
    years = 9.0
    cf_low = conversion_factor(0.02, years)
    cf_mid = conversion_factor(0.04, years)
    cf_high = conversion_factor(0.07, years)
    assert cf_low < cf_mid < cf_high


def test_main_engine_and_oracle_conversion_factor_agree():
    """The main engine's loop-based PV and the oracle's closed-form annuity
    PV must agree to floating precision for every basket coupon/maturity."""
    for coupon in [0.035, 0.0375, 0.04, 0.04125, 0.0425, 0.045, 0.0475]:
        for years in [6.8, 7.5, 8.0, 8.8, 9.9, 10.0]:
            main_cf = conversion_factor(coupon, years)
            oracle_cf = oracle_conversion_factor(coupon, years)
            assert abs(main_cf - oracle_cf) < 1e-10, (coupon, years, main_cf, oracle_cf)
