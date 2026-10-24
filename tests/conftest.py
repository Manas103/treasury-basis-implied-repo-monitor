from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from treasury_monitor import db as db_module
from treasury_monitor import market_sim
from treasury_monitor import rates_market_sim
from treasury_monitor.engine import run_engine
from treasury_monitor.screener import run_screener


@pytest.fixture
def small_db(tmp_path):
    """A small, fast simulation database (40 sessions) for unit tests that
    do not need the full 500-session run."""
    db_path = tmp_path / "small_sessions.db"
    market_sim.populate_db(db_path=db_path, num_sessions=40, seed=7)
    conn = db_module.connect(db_path)
    run_engine(conn)
    yield conn
    conn.close()


@pytest.fixture
def screened_db(tmp_path):
    """A small (120-session) basis database with the swap curve and
    Treasury yields simulated and the screener already run, for the
    screener's own unit tests. 120 sessions is the smallest size that
    clears the screener's 60-session rolling window with room to spare."""
    db_path = tmp_path / "screened_sessions.db"
    market_sim.populate_db(db_path=db_path, num_sessions=120, seed=7)
    conn = db_module.connect(db_path)
    run_engine(conn)
    rates_market_sim.populate_rates(conn, num_sessions=120)
    run_screener(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def full_db(tmp_path_factory):
    """The full 500-session simulation database, built once per test session."""
    db_path = tmp_path_factory.mktemp("full_data") / "sessions.db"
    market_sim.populate_db(db_path=db_path, num_sessions=market_sim.NUM_SESSIONS, seed=market_sim.SEED)
    conn = db_module.connect(db_path)
    run_engine(conn)
    yield conn
    conn.close()
