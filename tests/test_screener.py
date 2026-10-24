from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from treasury_monitor.screener import SCREENED_TENORS, ROLLING_WINDOW, dv01_neutral_ratio


def test_every_session_has_every_series(screened_db):
    cur = screened_db.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions")
    (num_sessions,) = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM spread_series")
    (num_rows,) = cur.fetchone()
    expected_series = len(SCREENED_TENORS) + 1  # 4 swap spreads + 1 invoice spread
    assert num_rows == num_sessions * expected_series


def test_no_zscore_before_the_rolling_window_fills(screened_db):
    cur = screened_db.cursor()
    cur.execute(f"SELECT COUNT(*) FROM spread_series WHERE session_id < {ROLLING_WINDOW} AND zscore IS NOT NULL")
    assert cur.fetchone()[0] == 0


def test_every_dislocation_has_a_zscore_at_or_past_threshold(screened_db):
    cur = screened_db.cursor()
    cur.execute("SELECT zscore FROM spread_series WHERE is_dislocation = 1")
    rows = cur.fetchall()
    assert len(rows) > 0, "the 120-session fixture should produce at least one dislocation"
    for (z,) in rows:
        assert abs(z) >= 2.0


def test_survivors_are_a_subset_of_dislocations(screened_db):
    cur = screened_db.cursor()
    cur.execute("SELECT COUNT(*) FROM spread_series WHERE survives_filter = 1 AND is_dislocation = 0")
    assert cur.fetchone()[0] == 0


def test_non_dislocations_never_survive(screened_db):
    cur = screened_db.cursor()
    cur.execute("SELECT COUNT(*) FROM spread_series WHERE is_dislocation = 0 AND survives_filter = 1")
    assert cur.fetchone()[0] == 0


def test_survivor_distance_exceeds_its_own_cost(screened_db):
    cur = screened_db.cursor()
    cur.execute(
        "SELECT spread_bp, rolling_mean_bp, cost_bp FROM spread_series WHERE survives_filter = 1"
    )
    rows = cur.fetchall()
    assert len(rows) > 0
    for spread_bp, mean_bp, cost_bp in rows:
        assert abs(spread_bp - mean_bp) > cost_bp


@pytest.mark.parametrize("series_name", [f"swap_spread_{t}" for t in SCREENED_TENORS] + ["invoice_spread_10"])
def test_dv01_neutral_sizing_is_exact(screened_db, series_name):
    cur = screened_db.cursor()
    cur.execute("SELECT session_id, sim_date FROM sessions ORDER BY session_id DESC LIMIT 1")
    session_id, sim_date_s = cur.fetchone()
    sim_date = dt.date.fromisoformat(sim_date_s)

    leg_a_dollar_dv01, leg_b_dollar_dv01 = dv01_neutral_ratio(series_name, session_id, screened_db, sim_date)
    assert leg_a_dollar_dv01 == pytest.approx(leg_b_dollar_dv01, abs=1e-9)
