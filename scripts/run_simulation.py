#!/usr/bin/env python
"""Regenerate data/sessions.db and run the basis/implied-repo engine.

Usage: python scripts/run_simulation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import db as db_module
from treasury_monitor import market_sim
from treasury_monitor.engine import run_engine


def main() -> None:
    print(f"Simulating {market_sim.NUM_SESSIONS} sessions (seed={market_sim.SEED})...")
    market_sim.populate_db()
    print(f"Wrote sessions/notes/note_prices to {db_module.DEFAULT_DB_PATH}")

    conn = db_module.connect()
    num_sessions = run_engine(conn)
    print(f"Engine computed results for {num_sessions} sessions.")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM results")
    total_rows = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT note_id) FROM results")
    distinct_notes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM notes")
    total_notes = cur.fetchone()[0]

    print(f"Total (session, note) result rows: {total_rows}")
    print(f"Distinct notes with results: {distinct_notes} / {total_notes} in basket")
    print(f"Expected rows if every issue is covered every session: {num_sessions * total_notes}")
    coverage_ok = (total_rows == num_sessions * total_notes) and (distinct_notes == total_notes)
    print(f"Coverage claim (every issue, every session): {coverage_ok}")

    cur.execute("SELECT COUNT(*) FROM results WHERE is_ctd = 1")
    ctd_rows = cur.fetchone()[0]
    print(f"Sessions with exactly one CTD flagged: check -> {ctd_rows} (should equal {num_sessions})")

    # invariant: invoice_dirty == futures_price * conversion_factor + accrued_delivery, exactly
    cur.execute(
        """SELECT r.session_id, r.note_id, r.invoice_dirty, s.futures_price, r.conversion_factor, r.accrued_delivery
           FROM results r JOIN sessions s ON r.session_id = s.session_id"""
    )
    max_identity_error = 0.0
    for session_id, note_id, invoice_dirty, futures_price, cf, accrued_delivery in cur.fetchall():
        expected = futures_price * cf + accrued_delivery
        max_identity_error = max(max_identity_error, abs(invoice_dirty - expected))
    print(f"Max |invoice_dirty - (futures_price*CF + accrued_delivery)| across all rows: {max_identity_error:.2e}")

    cur.execute("SELECT MIN(net_basis_ticks), MAX(net_basis_ticks) FROM results")
    min_nb, max_nb = cur.fetchone()
    print(f"Net basis range across all rows: {min_nb:.3f} to {max_nb:.3f} ticks")

    conn.close()


if __name__ == "__main__":
    main()
