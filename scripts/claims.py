#!/usr/bin/env python3
"""
Claims management for shared-enterprise.

Usage:
    ./scripts/claims.py add ID --text TEXT [--source SOURCE] [--assumes ID,ID]
    ./scripts/claims.py list [--status IN|OUT|STALE]
    ./scripts/claims.py show ID
    ./scripts/claims.py stale ID --reason REASON
    ./scripts/claims.py resolve ID --superseded-by NEW_ID
    ./scripts/claims.py retract ID
    ./scripts/claims.py audit
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "shared.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def add_claim(claim_id, text, source=None, assumes=None, depends_on=None):
    """Add a new claim."""
    conn = get_connection()

    # Check for duplicate
    existing = conn.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if existing:
        print(f"Error: claim '{claim_id}' already exists. Use a different ID.")
        conn.close()
        sys.exit(1)

    assumes_json = json.dumps(assumes) if assumes else None
    depends_json = json.dumps(depends_on) if depends_on else None

    conn.execute(
        """
        INSERT INTO claims (id, text, status, source, assumes, depends_on)
        VALUES (?, ?, 'IN', ?, ?, ?)
        """,
        (claim_id, text, source, assumes_json, depends_json),
    )
    conn.commit()
    conn.close()

    print(f"Added claim: {claim_id}")
    print(f"  Text: {text}")
    if source:
        print(f"  Source: {source}")
    if assumes:
        print(f"  Assumes: {assumes}")


def list_claims(status=None):
    """List claims, optionally filtered by status."""
    conn = get_connection()

    if status:
        cursor = conn.execute(
            "SELECT id, status, text, source FROM claims WHERE status = ? ORDER BY id",
            (status.upper(),),
        )
    else:
        cursor = conn.execute(
            "SELECT id, status, text, source FROM claims ORDER BY status, id"
        )

    rows = cursor.fetchall()
    if not rows:
        print("No claims found")
        conn.close()
        return

    for row in rows:
        text = row["text"]
        if len(text) > 80:
            text = text[:77] + "..."
        print(f"  [{row['status']}] {row['id']}: {text}")

    print(f"\n({len(rows)} claims)")
    conn.close()


def show_claim(claim_id):
    """Show full details of a claim."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()

    if not row:
        print(f"Claim not found: {claim_id}")
        conn.close()
        return

    print(f"ID: {row['id']}")
    print(f"Status: {row['status']}")
    print(f"Text: {row['text']}")
    print(f"Source: {row['source'] or '(none)'}")
    print(f"Created: {row['created_at']}")
    print(f"Updated: {row['updated_at']}")

    if row["assumes"]:
        print(f"Assumes: {row['assumes']}")
    if row["depends_on"]:
        print(f"Depends on: {row['depends_on']}")
    if row["superseded_by"]:
        print(f"Superseded by: {row['superseded_by']}")
    if row["stale_reason"]:
        print(f"Stale reason: {row['stale_reason']}")

    # Show what depends on this claim
    all_claims = conn.execute("SELECT id, assumes, depends_on FROM claims WHERE id != ?", (claim_id,)).fetchall()
    dependents = []
    for c in all_claims:
        deps = []
        if c["assumes"]:
            deps.extend(json.loads(c["assumes"]))
        if c["depends_on"]:
            deps.extend(json.loads(c["depends_on"]))
        if claim_id in deps:
            dependents.append(c["id"])

    if dependents:
        print(f"Depended on by: {dependents}")

    # Show linked entries
    links = conn.execute(
        """
        SELECT el.to_id, el.relation, e.title
        FROM entry_links el
        LEFT JOIN entries e ON e.id = el.to_id
        WHERE el.from_id = ?
        """,
        (claim_id,),
    ).fetchall()
    if links:
        print("Linked entries:")
        for l in links:
            label = l["title"] if l["title"] else l["to_id"]
            print(f"  → {label} ({l['relation']})")

    # Show history events
    history = conn.execute(
        """
        SELECT h.event_date, h.event_type, h.summary
        FROM history_refs hr
        JOIN history h ON h.id = hr.history_id
        WHERE hr.ref_id = ?
        ORDER BY h.event_date
        """,
        (claim_id,),
    ).fetchall()
    if history:
        print("History:")
        for h in history:
            print(f"  {h['event_date']} [{h['event_type']}] {h['summary']}")

    conn.close()


