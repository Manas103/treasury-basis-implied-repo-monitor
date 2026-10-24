"""Swap spread and invoice spread relative-value screener.

Five spread series are screened every session:

- `swap_spread_2`, `swap_spread_5`, `swap_spread_10`, `swap_spread_30`:
  the simulated swap par rate at that tenor minus the simulated on-the-run
  Treasury yield at the same tenor, in basis points.
- `invoice_spread_10`: the CTD note's yield-to-maturity (solved from its
  simulated cash price, `bond_math.solve_ytm`) minus the 10-year swap par
  rate, in basis points. This is the standard invoice-spread framing: the
  futures contract delivers the CTD note, so the futures-versus-swap
  package's spread is the CTD note's own yield versus the matching-tenor
  swap rate.

Both legs of every package are sized DV01-neutral (`dv01_neutral_ratio`): for the
swap-spread series that is a matching-tenor Treasury-proxy bond against
the swap's own PVBP; for the invoice spread it is the CTD note (via
`bond_math.bond_dv01`) against the 10-year swap.

Each series gets a rolling z-score against a trailing, strictly-prior
60-session window (no lookahead: session t's z-score only ever uses
sessions [t-60, t)). |z| >= 2 flags a dislocation. A flagged dislocation
survives the cost filter only if its distance back to the rolling mean, in
basis points, exceeds `half_spread_bp` (an illustrative round-trip
bid-ask-crossing cost for the package) plus that session's repo-carry cost
(`repo_carry_bp`, driven by the session's own simulated repo rate, scaled
by HOLDING_DAYS and the disclosed CARRY_COEFF illustrative assumption).
Neither the window length, the z threshold, nor the two cost assumptions
were chosen after looking at how many dislocations would survive; they are
fixed here before `scripts/run_screener.py` was ever run.
"""
from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass

from treasury_monitor import bond_math
from treasury_monitor.basket import BASKET, years_to_maturity
from treasury_monitor.swap_curve import SwapCurve, bootstrap

ROLLING_WINDOW = 60
Z_THRESHOLD = 2.0
HALF_SPREAD_BP = 1.5  # illustrative round-trip bid/ask crossing cost for the DV01-neutral package
HOLDING_DAYS = 60  # one trading quarter, the same holding-period convention futures-strategy-backtester uses for its walk-forward window
CARRY_COEFF = 0.15  # illustrative: fraction of the gross repo rate that flows through to net package carry

SCREENED_TENORS = (2, 5, 10, 30)
_NOTE_BY_ID = {n.note_id: n for n in BASKET}


@dataclass
class SessionSpreads:
    session_id: int
    series: dict  # series_name -> spread_bp
    repo_rate: float


def _load_sessions(conn: sqlite3.Connection) -> list[tuple]:
    cur = conn.cursor()
    cur.execute("SELECT session_id, sim_date, repo_rate FROM sessions ORDER BY session_id")
    return cur.fetchall()


def _load_swap_curve(conn: sqlite3.Connection, session_id: int) -> SwapCurve:
    cur = conn.cursor()
    cur.execute("SELECT tenor, par_rate FROM swap_rates WHERE session_id = ?", (session_id,))
    par_rates = {tenor: rate for tenor, rate in cur.fetchall()}
    return bootstrap(par_rates)


def _load_treasury_yields(conn: sqlite3.Connection, session_id: int) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT tenor, yield_rate FROM treasury_yields WHERE session_id = ?", (session_id,))
    return {tenor: y for tenor, y in cur.fetchall()}


def _load_ctd(conn: sqlite3.Connection, session_id: int):
    cur = conn.cursor()
    cur.execute(
        "SELECT note_id, purchase_dirty FROM results WHERE session_id = ? AND is_ctd = 1",
        (session_id,),
    )
    note_id, purchase_dirty = cur.fetchone()
    return note_id, purchase_dirty


