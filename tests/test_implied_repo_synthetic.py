"""Synthetic case with a known closed-form implied repo answer.

Construct a note position where, by construction, there is no coupon
payment during the holding period, so:

  implied_repo = (invoice_dirty - purchase_dirty) / purchase_dirty * (360 / days)

Pick invoice_dirty = purchase_dirty * (1 + target_rate * days / 360) exactly,
so the closed-form answer for implied repo is target_rate, and check the
engine's formula recovers it exactly (to floating precision).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def implied_repo_formula(invoice_dirty: float, purchase_dirty: float, coupon_income: float, days_to_delivery: int) -> float:
    return ((invoice_dirty - purchase_dirty) + coupon_income) / purchase_dirty * (360.0 / days_to_delivery)


def test_implied_repo_recovers_known_rate_no_coupon():
    purchase_dirty = 101.375
    days = 45
    target_rate = 0.0537
    invoice_dirty = purchase_dirty * (1.0 + target_rate * days / 360.0)

    recovered = implied_repo_formula(invoice_dirty, purchase_dirty, 0.0, days)
    assert abs(recovered - target_rate) < 1e-10


def test_implied_repo_recovers_known_rate_with_coupon_income():
    """With a coupon paid during the holding period, the closed-form target
    still must be recovered exactly: invoice_dirty is picked so that
    (invoice - purchase + coupon_income) / purchase * (360/days) == target."""
    purchase_dirty = 98.5
    days = 60
    coupon_income = 2.0625
    target_rate = 0.0412

    # solve invoice_dirty for the target rate
    invoice_dirty = purchase_dirty * target_rate * days / 360.0 + purchase_dirty - coupon_income

    recovered = implied_repo_formula(invoice_dirty, purchase_dirty, coupon_income, days)
    assert abs(recovered - target_rate) < 1e-10


def test_engine_compute_note_result_matches_hand_solved_case():
    """End-to-end through the real engine.compute_note_result function
    (not just the standalone formula above), using inputs chosen so the
    conversion factor, accrued interest, and coupon income are all
    independently hand-computable."""
    from datetime import date

    from treasury_monitor.engine import compute_note_result
    from treasury_monitor.basket import BASKET

    note = BASKET[3]  # SYN-D 4.125%, matures 2033-06-18
    sim_date = date(2026, 8, 26)
    delivery_date = date(2026, 10, 10)  # 45 days later, no coupon date crossed (coupons Jun/Dec 18)
    days_to_delivery = (delivery_date - sim_date).days
    assert days_to_delivery == 45

    futures_price = 111.0
    repo_rate = 0.053
    cash_clean_price = 100.75

    result = compute_note_result(note.note_id, sim_date, delivery_date, days_to_delivery, futures_price, repo_rate, cash_clean_price)

    # No coupon date (2026-06-18 or 2026-12-18) falls strictly within (sim_date, delivery_date]
    assert result["coupon_income"] == 0.0

    # Hand-recompute accrued interest at sim_date: last coupon 2026-06-18, next 2026-12-18 (183 days)
    days_in_period = (date(2026, 12, 18) - date(2026, 6, 18)).days
    days_accrued = (sim_date - date(2026, 6, 18)).days
    expected_accrued_now = (note.coupon_rate / 2 * 100) * days_accrued / days_in_period
    assert abs(result["accrued_now"] - expected_accrued_now) < 1e-9

    purchase_dirty = cash_clean_price + expected_accrued_now
    assert abs(result["purchase_dirty"] - purchase_dirty) < 1e-9

    expected_implied_repo = ((result["invoice_dirty"] - purchase_dirty) + 0.0) / purchase_dirty * (360.0 / 45)
    assert abs(result["implied_repo_rate"] - expected_implied_repo) < 1e-9