def mark_stale(claim_id, reason):
    """Mark a claim as STALE and cascade to dependents."""
    conn = get_connection()

    row = conn.execute("SELECT id, status FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not row:
        print(f"Claim not found: {claim_id}")
        conn.close()
        return

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE claims SET status = 'STALE', stale_reason = ?, updated_at = ? WHERE id = ?",
        (reason, now, claim_id),
    )

    # Cascade: find claims that assume or depend on this one
    cascaded = []
    all_claims = conn.execute("SELECT id, assumes, depends_on FROM claims WHERE status = 'IN'").fetchall()
    for c in all_claims:
        deps = []
        if c["assumes"]:
            deps.extend(json.loads(c["assumes"]))
        if c["depends_on"]:
            deps.extend(json.loads(c["depends_on"]))
        if claim_id in deps:
            conn.execute(
                "UPDATE claims SET status = 'STALE', stale_reason = ?, updated_at = ? WHERE id = ?",
                (f"dependency {claim_id} is stale", now, c["id"]),
            )
            cascaded.append(c["id"])

    conn.commit()
    conn.close()

    print(f"Marked STALE: {claim_id}")
    print(f"  Reason: {reason}")
    if cascaded:
        print(f"  Cascaded to: {cascaded}")


def resolve(claim_id, superseded_by):
    """Resolve a stale/outdated claim by pointing to its replacement."""
    conn = get_connection()

    row = conn.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not row:
        print(f"Claim not found: {claim_id}")
        conn.close()
        return

    replacement = conn.execute("SELECT id FROM claims WHERE id = ?", (superseded_by,)).fetchone()
    if not replacement:
        print(f"Replacement claim not found: {superseded_by}")
        conn.close()
        return

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE claims SET status = 'OUT', superseded_by = ?, updated_at = ? WHERE id = ?",
        (superseded_by, now, claim_id),
    )
    conn.commit()
    conn.close()

    print(f"Resolved: {claim_id} -> superseded by {superseded_by}")


def retract(claim_id):
    """Retract a claim (mark as OUT with no replacement)."""
    conn = get_connection()

    row = conn.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not row:
        print(f"Claim not found: {claim_id}")
        conn.close()
        return

    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "UPDATE claims SET status = 'OUT', updated_at = ? WHERE id = ?",
        (now, claim_id),
    )
    conn.commit()
    conn.close()

    print(f"Retracted: {claim_id}")


def audit():
    """Run a full belief audit."""
    conn = get_connection()

    # Status summary
    print("=== BELIEF AUDIT ===\n")
    stats = conn.execute("SELECT status, COUNT(*) as n FROM claims GROUP BY status ORDER BY status").fetchall()
    for row in stats:
        print(f"  {row['status']}: {row['n']}")
    print()

    # Dependency chains
    all_claims = conn.execute("SELECT id, status, assumes, depends_on FROM claims").fetchall()
    chains = []
    for c in all_claims:
        deps = []
        if c["assumes"]:
            deps.extend(json.loads(c["assumes"]))
        if c["depends_on"]:
            deps.extend(json.loads(c["depends_on"]))
        if deps:
            chains.append((c["id"], c["status"], deps))

    if chains:
        print("Dependency chains:")
        for claim_id, status, deps in chains:
            print(f"  [{status}] {claim_id} <- {deps}")
        print()

    # Stale claims
    stale = conn.execute("SELECT id, text, stale_reason FROM claims WHERE status = 'STALE'").fetchall()
    if stale:
        print(f"STALE claims ({len(stale)}):")
        for s in stale:
            print(f"  {s['id']}: {s['stale_reason']}")
        print()

    # Superseded claims
    superseded = conn.execute(
        "SELECT id, superseded_by FROM claims WHERE superseded_by IS NOT NULL"
    ).fetchall()
    if superseded:
        print("Supersession chain:")
        for s in superseded:
            print(f"  {s['id']} -> {s['superseded_by']}")
        print()

    # Source distribution
    print("Sources:")
    sources = conn.execute(
        "SELECT source, COUNT(*) as n FROM claims WHERE source IS NOT NULL GROUP BY source ORDER BY n DESC"
    ).fetchall()
    for s in sources:
        print(f"  {s['source']}: {s['n']}")

    unsourced = conn.execute("SELECT id FROM claims WHERE source IS NULL").fetchall()
    if unsourced:
        print(f"\nWARNING: {len(unsourced)} claims without sources: {[r['id'] for r in unsourced]}")

    print()
    conn.close()


