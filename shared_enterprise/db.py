"""Database access and query commands for shared-enterprise."""

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

EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def get_db_path():
    """Database path in current working directory."""
    return Path.cwd() / "shared.db"


def get_schema_path():
    """Find schema.sql — bundled in package."""
    return Path(__file__).parent / "schema.sql"


def get_connection():
    """Get database connection."""
    db_path = get_db_path()
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("Run: shared-enterprise init")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize database from schema.sql."""
    db_path = get_db_path()
    schema_path = get_schema_path()
    if not schema_path.exists():
        print(f"Schema not found at {schema_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text())
    conn.close()
    print(f"Initialized {db_path}")


def query(sql):
    """Execute a query and print results."""
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            print("No results")
            return
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


def schema(table_name):
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


def search(terms):
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
        count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        print(f"## {name} ({count} rows)")
        cols = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
        for col in cols:
            nullable = "" if col["notnull"] else " (nullable)"
            default = f" DEFAULT {col['dflt_value']}" if col["dflt_value"] else ""
            pk = " PK" if col["pk"] else ""
            print(f"  {col['name']}: {col['type']}{pk}{default}{nullable}")
        if count > 0:
            sample = conn.execute(f"SELECT * FROM [{name}] LIMIT 1").fetchone()
            print(f"  Sample: {dict(sample)}")
        print()
    conn.close()


def context(terms):
    """Gather everything relevant to a topic across all tables, with convergence detection."""
    conn = get_connection()
    like = f"%{terms}%"

    # Track which sources found each item: item_id -> {sources, label, type}
    convergence = {}  # id -> {"sources": set, "label": str, "type": str}

    def _track(item_id, source_name, label, item_type="entry"):
        if item_id not in convergence:
            convergence[item_id] = {"sources": set(), "label": label, "type": item_type}
        convergence[item_id]["sources"].add(source_name)

    # 1. FTS5 entries
    try:
        fts_rows = conn.execute(
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
        fts_rows = conn.execute(
            "SELECT id, topic, title, content, metadata FROM entries WHERE content LIKE ? OR title LIKE ?",
            (like, like),
        ).fetchall()

    for row in fts_rows:
        _track(row["id"], "fts", row["title"], "entry")

    # 2. Claims
    claim_rows = conn.execute(
        "SELECT id, status, text, source FROM claims WHERE text LIKE ? ORDER BY status, id",
        (like,),
    ).fetchall()
    for row in claim_rows:
        text_short = row["text"][:80] if len(row["text"]) > 80 else row["text"]
        _track(row["id"], "claims", text_short, "claim")

    # 3. History
    history_rows = conn.execute(
        "SELECT event_date, event_type, summary, related_ids FROM history WHERE summary LIKE ? ORDER BY event_date",
        (like,),
    ).fetchall()
    for row in history_rows:
        # Track related IDs from history entries
        related = json.loads(row["related_ids"]) if row["related_ids"] else []
        for rid in related:
            _track(rid, "history", row["summary"][:80], "ref")

    # 4. Facet metadata
    facet_rows = conn.execute(
        "SELECT id, title, metadata FROM entries WHERE metadata LIKE ?",
        (like,),
    ).fetchall()
    for row in facet_rows:
        _track(row["id"], "facets", row["title"], "entry")

    # 5. Semantic search (optional)
    semantic_scored = []
    if HAS_EMBEDDINGS:
        emb_rows = conn.execute(
            "SELECT id, source_table, vector FROM embeddings"
        ).fetchall()
        if emb_rows:
            model = TextEmbedding(model_name=EMBED_MODEL)
            query_vec = list(model.embed([terms]))[0]
            for row in emb_rows:
                vec = np.frombuffer(row["vector"], dtype=np.float32)
                dot = np.dot(query_vec, vec)
                norm = np.linalg.norm(query_vec) * np.linalg.norm(vec)
                sim = float(dot / norm) if norm > 0 else 0.0
                if sim >= 0.4:
                    semantic_scored.append((sim, row["id"], row["source_table"]))
                    if row["source_table"] == "entries":
                        r = conn.execute("SELECT title FROM entries WHERE id = ?", (row["id"],)).fetchone()
                        label = r["title"] if r else row["id"]
                    else:
                        r = conn.execute("SELECT text FROM claims WHERE id = ?", (row["id"],)).fetchone()
                        label = r["text"][:80] if r else row["id"]
                    _track(row["id"], "semantic", label, row["source_table"])
            semantic_scored.sort(reverse=True)

    # === Convergence Summary ===
    converged = [(k, v) for k, v in convergence.items() if len(v["sources"]) >= 2]
    converged.sort(key=lambda x: len(x[1]["sources"]), reverse=True)

    if converged:
        print(f"## Convergence ({len(converged)} items from 2+ sources)\n")
        for item_id, info in converged:
            sources = sorted(info["sources"])
            count = len(sources)
            marker = "***" if count >= 4 else "**" if count >= 3 else "*"
            print(f"  {marker} {item_id} [{info['type']}] — {count}/5 sources: {', '.join(sources)}")
            print(f"    {info['label']}")
        print()

    # === Per-source detail ===
    if fts_rows:
        print(f"## Entries ({len(fts_rows)})\n")
        for row in fts_rows:
            src_count = len(convergence.get(row["id"], {}).get("sources", set()))
            badge = f" [{src_count}/5]" if src_count >= 2 else ""
            print(f"  [{row['topic']}] {row['title']} (id: {row['id']}){badge}")
            content = row["content"]
            if len(content) > 150:
                content = content[:150] + "..."
            print(f"    {content}")
            if row["metadata"]:
                meta = json.loads(row["metadata"])
                if meta:
                    print(f"    Facets: {list(meta.keys())}")
            links = conn.execute(
                "SELECT to_id, relation FROM entry_links WHERE from_id = ?",
                (row["id"],),
            ).fetchall()
            if links:
                print(f"    Links: {[(l['to_id'], l['relation']) for l in links]}")
            print()

    if claim_rows:
        print(f"## Claims ({len(claim_rows)})\n")
        for row in claim_rows:
            src_count = len(convergence.get(row["id"], {}).get("sources", set()))
            badge = f" [{src_count}/5]" if src_count >= 2 else ""
            print(f"  [{row['status']}] {row['id']}: {row['text']}{badge}")
            if row["source"]:
                print(f"    Source: {row['source']}")
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

    if history_rows:
        print(f"## History ({len(history_rows)})\n")
        for row in history_rows:
            related = json.loads(row["related_ids"]) if row["related_ids"] else []
            related_str = f" → {related}" if related else ""
            print(f"  {row['event_date']} [{row['event_type']}] {row['summary']}{related_str}")
        print()

    if facet_rows:
        print(f"## Facet Matches ({len(facet_rows)})\n")
        for row in facet_rows:
            meta = json.loads(row["metadata"])
            src_count = len(convergence.get(row["id"], {}).get("sources", set()))
            badge = f" [{src_count}/5]" if src_count >= 2 else ""
            print(f"  {row['title']} (id: {row['id']}){badge}")
            print(f"    {json.dumps(meta)}")
        print()

    if semantic_scored:
        print(f"## Semantic Matches ({len(semantic_scored)})\n")
        for sim, item_id, source_table in semantic_scored[:8]:
            src_count = len(convergence.get(item_id, {}).get("sources", set()))
            badge = f" [{src_count}/5]" if src_count >= 2 else ""
            label = convergence.get(item_id, {}).get("label", item_id)
            print(f"  {sim:.3f}  [{source_table}] {item_id}: {label}{badge}")
        print()

    # Summary
    total_items = len(convergence)
    multi_source = len(converged)
    single_source = total_items - multi_source
    sources_active = set()
    for v in convergence.values():
        sources_active.update(v["sources"])
    if total_items:
        print(f"--- {total_items} items found across {len(sources_active)} sources: {multi_source} converged, {single_source} single-source")
    else:
        print(f"Nothing found for: {terms}")

    conn.close()
