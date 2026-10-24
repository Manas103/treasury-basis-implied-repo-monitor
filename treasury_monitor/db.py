"""SQLite storage layer. Regenerable: the database under data/ is rebuilt by
running scripts/run_simulation.py; see README for the exact command."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sessions.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    note_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    coupon_rate REAL NOT NULL,
    maturity_date TEXT NOT NULL,
    basis_level_points REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY,
    sim_date TEXT NOT NULL,
    futures_price REAL NOT NULL,
    repo_rate REAL NOT NULL,
    days_to_delivery INTEGER NOT NULL,
    delivery_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_prices (
    session_id INTEGER NOT NULL,
    note_id INTEGER NOT NULL,
    cash_clean_price REAL NOT NULL,
    PRIMARY KEY (session_id, note_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (note_id) REFERENCES notes(note_id)
);

CREATE TABLE IF NOT EXISTS results (
    session_id INTEGER NOT NULL,
    note_id INTEGER NOT NULL,
    conversion_factor REAL NOT NULL,
    accrued_now REAL NOT NULL,
    accrued_delivery REAL NOT NULL,
    coupon_income REAL NOT NULL,
    purchase_dirty REAL NOT NULL,
    invoice_dirty REAL NOT NULL,
    gross_basis_points REAL NOT NULL,
    financing_cost_points REAL NOT NULL,
    carry_points REAL NOT NULL,
    net_basis_points REAL NOT NULL,
    net_basis_ticks REAL NOT NULL,
    implied_repo_rate REAL NOT NULL,
    is_ctd INTEGER NOT NULL,
    PRIMARY KEY (session_id, note_id),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
    FOREIGN KEY (note_id) REFERENCES notes(note_id)
);

CREATE INDEX IF NOT EXISTS idx_results_session ON results(session_id);
CREATE INDEX IF NOT EXISTS idx_results_ctd ON results(session_id, is_ctd);

CREATE TABLE IF NOT EXISTS swap_rates (
    session_id INTEGER NOT NULL,
    tenor INTEGER NOT NULL,
    par_rate REAL NOT NULL,
    PRIMARY KEY (session_id, tenor),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS treasury_yields (
    session_id INTEGER NOT NULL,
    tenor INTEGER NOT NULL,
    yield_rate REAL NOT NULL,
    PRIMARY KEY (session_id, tenor),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS spread_series (
    session_id INTEGER NOT NULL,
    series_name TEXT NOT NULL,
    spread_bp REAL NOT NULL,
    rolling_mean_bp REAL,
    rolling_std_bp REAL,
    zscore REAL,
    is_dislocation INTEGER NOT NULL,
    cost_bp REAL,
    survives_filter INTEGER NOT NULL,
    PRIMARY KEY (session_id, series_name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_spread_series_name ON spread_series(series_name);
"""


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def reset_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS spread_series;
        DROP TABLE IF EXISTS treasury_yields;
        DROP TABLE IF EXISTS swap_rates;
        DROP TABLE IF EXISTS results;
        DROP TABLE IF EXISTS note_prices;
        DROP TABLE IF EXISTS sessions;
        DROP TABLE IF EXISTS notes;
        """
    )
    init_schema(conn)
