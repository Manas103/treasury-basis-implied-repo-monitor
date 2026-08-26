"""The synthetic 10-year note futures deliverable basket.

Seven notes, remaining maturity 8.80 to 9.90 years as of the simulation
start date, which keeps every note above the real CME 6.5-year eligibility
floor for the entire 500-session / ~700-calendar-day simulation window
(see README limitations: the basket composition is NOT re-validated for
eligibility as time passes, it is fixed for the whole run).

Coupons and the basis_level_points offsets are synthetic, chosen to produce
a plausible spread of gross basis across the basket. They are NOT real
CUSIPs, real coupons, or real prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

SIM_START_DATE = date(2024, 3, 1)


@dataclass(frozen=True)
class Note:
    note_id: int
    name: str
    coupon_rate: float
    maturity_date: date
    basis_level_points: float  # synthetic structural richness/cheapness offset


BASKET: list[Note] = [
    Note(0, "SYN-A 3.500 12/2032", 0.03500, date(2032, 12, 18), 0.30),
    Note(1, "SYN-B 3.750 02/2033", 0.03750, date(2033, 2, 10), 0.24),
    Note(2, "SYN-C 4.000 04/2033", 0.04000, date(2033, 4, 6), 0.16),
    Note(3, "SYN-D 4.125 06/2033", 0.04125, date(2033, 6, 18), 0.06),
    Note(4, "SYN-E 4.250 08/2033", 0.04250, date(2033, 8, 30), 0.12),
    Note(5, "SYN-F 4.500 11/2033", 0.04500, date(2033, 11, 11), 0.20),
    Note(6, "SYN-G 4.750 01/2034", 0.04750, date(2034, 1, 23), 0.34),
]


def years_to_maturity(note: Note, as_of: date) -> float:
    return (note.maturity_date - as_of).days / 365.25
