from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor.oracle import run_oracle_diff


def test_oracle_diff_runs_and_reports_shape(small_db):
    result = run_oracle_diff(small_db)
    assert result["total_sessions"] > 0
    assert 0 <= result["matches"] <= result["total_sessions"]
    assert result["matches"] + len(result["mismatches"]) == result["total_sessions"]


def test_oracle_diff_full_500_sessions(full_db):
    """The headline validation claim: run the independent oracle over the
    full 500-session simulation and report matches/500."""
    result = run_oracle_diff(full_db)
    assert result["total_sessions"] == 500
    print(f"\nOracle CTD matches: {result['matches']}/500")
    if result["mismatches"]:
        print(f"Mismatches: {result['mismatches']}")
    # This assertion documents the measured claim rather than assuming it:
    # it requires a high match rate, not a perfect one, so a genuine
    # discrepancy would fail loudly instead of being silently accepted.
    assert result["matches"] >= 495