def compute_session_spreads(conn: sqlite3.Connection, session_id: int, sim_date) -> SessionSpreads:
    curve = _load_swap_curve(conn, session_id)
    treasury_yields = _load_treasury_yields(conn, session_id)

    series = {}
    for tenor in SCREENED_TENORS:
        swap_rate = curve.par_rate_at(tenor)
        series[f"swap_spread_{tenor}"] = (swap_rate - treasury_yields[tenor]) * 10000.0

    note_id, purchase_dirty = _load_ctd(conn, session_id)
    note = _NOTE_BY_ID[note_id]
    ytm_years = years_to_maturity(note, sim_date)
    ctd_ytm = bond_math.solve_ytm(purchase_dirty, note.coupon_rate, ytm_years)
    series["invoice_spread_10"] = (ctd_ytm - curve.par_rate_at(10)) * 10000.0

    cur = conn.cursor()
    cur.execute("SELECT repo_rate FROM sessions WHERE session_id = ?", (session_id,))
    (repo_rate,) = cur.fetchone()

    return SessionSpreads(session_id=session_id, series=series, repo_rate=repo_rate)


def dv01_neutral_ratio(series_name: str, session_id: int, conn: sqlite3.Connection, sim_date) -> tuple[float, float]:
    """Real DV01-neutral leg sizing, used both by the screener's own
    bookkeeping and by tests/test_screener.py's invariant check: given
    leg_a sized at 100 notional, leg_b_notional makes leg_b's dollar DV01
    match leg_a's exactly."""
    curve = _load_swap_curve(conn, session_id)
    treasury_yields = _load_treasury_yields(conn, session_id)

    if series_name.startswith("swap_spread_"):
        tenor = int(series_name.rsplit("_", 1)[1])
        leg_a_dv01 = bond_math.bond_dv01(treasury_yields[tenor], treasury_yields[tenor], float(tenor))
        leg_b_dv01 = curve.pvbp(tenor) * 0.01
    else:
        note_id, purchase_dirty = _load_ctd(conn, session_id)
        note = _NOTE_BY_ID[note_id]
        ytm_years = years_to_maturity(note, sim_date)
        ctd_ytm = bond_math.solve_ytm(purchase_dirty, note.coupon_rate, ytm_years)
        leg_a_dv01 = bond_math.bond_dv01(ctd_ytm, note.coupon_rate, ytm_years)
        leg_b_dv01 = curve.pvbp(10) * 0.01

    leg_a_notional = 100.0
    leg_b_notional = leg_a_notional * leg_a_dv01 / leg_b_dv01
    return leg_a_notional * leg_a_dv01, leg_b_notional * leg_b_dv01


def run_screener(conn: sqlite3.Connection) -> dict:
    sessions = _load_sessions(conn)
    import datetime as _dt

    all_series_names = [f"swap_spread_{t}" for t in SCREENED_TENORS] + ["invoice_spread_10"]
    history = {name: [] for name in all_series_names}
    rows_to_write = []

    total_dislocations = 0
    total_survivors = 0

    for session_id, sim_date_s, repo_rate in sessions:
        sim_date = _dt.date.fromisoformat(sim_date_s)
        snap = compute_session_spreads(conn, session_id, sim_date)

        for name in all_series_names:
            spread_bp = snap.series[name]
            window = history[name][-ROLLING_WINDOW:]

            rolling_mean = rolling_std = zscore = None
            is_dislocation = 0
            cost_bp = None
            survives = 0

            if len(window) == ROLLING_WINDOW:
                rolling_mean = statistics.mean(window)
                rolling_std = statistics.pstdev(window)
                if rolling_std > 0:
                    zscore = (spread_bp - rolling_mean) / rolling_std
                    if abs(zscore) >= Z_THRESHOLD:
                        is_dislocation = 1
                        total_dislocations += 1
                        repo_carry_bp = repo_rate * 10000.0 * (HOLDING_DAYS / 360.0) * CARRY_COEFF
                        cost_bp = HALF_SPREAD_BP + repo_carry_bp
                        if abs(spread_bp - rolling_mean) > cost_bp:
                            survives = 1
                            total_survivors += 1

            rows_to_write.append(
                (session_id, name, spread_bp, rolling_mean, rolling_std, zscore, is_dislocation, cost_bp, survives)
            )
            history[name].append(spread_bp)

    cur = conn.cursor()
    cur.execute("DELETE FROM spread_series")
    cur.executemany(
        """INSERT INTO spread_series
           (session_id, series_name, spread_bp, rolling_mean_bp, rolling_std_bp, zscore, is_dislocation, cost_bp, survives_filter)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows_to_write,
    )
    conn.commit()

    return {
        "num_sessions": len(sessions),
        "num_series": len(all_series_names),
        "total_dislocations": total_dislocations,
        "total_survivors": total_survivors,
    }
