"""Independent reference-oracle recomputation of cheapest-to-deliver (CTD).

Deliberately does NOT import anything from engine.py, conversion_factor.py,
or daycount.py. It re-derives note coupon/maturity data straight from the
`notes` SQL table (not the basket.py Python objects) and reimplements every
formula from scratch, using different algorithmic techniques than the main
engine wherever there is a choice, specifically so a bug in one code path is
unlikely to be mirrored in the other:

- Conversion factor: closed-form geometric-series annuity formula, versus
  the main engine's term-by-term summation loop.
- Coupon-date bracketing: a days/182.5 estimate-then-correct search using
  `calendar.monthrange` for month-end clamping, versus the main engine's
  plain backward walk using explicit next-month-first-day arithmetic.

If the two independently-coded implementations agree on which note is CTD
for all 500 sessions, that is a meaningful cross-check, not a tautology,
because the code paths share no functions.
"""
from __future__ import annotations

import calendar
import sqlite3
from datetime import date


def oracle_add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    mo = m % 12 + 1
    last_day = calendar.monthrange(y, mo)[1]
    day = min(d.day, last_day)
    return date(y, mo, day)


def oracle_coupon_bracket(as_of: date, maturity: date) -> tuple[date, date]:
    """Estimate-then-correct search for the coupon dates bracketing as_of,
    independent in structure from daycount.coupon_bracket's plain backward walk.

    Finds the minimal k >= 0 such that (maturity - 6k months) <= as_of; that
    date is prev_date, and (maturity - 6(k-1) months), or maturity if k == 0,
    is next_date."""
    total_days = (maturity - as_of).days

    def back(k_steps: int) -> date:
        return oracle_add_months(maturity, -6 * k_steps)

    k = max(int(total_days // 182.5), 0)
    while back(k) > as_of:
        k += 1
    while k > 0 and back(k - 1) <= as_of:
        k -= 1

    prev = back(k)
    next_date = back(k - 1) if k > 0 else maturity
    return prev, next_date


def oracle_accrued_interest(coupon_rate: float, as_of: date, maturity: date, face: float = 100.0) -> float:
    prev_date, next_date = oracle_coupon_bracket(as_of, maturity)
    days_in_period = (next_date - prev_date).days
    days_accrued = (as_of - prev_date).days
    semiannual = coupon_rate / 2.0 * face
    if days_in_period == 0:
        return 0.0
    return semiannual * days_accrued / days_in_period


def oracle_coupons_paid_between(coupon_rate: float, start: date, end: date, maturity: date, face: float = 100.0) -> float:
    if start >= end:
        return 0.0
    semiannual = coupon_rate / 2.0 * face
    total = 0.0
    _, next_after_start = oracle_coupon_bracket(start, maturity)
    cd = next_after_start
    while cd <= end and cd <= maturity:
        total += semiannual
        cd = oracle_add_months(cd, 6)
    return total


def oracle_conversion_factor(coupon_rate: float, years_to_maturity: float, face: float = 100.0) -> float:
    """Closed-form geometric-series PV, independent of the main engine's
    term-by-term summation loop in conversion_factor.py."""
    n = max(round(years_to_maturity * 2), 1)
    c = coupon_rate / 2.0 * face
    y = 0.03
    discount_n = (1.0 + y) ** -n
    pv = c * (1.0 - discount_n) / y + face * discount_n
    return pv / face


def run_oracle_diff(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()

    cur.execute("SELECT note_id, coupon_rate, maturity_date FROM notes ORDER BY note_id")
    notes = {row[0]: (row[1], date.fromisoformat(row[2])) for row in cur.fetchall()}

    cur.execute("SELECT session_id, sim_date, futures_price, repo_rate, days_to_delivery, delivery_date FROM sessions ORDER BY session_id")
    sessions = cur.fetchall()

    matches = 0
    mismatches = []
    closest_margins = []  # (margin, session_id) smallest gap between best and 2nd best implied repo

    for session_id, sim_date_s, futures_price, repo_rate, days_to_delivery, delivery_date_s in sessions:
        sim_date = date.fromisoformat(sim_date_s)
        delivery_date = date.fromisoformat(delivery_date_s)

        cur.execute("SELECT note_id, cash_clean_price FROM note_prices WHERE session_id = ?", (session_id,))
        price_rows = cur.fetchall()

        implied_repos = []
        for note_id, cash_clean_price in price_rows:
            coupon_rate, maturity_date = notes[note_id]
            years_to_maturity = (maturity_date - delivery_date).days / 365.25
            cf = oracle_conversion_factor(coupon_rate, years_to_maturity)

            accrued_now = oracle_accrued_interest(coupon_rate, sim_date, maturity_date)
            accrued_delivery = oracle_accrued_interest(coupon_rate, delivery_date, maturity_date)
            coupon_income = oracle_coupons_paid_between(coupon_rate, sim_date, delivery_date, maturity_date)

            purchase_dirty = cash_clean_price + accrued_now
            invoice_dirty = futures_price * cf + accrued_delivery

            implied_repo = ((invoice_dirty - purchase_dirty) + coupon_income) / purchase_dirty * (360.0 / days_to_delivery)
            implied_repos.append((implied_repo, note_id))

        implied_repos.sort(key=lambda t: (-t[0], t[1]))
        oracle_ctd = implied_repos[0][1]
        margin = implied_repos[0][0] - implied_repos[1][0] if len(implied_repos) > 1 else float("inf")
        closest_margins.append((margin, session_id))

        cur.execute("SELECT note_id FROM results WHERE session_id = ? AND is_ctd = 1", (session_id,))
        engine_ctd = cur.fetchone()[0]

        if oracle_ctd == engine_ctd:
            matches += 1
        else:
            mismatches.append({"session_id": session_id, "engine_ctd": engine_ctd, "oracle_ctd": oracle_ctd, "margin": margin})

    closest_margins.sort(key=lambda t: t[0])

    return {
        "total_sessions": len(sessions),
        "matches": matches,
        "mismatches": mismatches,
        "closest_margins": closest_margins[:5],
    }
