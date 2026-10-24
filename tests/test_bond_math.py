from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from treasury_monitor import bond_math


def test_par_bond_prices_to_par():
    # a bond whose coupon rate equals the discount yield must price to 100
    price = bond_math.bond_price(0.045, 0.045, 10.0)
    assert price == pytest.approx(100.0, abs=1e-9)


def test_solve_ytm_recovers_the_pricing_yield():
    price = bond_math.bond_price(0.0512, 0.0400, 7.3)
    ytm = bond_math.solve_ytm(price, 0.0400, 7.3)
    assert ytm == pytest.approx(0.0512, abs=1e-8)


def test_dv01_matches_a_direct_bump_and_reprice():
    y, coupon, years = 0.045, 0.04, 9.6
    dv01 = bond_math.bond_dv01(y, coupon, years)
    direct = (bond_math.bond_price(y - 0.0001, coupon, years) - bond_math.bond_price(y + 0.0001, coupon, years)) / 2.0
    assert dv01 == pytest.approx(direct, abs=1e-12)


def test_dv01_is_positive_for_a_normal_bond():
    assert bond_math.bond_dv01(0.045, 0.04, 10.0) > 0
