from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import rates_market_sim
from treasury_monitor.swap_curve import TENORS


def test_generation_is_reproducible_given_the_same_seed():
    swap_a, treasury_a, _ = rates_market_sim.generate_sessions(50, seed=99)
    swap_b, treasury_b, _ = rates_market_sim.generate_sessions(50, seed=99)
    assert swap_a == swap_b
    assert treasury_a == treasury_b


def test_every_session_has_all_14_swap_tenors():
    swap_rows, _, _ = rates_market_sim.generate_sessions(30, seed=1)
    by_session = {}
    for session_id, tenor, _ in swap_rows:
        by_session.setdefault(session_id, set()).add(tenor)
    assert len(by_session) == 30
    for tenors in by_session.values():
        assert tenors == set(TENORS)


def test_swap_rates_land_in_a_plausible_band():
    swap_rows, _, _ = rates_market_sim.generate_sessions(200, seed=1)
    for _, _, rate in swap_rows:
        assert 0.01 < rate < 0.10


def test_treasury_yield_equals_swap_rate_minus_spread():
    swap_rows, treasury_rows, spread_bp = rates_market_sim.generate_sessions(80, seed=5)
    swap_by_key = {(sid, t): r for sid, t, r in swap_rows}
    for session_id, tenor, treasury_yield in treasury_rows:
        swap_rate = swap_by_key[(session_id, tenor)]
        implied_spread_bp = (swap_rate - treasury_yield) * 10000.0
        recorded_spread_bp = spread_bp[tenor][session_id]
        assert abs(implied_spread_bp - recorded_spread_bp) < 1e-9
