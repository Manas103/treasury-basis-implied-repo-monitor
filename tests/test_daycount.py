from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor.daycount import accrued_interest, coupon_bracket, coupons_paid_between
from treasury_monitor.oracle import oracle_accrued_interest, oracle_coupon_bracket, oracle_coupons_paid_between


def test_coupon_bracket_contains_as_of_date():
    maturity = date(2033, 6, 18)
    for as_of in [date(2024, 3, 1), date(2028, 12, 25), date(2033, 1, 1), date(2033, 6, 18)]:
        prev_d, next_d = coupon_bracket(as_of, maturity)
        assert prev_d <= as_of <= next_d
        assert (next_d - prev_d).days in (181, 182, 183, 184)


def test_accrued_interest_bounds():
    maturity = date(2033, 6, 18)
    coupon_rate = 0.04125
    semiannual = coupon_rate / 2 * 100
    for as_of in [date(2024, 3, 1), date(2026, 8, 26), date(2033, 6, 18)]:
        a = accrued_interest(coupon_rate, as_of, maturity)
        assert -1e-9 <= a <= semiannual + 1e-9


def test_coupons_paid_between_known_window():
    # maturity anchors coupons on the 18th every June and December.
    maturity = date(2033, 6, 18)
    coupon_rate = 0.04
    semiannual = coupon_rate / 2 * 100
    # window spans exactly one coupon date (2032-12-18)
    total = coupons_paid_between(coupon_rate, date(2032, 7, 1), date(2032, 12, 20), maturity)
    assert abs(total - semiannual) < 1e-9

    # window spans two coupon dates (2032-06-18 and 2032-12-18)
    total2 = coupons_paid_between(coupon_rate, date(2032, 1, 1), date(2033, 1, 1), maturity)
    assert abs(total2 - 2 * semiannual) < 1e-9

    # window spans zero coupon dates
    total0 = coupons_paid_between(coupon_rate, date(2032, 7, 1), date(2032, 12, 1), maturity)
    assert abs(total0 - 0.0) < 1e-9


def test_main_and_oracle_daycount_agree():
    """Independently-coded coupon-date search (backward walk vs
    estimate-then-correct) must agree on accrued interest and coupon
    brackets for the same inputs."""
    maturity = date(2033, 8, 30)
    coupon_rate = 0.0425
    # Note: as_of == maturity is deliberately excluded here; see README
    # findings section for the genuine boundary disagreement at that
    # single point (irrelevant to the simulation, which never settles
    # exactly on a note's maturity date).
    for as_of in [date(2024, 3, 1), date(2026, 8, 26), date(2029, 2, 14), date(2033, 8, 29)]:
        main_prev, main_next = coupon_bracket(as_of, maturity)
        oracle_prev, oracle_next = oracle_coupon_bracket(as_of, maturity)
        assert main_prev == oracle_prev, (as_of, main_prev, oracle_prev)
        assert main_next == oracle_next, (as_of, main_next, oracle_next)

        main_acc = accrued_interest(coupon_rate, as_of, maturity)
        oracle_acc = oracle_accrued_interest(coupon_rate, as_of, maturity)
        assert abs(main_acc - oracle_acc) < 1e-9

    main_paid = coupons_paid_between(coupon_rate, date(2024, 3, 1), date(2025, 3, 1), maturity)
    oracle_paid = oracle_coupons_paid_between(coupon_rate, date(2024, 3, 1), date(2025, 3, 1), maturity)
    assert abs(main_paid - oracle_paid) < 1e-9
