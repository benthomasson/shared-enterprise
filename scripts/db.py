#!/usr/bin/env python3
"""
Simple database CLI for shared-enterprise.

Usage:
    ./scripts/db.py query "SELECT * FROM entries LIMIT 10"
    ./scripts/db.py tables
    ./scripts/db.py schema entries
    ./scripts/db.py search "authentication retry"
    ./scripts/db.py describe
    ./scripts/db.py context "error handling"
"""

import json
import sqlite3
import sys
from pathlib import Path

try:
    import numpy as np
    from fastembed import TextEmbedding

    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False

DB_PATH = Path(__file__).parent.parent / "shared.db"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"


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


def search(terms: str):
    """Full-text search across entries using FTS5."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            SELECT e.id, e.topic, e.title, e.content, fts.rank
            FROM entries_fts fts
            JOIN entries e ON e.rowid = fts.rowid
            WHERE entries_fts MATCH ?
            ORDER BY fts.rank
            """,
            (terms,),
        )
        rows = cursor.fetchall()

        if not rows:
            print(f"No results for: {terms}")
            return

        for row in rows:
            print(f"[{row['topic']}] {row['title']} (id: {row['id']})")
            # Show first 200 chars of content
            content = row["content"]
            if len(content) > 200:
                content = content[:200] + "..."
            print(f"  {content}")
            print()

        print(f"({len(rows)} results)")
    except sqlite3.Error as e:
        print(f"Error: {e}")
    finally:
        conn.close()


def describe():
    """Describe all tables: schema, row counts, and sample data."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'entries_fts%' ORDER BY name"
    )
    table_names = [row[0] for row in cursor.fetchall()]

    for name in table_names:
        # Row count
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"## {name} ({count} rows)")

        # Schema
        cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
        for col in cols:
            nullable = "" if col["notnull"] else " (nullable)"
            default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] else ""
            pk = " PK" if col["pk"] else ""
            print(f"  {col['name']}: {col['type']}{pk}{default}{nullable}")

        # Sample row
        if count > 0:
            sample = conn.execute(f"SELECT * FROM [{name}] LIMIT 1").fetchone()
            print(f"  Sample: {dict(sample)}")

        print()

    conn.close()


def context(terms: str):
    """Gather everything relevant to a topic across all tables."""
    conn = get_connection()
    like = f"%{terms}%"
    found_anything = False

    # 1. FTS5 entries
    try:
        rows = conn.execute(
            """
            SELECT e.id, e.topic, e.title, e.content, e.metadata
            FROM entries_fts fts
            JOIN entries e ON e.rowid = fts.rowid
            WHERE entries_fts MATCH ?
            ORDER BY fts.rank
            """,
            (terms,),
        ).fetchall()
    except sqlite3.Error:
        # FTS match syntax error — fall back to LIKE
        rows = conn.execute(
            "SELECT id, topic, title, content, metadata FROM entries WHERE content LIKE ? OR title LIKE ?",
            (like, like),
        ).fetchall()

    if rows:
        found_anything = True
        print(f"## Entries ({len(rows)})\n")
        for row in rows:
            print(f"  [{row['topic']}] {row['title']} (id: {row['id']})")
            content = row["content"]
            if len(content) > 150:
                content = content[:150] + "..."
            print(f"    {content}")
            if row["metadata"]:
                meta = json.loads(row["metadata"])
                if meta:
                    print(f"    Facets: {list(meta.keys())}")
            # Show links from this entry
            links = conn.execute(
                "SELECT to_id, relation FROM entry_links WHERE from_id = ?",
                (row["id"],),
            ).fetchall()
            if links:
                print(f"    Links: {[(l['to_id'], l['relation']) for l in links]}")
            print()

    # 2. Claims
    rows = conn.execute(
        "SELECT id, status, text, source FROM claims WHERE text LIKE ? ORDER BY status, id",
        (like,),
    ).fetchall()
    if rows:
        found_anything = True
        print(f"## Claims ({len(rows)})\n")
        for row in rows:
            print(f"  [{row['status']}] {row['id']}: {row['text']}")
            if row["source"]:
                print(f"    Source: {row['source']}")
            # Show links from this claim
            links = conn.execute(
                """
                SELECT el.to_id, el.relation, e.title
                FROM entry_links el
                LEFT JOIN entries e ON e.id = el.to_id
                WHERE el.from_id = ?
                """,
                (row["id"],),
            ).fetchall()
            if links:
                for l in links:
                    label = l["title"] if l["title"] else l["to_id"]
                    print(f"    → {label} ({l['relation']})")
            # Show history for this claim via reverse index
            hist = conn.execute(
                """
                SELECT h.event_date, h.event_type, h.summary
                FROM history_refs hr
                JOIN history h ON h.id = hr.history_id
                WHERE hr.ref_id = ?
                ORDER BY h.event_date
                """,
                (row["id"],),
            ).fetchall()
            if hist:
                for h in hist:
                    print(f"    {h['event_date']} [{h['event_type']}] {h['summary']}")
            print()

    # 3. History
    rows = conn.execute(
        "SELECT event_date, event_type, summary, related_ids FROM history WHERE summary LIKE ? ORDER BY event_date",
        (like,),
    ).fetchall()
    if rows:
        found_anything = True
        print(f"## History ({len(rows)})\n")
        for row in rows:
            related = json.loads(row["related_ids"]) if row["related_ids"] else []
            related_str = f" → {related}" if related else ""
            print(f"  {row['event_date']} [{row['event_type']}] {row['summary']}{related_str}")
        print()

    # 4. Facet metadata — search for the term in extracted facets
    rows = conn.execute(
        "SELECT id, title, metadata FROM entries WHERE metadata LIKE ?",
        (like,),
    ).fetchall()
    if rows:
        found_anything = True
        print(f"## Facet Matches ({len(rows)})\n")
        for row in rows:
            meta = json.loads(row["metadata"])
            print(f"  {row['title']} (id: {row['id']})")
            print(f"    {json.dumps(meta)}")
        print()

    # 5. Semantic search (only if fastembed available)
    if HAS_EMBEDDINGS:
        emb_rows = conn.execute(
            "SELECT id, source_table, vector FROM embeddings"
        ).fetchall()
        if emb_rows:
            model = TextEmbedding(model_name=EMBED_MODEL)
            query_vec = list(model.embed([terms]))[0]

            scored = []
            for row in emb_rows:
                vec = np.frombuffer(row["vector"], dtype=np.float32)
                dot = np.dot(query_vec, vec)
                norm = np.linalg.norm(query_vec) * np.linalg.norm(vec)
                sim = float(dot / norm) if norm > 0 else 0.0
                if sim >= 0.4:
                    scored.append((sim, row["id"], row["source_table"]))

            scored.sort(reverse=True)
            if scored:
                found_anything = True
                print(f"## Semantic Matches ({len(scored)})\n")
                for sim, item_id, source_table in scored[:8]:
                    if source_table == "entries":
                        r = conn.execute("SELECT title FROM entries WHERE id = ?", (item_id,)).fetchone()
                        label = r["title"] if r else item_id
                    else:
                        r = conn.execute("SELECT text FROM claims WHERE id = ?", (item_id,)).fetchone()
                        label = r["text"][:80] if r else item_id
                    print(f"  {sim:.3f}  [{source_table}] {item_id}: {label}")
                print()

    if not found_anything:
        print(f"Nothing found for: {terms}")


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
    elif cmd == "search" and len(sys.argv) > 2:
        search(sys.argv[2])
    elif cmd == "describe":
        describe()
    elif cmd == "context" and len(sys.argv) > 2:
        context(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
