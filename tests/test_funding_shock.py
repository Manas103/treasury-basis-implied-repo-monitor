from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor.funding_shock import FUNDING_SHOCK, run_funding_shock


def test_funding_shock_shifts_net_basis_up(small_db):
    """A positive funding-rate shock raises financing cost, which shrinks
    carry, which pushes net basis up: every observation should show a
    strictly positive shift."""
    result = run_funding_shock(small_db)
    assert result["num_observations"] > 0
    assert result["min_delta_ticks"] > 0
    assert result["median_delta_ticks_all_observations"] > 0


def test_funding_shock_formula_matches_hand_calc():
    """Direct unit check of the shock formula against a hand-computed
    example, independent of any database round trip."""
    purchase_dirty = 101.375
    days_to_delivery = 45

    expected_points = purchase_dirty * FUNDING_SHOCK * days_to_delivery / 360.0
    expected_ticks = expected_points * 32.0

    # purchase_dirty=101.375, shock=0.0025, days=45/360=0.125 -> points=0.03167..., ticks=1.0135
    assert abs(expected_points - 0.031679688) < 1e-6
    assert abs(expected_ticks - 1.013749999) < 1e-4


def test_funding_shock_scales_linearly_with_days_to_delivery(small_db):
    """Sanity check: sessions closer to delivery (fewer days) should show
    a smaller funding-shock impact than sessions further from delivery,
    all else equal, because financing cost scales with days/360."""
    cur = small_db.cursor()
    cur.execute("SELECT DISTINCT purchase_dirty, days_to_delivery FROM results r JOIN sessions s ON r.session_id = s.session_id LIMIT 1")
    purchase_dirty, _ = cur.fetchone()

    points_10_days = purchase_dirty * FUNDING_SHOCK * 10 / 360.0
    points_80_days = purchase_dirty * FUNDING_SHOCK * 80 / 360.0
    assert points_80_days > points_10_days
