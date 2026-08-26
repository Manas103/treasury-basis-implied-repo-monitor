"""Funding-shock comparative-statics experiment.

Holds futures price and every note's cash price fixed at the base scenario
(the values already stored in results/note_prices for each session) and
recomputes net basis with the overnight repo rate shifted by +25bp. Only
the financing_cost term changes (coupon income and gross basis are
unaffected by financing rate), so this isolates exactly the carry channel,
which is the point: it is a controlled comparative-statics experiment, not
a resimulation with new noise, so the entire measured shift in net basis is
attributable to the funding rate move rather than confounded by fresh price
draws.
"""
from __future__ import annotations

import sqlite3
import statistics

from treasury_monitor.engine import TICKS_PER_POINT

FUNDING_SHOCK = 0.0025  # 25bp


def run_funding_shock(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT r.session_id, r.note_id, r.purchase_dirty, s.days_to_delivery
           FROM results r JOIN sessions s ON r.session_id = s.session_id
           ORDER BY r.session_id, r.note_id"""
    )
    rows = cur.fetchall()

    all_deltas = []
    per_session_medians = []
    current_session = None
    session_deltas: list[float] = []

    def flush_session():
        if session_deltas:
            per_session_medians.append(statistics.median(session_deltas))

    for session_id, note_id, purchase_dirty, days_to_delivery in rows:
        if session_id != current_session:
            flush_session()
            session_deltas = []
            current_session = session_id

        # net_basis = gross_basis - carry = gross_basis - (coupon_income - financing_cost)
        # so d(net_basis)/d(financing_cost) = +1: a higher funding rate raises financing
        # cost, shrinks carry, and pushes net basis up by exactly that amount.
        extra_financing_points = purchase_dirty * FUNDING_SHOCK * days_to_delivery / 360.0
        delta_ticks = extra_financing_points * TICKS_PER_POINT

        all_deltas.append(delta_ticks)
        session_deltas.append(delta_ticks)

    flush_session()

    return {
        "num_observations": len(all_deltas),
        "num_sessions": len(per_session_medians),
        "median_delta_ticks_all_observations": statistics.median(all_deltas),
        "median_of_session_medians_ticks": statistics.median(per_session_medians),
        "mean_delta_ticks_all_observations": statistics.mean(all_deltas),
        "min_delta_ticks": min(all_deltas),
        "max_delta_ticks": max(all_deltas),
    }
