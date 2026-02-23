#!/usr/bin/env python3
"""Initialize the shared-enterprise SQLite database."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "shared.db"
SCHEMA_PATH = Path(__file__).parent.parent / "schema.sql"


def init_db():
    """Create database and apply schema."""
    print(f"Initializing database at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode
    conn.execute("PRAGMA foreign_keys=ON")

    schema = SCHEMA_PATH.read_text()
    conn.executescript(schema)
    conn.commit()

    # Verify tables
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Created tables: {', '.join(tables)}")

    conn.close()
    print("Database initialized successfully")


if __name__ == "__main__":
    init_db()