def link_claim(claim_id, entry_id, relation="related"):
    """Link a claim to an entry via entry_links."""
    conn = get_connection()

    claim = conn.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not claim:
        print(f"Claim not found: {claim_id}")
        conn.close()
        return

    entry = conn.execute("SELECT id, title FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if not entry:
        print(f"Entry not found: {entry_id}")
        conn.close()
        return

    conn.execute(
        "INSERT OR IGNORE INTO entry_links (from_id, to_id, relation) VALUES (?, ?, ?)",
        (claim_id, entry_id, relation),
    )
    conn.commit()
    conn.close()

    print(f"Linked: {claim_id} → {entry['title']} ({relation})")


def main():
    parser = argparse.ArgumentParser(description="Claims management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = subparsers.add_parser("add", help="Add a claim")
    add_p.add_argument("id", help="Claim ID (short, descriptive)")
    add_p.add_argument("--text", required=True, help="Claim text")
    add_p.add_argument("--source", help="Source reference")
    add_p.add_argument("--assumes", help="Comma-separated claim IDs this assumes")
    add_p.add_argument("--depends-on", help="Comma-separated claim IDs this depends on")

    # list
    list_p = subparsers.add_parser("list", help="List claims")
    list_p.add_argument("--status", choices=["IN", "OUT", "STALE"], help="Filter by status")

    # show
    show_p = subparsers.add_parser("show", help="Show claim details")
    show_p.add_argument("id", help="Claim ID")

    # stale
    stale_p = subparsers.add_parser("stale", help="Mark a claim as stale")
    stale_p.add_argument("id", help="Claim ID")
    stale_p.add_argument("--reason", required=True, help="Why it's stale")

    # resolve
    resolve_p = subparsers.add_parser("resolve", help="Resolve a claim with its replacement")
    resolve_p.add_argument("id", help="Old claim ID")
    resolve_p.add_argument("--superseded-by", required=True, help="New claim ID")

    # retract
    retract_p = subparsers.add_parser("retract", help="Retract a claim (no replacement)")
    retract_p.add_argument("id", help="Claim ID")

    # audit
    subparsers.add_parser("audit", help="Run full belief audit")

    # link
    link_p = subparsers.add_parser("link", help="Link a claim to an entry")
    link_p.add_argument("id", help="Claim ID")
    link_p.add_argument("entry_id", help="Entry ID")
    link_p.add_argument("--relation", default="related",
                        choices=["related", "supersedes", "extends", "contradicts"],
                        help="Relationship type")

    args = parser.parse_args()

    if args.command == "add":
        assumes = args.assumes.split(",") if args.assumes else None
        depends_on = args.depends_on.split(",") if args.depends_on else None
        add_claim(args.id, args.text, args.source, assumes, depends_on)
    elif args.command == "list":
        list_claims(args.status)
    elif args.command == "show":
        show_claim(args.id)
    elif args.command == "stale":
        mark_stale(args.id, args.reason)
    elif args.command == "resolve":
        resolve(args.id, args.superseded_by)
    elif args.command == "retract":
        retract(args.id)
    elif args.command == "audit":
        audit()
    elif args.command == "link":
        link_claim(args.id, args.entry_id, args.relation)


if __name__ == "__main__":
    main()
