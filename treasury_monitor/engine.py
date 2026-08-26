"""Main basis / implied repo computation engine.

For every session and every note in the basket:

  invoice_dirty      = futures_price * conversion_factor + accrued_delivery
  purchase_dirty      = cash_clean_price + accrued_now
  gross_basis         = cash_clean_price - futures_price * conversion_factor   (points)
  financing_cost      = purchase_dirty * repo_rate * days_to_delivery / 360    (points)
  carry               = coupon_income_during_holding - financing_cost         (points)
  net_basis           = gross_basis - carry                                   (points)
  implied_repo_rate   = ((invoice_dirty - purchase_dirty) + coupon_income)
                        / purchase_dirty * (360 / days_to_delivery)

Cheapest-to-deliver (CTD) is the note with the highest implied repo rate in
the basket for that session (ties broken by lowest note_id, which never
happens with continuous synthetic noise but is defined for determinism).

Net basis over financing cost: net basis (not gross basis) is the ranking
quantity a repo desk actually cares about, because gross basis ignores the
cost of carrying the position to delivery; two notes with identical gross
basis can have very different economics once carry is netted out. Implied
repo rate is used to pick CTD rather than raw net basis because it is the
quantity market participants actually compare (the annualized breakeven
financing rate of the basis trade), and it normalizes for the size of the
purchase price across notes of different coupon/price levels, whereas net
basis in price points does not.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from treasury_monitor import db as db_module
from treasury_monitor.basket import BASKET, years_to_maturity
from treasury_monitor.conversion_factor import conversion_factor
from treasury_monitor.daycount import accrued_interest, coupons_paid_between

TICKS_PER_POINT = 32.0

_NOTE_BY_ID = {n.note_id: n for n in BASKET}


def compute_note_result(note_id: int, sim_date: date, delivery_date: date, days_to_delivery: int,
                         futures_price: float, repo_rate: float, cash_clean_price: float) -> dict:
    note = _NOTE_BY_ID[note_id]

    ytm_at_delivery = years_to_maturity(note, delivery_date)
    cf = conversion_factor(note.coupon_rate, ytm_at_delivery)

    accrued_now = accrued_interest(note.coupon_rate, sim_date, note.maturity_date)
    accrued_delivery = accrued_interest(note.coupon_rate, delivery_date, note.maturity_date)
    coupon_income = coupons_paid_between(note.coupon_rate, sim_date, delivery_date, note.maturity_date)

    purchase_dirty = cash_clean_price + accrued_now
    invoice_dirty = futures_price * cf + accrued_delivery

    gross_basis_points = cash_clean_price - futures_price * cf
    financing_cost_points = purchase_dirty * repo_rate * days_to_delivery / 360.0
    carry_points = coupon_income - financing_cost_points
    net_basis_points = gross_basis_points - carry_points
    net_basis_ticks = net_basis_points * TICKS_PER_POINT

    implied_repo_rate = (
        ((invoice_dirty - purchase_dirty) + coupon_income) / purchase_dirty * (360.0 / days_to_delivery)
    )

    return {
        "note_id": note_id,
        "conversion_factor": cf,
        "accrued_now": accrued_now,
        "accrued_delivery": accrued_delivery,
        "coupon_income": coupon_income,
        "purchase_dirty": purchase_dirty,
        "invoice_dirty": invoice_dirty,
        "gross_basis_points": gross_basis_points,
        "financing_cost_points": financing_cost_points,
        "carry_points": carry_points,
        "net_basis_points": net_basis_points,
        "net_basis_ticks": net_basis_ticks,
        "implied_repo_rate": implied_repo_rate,
    }


def run_engine(conn: sqlite3.Connection) -> int:
    """Read sessions/note_prices, compute results for every note/session,
    write to the results table. Returns the number of sessions processed."""
    cur = conn.cursor()
    cur.execute("SELECT session_id, sim_date, futures_price, repo_rate, days_to_delivery, delivery_date FROM sessions ORDER BY session_id")
    sessions = cur.fetchall()

    cur.execute("DELETE FROM results")

    num_sessions = 0
    for session_id, sim_date_s, futures_price, repo_rate, days_to_delivery, delivery_date_s in sessions:
        sim_date = date.fromisoformat(sim_date_s)
        delivery_date = date.fromisoformat(delivery_date_s)

        cur.execute("SELECT note_id, cash_clean_price FROM note_prices WHERE session_id = ?", (session_id,))
        price_rows = cur.fetchall()

        results = []
        for note_id, cash_clean_price in price_rows:
            r = compute_note_result(note_id, sim_date, delivery_date, days_to_delivery, futures_price, repo_rate, cash_clean_price)
            results.append(r)

        best = max(results, key=lambda r: (r["implied_repo_rate"], -r["note_id"]))
        ctd_note_id = best["note_id"]

        for r in results:
            cur.execute(
                """INSERT INTO results
                (session_id, note_id, conversion_factor, accrued_now, accrued_delivery, coupon_income,
                 purchase_dirty, invoice_dirty, gross_basis_points, financing_cost_points, carry_points,
                 net_basis_points, net_basis_ticks, implied_repo_rate, is_ctd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, r["note_id"], r["conversion_factor"], r["accrued_now"], r["accrued_delivery"],
                    r["coupon_income"], r["purchase_dirty"], r["invoice_dirty"], r["gross_basis_points"],
                    r["financing_cost_points"], r["carry_points"], r["net_basis_points"], r["net_basis_ticks"],
                    r["implied_repo_rate"], 1 if r["note_id"] == ctd_note_id else 0,
                ),
            )
        num_sessions += 1

    conn.commit()
    return num_sessions
