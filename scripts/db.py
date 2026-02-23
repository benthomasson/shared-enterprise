#!/usr/bin/env python3
"""
Simple database CLI for shared-enterprise.

Usage:
    ./scripts/db.py query "SELECT * FROM entries LIMIT 10"
    ./scripts/db.py tables
    ./scripts/db.py schema entries
"""

import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "shared.db"


def get_connection():
    """Get database connection with WAL mode."""
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run: python scripts/init-db.py")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def query(sql: str):
    """Execute a query and print results."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()

        if not rows:
            print("No results")
            return

        # Print as table
        columns = [desc[0] for desc in cursor.description]
        print(" | ".join(columns))
        print("-" * (len(" | ".join(columns))))

        for row in rows:
            values = [str(v) if v is not None else "NULL" for v in row]
            print(" | ".join(values))

        print(f"\n({len(rows)} rows)")
    except sqlite3.Error as e:
        print(f"Error: {e}")
    finally:
        conn.close()


def tables():
    """List all tables."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    for row in cursor:
        print(row[0])
    conn.close()


def schema(table_name: str):
    """Show schema for a table."""
    conn = get_connection()
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    rows = cursor.fetchall()

    if not rows:
        print(f"Table '{table_name}' not found")
        return

    print(f"Schema for {table_name}:")
    for row in rows:
        nullable = "" if row["notnull"] else " (nullable)"
        default = f" DEFAULT {row['dflt_value']}" if row["dflt_value"] else ""
        pk = " PRIMARY KEY" if row["pk"] else ""
        print(f"  {row['name']}: {row['type']}{pk}{default}{nullable}")

    conn.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "query" and len(sys.argv) > 2:
        query(sys.argv[2])
    elif cmd == "tables":
        tables()
    elif cmd == "schema" and len(sys.argv) > 2:
        schema(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
