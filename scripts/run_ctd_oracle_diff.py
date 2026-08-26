#!/usr/bin/env python
"""Diff the independent CTD reference oracle against the main engine's CTD
pick, session by session, over all 500 sessions.

Usage: python scripts/run_ctd_oracle_diff.py
(requires data/sessions.db already populated by run_simulation.py)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import db as db_module
from treasury_monitor.oracle import run_oracle_diff


def main() -> None:
    conn = db_module.connect()
    result = run_oracle_diff(conn)
    conn.close()

    total = result["total_sessions"]
    matches = result["matches"]
    mismatches = result["mismatches"]

    print(f"Total sessions checked: {total}")
    print(f"Independent oracle CTD matches main engine CTD: {matches}/{total}")
    print(f"Mismatches: {len(mismatches)}")
    for m in mismatches:
        print(f"  session {m['session_id']}: engine picked note {m['engine_ctd']}, oracle picked note {m['oracle_ctd']}, margin {m['margin']:.6f}")

    print()
    print("5 closest implied-repo margins between the CTD pick and the runner-up (most numerically sensitive sessions):")
    for margin, session_id in result["closest_margins"]:
        print(f"  session {session_id}: margin = {margin:.6f} (annualized implied repo rate, decimal)")


if __name__ == "__main__":
    main()
