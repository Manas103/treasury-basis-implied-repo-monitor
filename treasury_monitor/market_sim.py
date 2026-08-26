"""Synthetic market simulator: 500 trading sessions of futures price, repo
rate, and per-note cash prices for the deliverable basket.

Every input is synthetic. Design choices, held fixed so results are
reproducible (seeded RNG):

- Futures price: a bounded random walk around a 111.50 start, daily
  increments ~N(0, 0.15) points, which is roughly the historical order of
  magnitude of ZN daily point moves.
- Repo (overnight funding) rate: a bounded random walk around 5.30% with
  tiny daily increments ~N(0, 0.0002), clipped to stay within a plausible
  [3%, 7%] band.
- Each note's cash clean price = futures_price * conversion_factor +
  basis_level_points (a fixed structural offset per note) + small noise.
  This keeps gross basis small and realistic instead of letting prices
  drift into arbitrage-free-violating territory.
- Days to delivery cycles 90 -> 1 and resets, approximating the last
  quarter of a futures contract's life (where basis trading concentrates),
  repeating across roughly 5-6 contract cycles over the 500 sessions.
- Trading sessions are business days (Mon-Fri), skipping weekends.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from treasury_monitor import db as db_module
from treasury_monitor.basket import BASKET, SIM_START_DATE, years_to_maturity
from treasury_monitor.conversion_factor import conversion_factor

NUM_SESSIONS = 500
SEED = 42

FUTURES_START = 111.50
FUTURES_DAILY_VOL = 0.15
REPO_START = 0.0530
REPO_DAILY_VOL = 0.0002
REPO_MIN, REPO_MAX = 0.03, 0.07
NOTE_NOISE_VOL = 0.008
DELIVERY_CYCLE_DAYS = 90


@dataclass
class SessionRow:
    session_id: int
    sim_date: date
    futures_price: float
    repo_rate: float
    days_to_delivery: int
    delivery_date: date


def next_business_day(d: date) -> date:
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:  # Saturday=5, Sunday=6
        nd += timedelta(days=1)
    return nd


def generate_sessions(num_sessions: int = NUM_SESSIONS, seed: int = SEED):
    rng = random.Random(seed)
    sim_date = SIM_START_DATE
    futures_price = FUTURES_START
    repo_rate = REPO_START

    sessions: list[SessionRow] = []
    note_prices: dict[int, list[float]] = {n.note_id: [] for n in BASKET}

    for i in range(num_sessions):
        if i > 0:
            sim_date = next_business_day(sim_date)
            futures_price += rng.gauss(0, FUTURES_DAILY_VOL)
            repo_rate += rng.gauss(0, REPO_DAILY_VOL)
            repo_rate = min(max(repo_rate, REPO_MIN), REPO_MAX)

        days_to_delivery = DELIVERY_CYCLE_DAYS - (i % DELIVERY_CYCLE_DAYS)
        delivery_date = sim_date + timedelta(days=days_to_delivery)

        sessions.append(
            SessionRow(
                session_id=i,
                sim_date=sim_date,
                futures_price=futures_price,
                repo_rate=repo_rate,
                days_to_delivery=days_to_delivery,
                delivery_date=delivery_date,
            )
        )

        for note in BASKET:
            ytm = years_to_maturity(note, delivery_date)
            cf = conversion_factor(note.coupon_rate, ytm)
            noise = rng.gauss(0, NOTE_NOISE_VOL)
            cash_price = futures_price * cf + note.basis_level_points + noise
            note_prices[note.note_id].append(cash_price)

    return sessions, note_prices


def populate_db(db_path=db_module.DEFAULT_DB_PATH, num_sessions: int = NUM_SESSIONS, seed: int = SEED) -> None:
    conn = db_module.connect(db_path)
    db_module.reset_schema(conn)

    conn.executemany(
        "INSERT INTO notes (note_id, name, coupon_rate, maturity_date, basis_level_points) VALUES (?, ?, ?, ?, ?)",
        [
            (n.note_id, n.name, n.coupon_rate, n.maturity_date.isoformat(), n.basis_level_points)
            for n in BASKET
        ],
    )

    sessions, note_prices = generate_sessions(num_sessions=num_sessions, seed=seed)

    conn.executemany(
        "INSERT INTO sessions (session_id, sim_date, futures_price, repo_rate, days_to_delivery, delivery_date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (s.session_id, s.sim_date.isoformat(), s.futures_price, s.repo_rate, s.days_to_delivery, s.delivery_date.isoformat())
            for s in sessions
        ],
    )

    rows = []
    for note in BASKET:
        prices = note_prices[note.note_id]
        for session_id, price in enumerate(prices):
            rows.append((session_id, note.note_id, price))
    conn.executemany(
        "INSERT INTO note_prices (session_id, note_id, cash_clean_price) VALUES (?, ?, ?)",
        rows,
    )

    conn.commit()
    conn.close()
