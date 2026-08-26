#!/usr/bin/env python
"""Run the 25bp overnight funding shock comparative-statics experiment and
report the measured shift in net basis.

Usage: python scripts/run_funding_shock.py
(requires data/sessions.db already populated and engine results computed
by run_simulation.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import db as db_module
from treasury_monitor.funding_shock import FUNDING_SHOCK, run_funding_shock


def main() -> None:
    conn = db_module.connect()
    result = run_funding_shock(conn)
    conn.close()

    print(f"Funding shock applied: +{FUNDING_SHOCK * 10000:.0f}bp on the overnight repo rate")
    print(f"Observations (session x note): {result['num_observations']} across {result['num_sessions']} sessions")
    print()
    print(f"Median net basis shift, all (session, note) observations: {result['median_delta_ticks_all_observations']:.4f} ticks")
    print(f"Median of per-session medians across the basket: {result['median_of_session_medians_ticks']:.4f} ticks")
    print(f"Mean net basis shift, all observations: {result['mean_delta_ticks_all_observations']:.4f} ticks")
    print(f"Min / max shift observed: {result['min_delta_ticks']:.4f} / {result['max_delta_ticks']:.4f} ticks")


if __name__ == "__main__":
    main()
