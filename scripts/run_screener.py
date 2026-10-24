#!/usr/bin/env python
"""Builds the basket basis/implied-repo database (same as run_simulation.py),
simulates the swap curve and Treasury yields, then runs the swap spread and
invoice spread relative-value screener.

Usage: python scripts/run_screener.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import db as db_module
from treasury_monitor import market_sim
from treasury_monitor import rates_market_sim
from treasury_monitor.engine import run_engine
from treasury_monitor.screener import (
    CARRY_COEFF,
    HALF_SPREAD_BP,
    HOLDING_DAYS,
    ROLLING_WINDOW,
    Z_THRESHOLD,
    run_screener,
)


def main() -> None:
    print(f"Simulating {market_sim.NUM_SESSIONS} basis sessions (seed={market_sim.SEED})...")
    market_sim.populate_db()

    conn = db_module.connect()
    num_sessions = run_engine(conn)
    print(f"Basis engine computed results for {num_sessions} sessions.")

    print(f"Simulating swap curve (14 tenors) and 2/5/10/30y Treasury yields (seed={rates_market_sim.SEED})...")
    rates_market_sim.populate_rates(conn, num_sessions=num_sessions)

    print(f"Running screener: rolling window {ROLLING_WINDOW} sessions, |z| >= {Z_THRESHOLD}, "
          f"half-spread {HALF_SPREAD_BP}bp + repo carry ({HOLDING_DAYS}d holding, {CARRY_COEFF} coeff)...")
    summary = run_screener(conn)

    print(f"Sessions: {summary['num_sessions']}")
    print(f"Series screened: {summary['num_series']} "
          f"(swap_spread_2, swap_spread_5, swap_spread_10, swap_spread_30, invoice_spread_10)")
    print(f"Two-sigma dislocations flagged: {summary['total_dislocations']}")
    print(f"Dislocations surviving half-spread + repo-carry filter: {summary['total_survivors']}")
    if summary["total_dislocations"] > 0:
        pct = 100.0 * summary["total_survivors"] / summary["total_dislocations"]
        print(f"Survival rate: {summary['total_survivors']}/{summary['total_dislocations']} ({pct:.1f}%)")

    # Reprice check: every one of the 14 swap curve inputs, on a sample of sessions
    from treasury_monitor.swap_curve import TENORS, bootstrap

    cur = conn.cursor()
    max_reprice_err_bp = 0.0
    sample_sessions = [0, num_sessions // 2, num_sessions - 1]
    for session_id in sample_sessions:
        cur.execute("SELECT tenor, par_rate FROM swap_rates WHERE session_id = ?", (session_id,))
        par_rates = {t: r for t, r in cur.fetchall()}
        curve = bootstrap(par_rates)
        for t in TENORS:
            err_bp = abs(curve.implied_par_rate(t) - par_rates[t]) * 10000.0
            max_reprice_err_bp = max(max_reprice_err_bp, err_bp)
    print(f"Max swap curve input repricing error across {len(sample_sessions)} sampled sessions, "
          f"all {len(TENORS)} tenors: {max_reprice_err_bp:.6f}bp")

    # DV01-neutral sizing check, one representative session per series
    from treasury_monitor.screener import SCREENED_TENORS, dv01_neutral_ratio
    import datetime as _dt

    cur.execute("SELECT session_id, sim_date FROM sessions ORDER BY session_id")
    sim_dates = {sid: _dt.date.fromisoformat(d) for sid, d in cur.fetchall()}
    check_session = num_sessions - 1
    series_names = [f"swap_spread_{t}" for t in SCREENED_TENORS] + ["invoice_spread_10"]
    max_dv01_mismatch = 0.0
    for name in series_names:
        dv01_a, dv01_b = dv01_neutral_ratio(name, check_session, conn, sim_dates[check_session])
        max_dv01_mismatch = max(max_dv01_mismatch, abs(dv01_a - dv01_b))
    print(f"Max |leg_a_dv01 - leg_b_dv01| after DV01-neutral sizing, session {check_session}, "
          f"all {len(series_names)} series: {max_dv01_mismatch:.2e}")

    conn.close()


if __name__ == "__main__":
    main()
