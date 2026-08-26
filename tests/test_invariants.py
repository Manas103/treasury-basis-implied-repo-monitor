from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_invoice_price_identity_holds_exactly(small_db):
    """invoice_dirty must equal futures_price * conversion_factor +
    accrued_delivery exactly (to floating precision) for every issue in
    every session: this is a conservation identity by construction, not a
    measured result, and it should never fail."""
    cur = small_db.cursor()
    cur.execute(
        """SELECT r.invoice_dirty, s.futures_price, r.conversion_factor, r.accrued_delivery
           FROM results r JOIN sessions s ON r.session_id = s.session_id"""
    )
    rows = cur.fetchall()
    assert len(rows) > 0
    for invoice_dirty, futures_price, cf, accrued_delivery in rows:
        expected = futures_price * cf + accrued_delivery
        assert abs(invoice_dirty - expected) < 1e-9


def test_every_issue_has_a_result_every_session(small_db):
    """Coverage claim: net basis and implied repo are computed for every
    issue in the basket, every session."""
    cur = small_db.cursor()
    cur.execute("SELECT COUNT(*) FROM sessions")
    num_sessions = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM notes")
    num_notes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM results")
    num_results = cur.fetchone()[0]
    assert num_results == num_sessions * num_notes

    cur.execute("SELECT COUNT(DISTINCT note_id) FROM results")
    assert cur.fetchone()[0] == num_notes


def test_exactly_one_ctd_per_session(small_db):
    cur = small_db.cursor()
    cur.execute("SELECT session_id, COUNT(*) FROM results WHERE is_ctd = 1 GROUP BY session_id")
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM sessions")
    num_sessions = cur.fetchone()[0]
    assert len(rows) == num_sessions
    for session_id, count in rows:
        assert count == 1


def test_ctd_has_the_max_implied_repo_in_its_session(small_db):
    cur = small_db.cursor()
    cur.execute("SELECT DISTINCT session_id FROM results")
    session_ids = [r[0] for r in cur.fetchall()]
    for session_id in session_ids:
        cur.execute("SELECT implied_repo_rate, is_ctd FROM results WHERE session_id = ?", (session_id,))
        rows = cur.fetchall()
        max_repo = max(r[0] for r in rows)
        ctd_repo = [r[0] for r in rows if r[1] == 1][0]
        assert abs(ctd_repo - max_repo) < 1e-12
