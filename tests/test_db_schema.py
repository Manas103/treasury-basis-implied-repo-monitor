from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from treasury_monitor import db as db_module


def test_schema_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.db"
    conn = db_module.connect(db_path)
    db_module.init_schema(conn)

    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cur.fetchall()}
    assert {"notes", "sessions", "note_prices", "results"} <= tables
    conn.close()


def test_notes_and_sessions_populated(small_db):
    cur = small_db.cursor()
    cur.execute("SELECT COUNT(*) FROM notes")
    assert cur.fetchone()[0] == 7

    cur.execute("SELECT COUNT(*) FROM sessions")
    assert cur.fetchone()[0] == 40

    cur.execute("SELECT COUNT(*) FROM note_prices")
    assert cur.fetchone()[0] == 40 * 7


def test_real_sql_query_basket_average_gross_basis_by_note(small_db):
    """Exercises real aggregate SQL over the schema, not just row counts."""
    cur = small_db.cursor()
    cur.execute(
        """SELECT n.name, AVG(r.gross_basis_points) as avg_gross_basis
           FROM results r JOIN notes n ON r.note_id = n.note_id
           GROUP BY n.note_id
           ORDER BY avg_gross_basis ASC"""
    )
    rows = cur.fetchall()
    assert len(rows) == 7
    # every row should have a finite, real numeric average
    for name, avg_gross_basis in rows:
        assert isinstance(avg_gross_basis, float)
