"""Synthetic swap curve and on-the-run Treasury yield simulator, aligned
session-for-session with `market_sim.populate_db` (same session_id range;
run after it, into the same database, never resetting its tables).

Every input here is synthetic, fixed-seed, and independent of any live or
historical market data:

- 14 par swap rates per session (`swap_curve.TENORS`), built from a fixed
  Nelson-Siegel-style structural curve shape plus a daily random-walk
  level shock shared across all tenors (a parallel move) plus a small
  independent idiosyncratic shock per tenor (a curve-shape wiggle).
- 4 on-the-run Treasury yields (2, 5, 10, 30 year), each defined as that
  tenor's simulated swap rate minus a simulated swap spread. The swap
  spread itself, not the Treasury yield, is the primary simulated
  quantity: each of the 4 tenors gets its own mean-reverting (OU) process
  around a fixed structural mean level, so the screener has a real,
  non-degenerate distribution of swap-spread dislocations to screen
  without any of these parameters being chosen after seeing the screener's
  output.
"""
from __future__ import annotations

import math
import random

from treasury_monitor import db as db_module
from treasury_monitor.swap_curve import TENORS

SEED = 4201

LEVEL_START = 0.0450
LEVEL_DAILY_VOL = 0.00012  # shared parallel shock, all tenors move together by this much
LEVEL_MIN, LEVEL_MAX = 0.02, 0.08

CURVE_SLOPE = 0.0120   # long-end minus short-end structural richness, Nelson-Siegel style
CURVE_DECAY = 8.0       # years, controls how quickly the slope term saturates
TENOR_IDIO_VOL = 0.00004  # independent per-tenor daily wiggle, on top of the shared level move

SCREENED_TENORS = (2, 5, 10, 30)

# Structural mean swap-spread level per screened tenor (basis points), and
# OU (mean-reverting) parameters, fixed before any screener run. Signs and
# magnitudes are illustrative term-structure-of-swap-spreads shapes (short
# tenors richer, long tenors cheaper, a realistic qualitative pattern), not
# calibrated to any observed market print.
SPREAD_OU_PARAMS = {
    2: {"mean_bp": 6.0, "kappa": 0.03, "vol_bp": 2.2},
    5: {"mean_bp": 10.0, "kappa": 0.025, "vol_bp": 2.6},
    10: {"mean_bp": 16.0, "kappa": 0.02, "vol_bp": 3.0},
    30: {"mean_bp": -8.0, "kappa": 0.018, "vol_bp": 3.4},
}


def _nelson_siegel_shape(tenor: float) -> float:
    """Slope term only (no separate curvature hump needed here): a
    monotone upward-sloping contribution that saturates with tenor,
    standard Nelson-Siegel slope-factor loading (1 - exp(-t/tau)) / (t/tau)
    inverted so long tenors carry more of CURVE_SLOPE than short ones."""
    x = tenor / CURVE_DECAY
    loading = (1.0 - math.exp(-x)) / x
    return 1.0 - loading  # 0 at t->0, -> 1 as t grows


def generate_sessions(num_sessions: int, seed: int = SEED):
    rng = random.Random(seed)

    level = LEVEL_START
    spread_level = {t: SPREAD_OU_PARAMS[t]["mean_bp"] for t in SCREENED_TENORS}

    swap_rate_rows = []   # (session_id, tenor, par_rate)
    treasury_rows = []    # (session_id, tenor, yield_rate)
    spread_bp_by_session = {t: [] for t in SCREENED_TENORS}  # kept for tests/diagnostics

    for session_id in range(num_sessions):
        if session_id > 0:
            level += rng.gauss(0, LEVEL_DAILY_VOL)
            level = min(max(level, LEVEL_MIN), LEVEL_MAX)

        swap_rate_this_session = {}
        for tenor in TENORS:
            shape = _nelson_siegel_shape(tenor) * CURVE_SLOPE
            idio = rng.gauss(0, TENOR_IDIO_VOL)
            par_rate = level + shape + idio
            swap_rate_rows.append((session_id, tenor, par_rate))
            swap_rate_this_session[tenor] = par_rate

        for tenor in SCREENED_TENORS:
            params = SPREAD_OU_PARAMS[tenor]
            if session_id > 0:
                shock = rng.gauss(0, params["vol_bp"])
                spread_level[tenor] += params["kappa"] * (params["mean_bp"] - spread_level[tenor]) + shock

            treasury_yield = swap_rate_this_session[tenor] - spread_level[tenor] / 10000.0
            treasury_rows.append((session_id, tenor, treasury_yield))
            spread_bp_by_session[tenor].append(spread_level[tenor])

    return swap_rate_rows, treasury_rows, spread_bp_by_session


def populate_rates(conn, num_sessions: int, seed: int = SEED) -> None:
    swap_rate_rows, treasury_rows, _ = generate_sessions(num_sessions, seed=seed)
    cur = conn.cursor()
    cur.execute("DELETE FROM swap_rates")
    cur.execute("DELETE FROM treasury_yields")
    cur.executemany("INSERT INTO swap_rates (session_id, tenor, par_rate) VALUES (?, ?, ?)", swap_rate_rows)
    cur.executemany("INSERT INTO treasury_yields (session_id, tenor, yield_rate) VALUES (?, ?, ?)", treasury_rows)
    conn.commit()
