"""Claims management for shared-enterprise."""

import json
import re
from datetime import datetime

from .db import get_connection


def add_claim(claim_id, text, source=None, assumes=None, depends_on=None):
    """Add a new claim."""
    conn = get_connection()
    existing = conn.execute("SELECT id FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if existing:
        print(f"Error: claim '{claim_id}' already exists.")
        conn.close()
        return
    assumes_json = json.dumps(assumes) if assumes else None
    depends_json = json.dumps(depends_on) if depends_on else None
    conn.execute(
        "INSERT INTO claims (id, text, status, source, assumes, depends_on) VALUES (?, ?, 'IN', ?, ?, ?)",
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

    # Dependents
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

    # Linked entries
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

    # History
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


def audit():
    """Run a full belief audit."""
    conn = get_connection()
    print("=== BELIEF AUDIT ===\n")
    stats = conn.execute("SELECT status, COUNT(*) as n FROM claims GROUP BY status ORDER BY status").fetchall()
    for row in stats:
        print(f"  {row['status']}: {row['n']}")
    print()

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

    stale = conn.execute("SELECT id, text, stale_reason FROM claims WHERE status = 'STALE'").fetchall()
    if stale:
        print(f"STALE claims ({len(stale)}):")
        for s in stale:
            print(f"  {s['id']}: {s['stale_reason']}")
        print()

    superseded = conn.execute(
        "SELECT id, superseded_by FROM claims WHERE superseded_by IS NOT NULL"
    ).fetchall()
    if superseded:
        print("Supersession chain:")
        for s in superseded:
            print(f"  {s['id']} -> {s['superseded_by']}")
        print()

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


def import_beliefs(filepath):
    """Import claims from a beliefs.md file."""
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return

    text = path.read_text()

    # Parse beliefs.md format:
    #   ### claim-id [STATUS]
    #   Claim text on next line
    #   - Source: repo:path/to/file
    #   - Source hash: abc123
    #   - Date: 2026-02-25
    pattern = re.compile(
        r"### (\S+) \[(\w+)\]\n"
        r"(.+?)\n"
        r"- Source: (.+?)\n"
        r"- Source hash: (\w+)\n"
        r"- Date: (\S+)"
    )
    matches = pattern.findall(text)

    if not matches:
        print(f"No beliefs found in {filepath}")
        print("Expected format: ### claim-id [STATUS]\\nClaim text\\n- Source: ...\\n- Source hash: ...\\n- Date: ...")
        return

    conn = get_connection()
    added = 0
    updated = 0
    unchanged = 0

    for claim_id, status, claim_text, source, source_hash, date in matches:
        # Normalize source prefix
        if not source.startswith(("repo:", "observation:", "analysis:", "experience:")):
            source = "repo:" + source

        existing = conn.execute("SELECT id, text, source, source_hash FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if existing:
            # Update if text or source changed
            if existing["text"] != claim_text or existing["source"] != source or existing["source_hash"] != source_hash:
                conn.execute(
                    "UPDATE claims SET text = ?, status = ?, source = ?, source_hash = ?, updated_at = ? WHERE id = ?",
                    (claim_text, status, source, source_hash, date + "T00:00:00", claim_id),
                )
                updated += 1
            else:
                unchanged += 1
        else:
            conn.execute(
                "INSERT INTO claims (id, text, status, source, source_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (claim_id, claim_text, status, source, source_hash, date + "T00:00:00"),
            )
            added += 1

    conn.commit()
    conn.close()
    total = added + updated + unchanged
    print(f"Imported {total} beliefs from {filepath}")
    print(f"  New: {added}  Updated: {updated}  Unchanged: {unchanged}")


def import_nogoods(filepath):
    """Import nogoods from a nogoods.md file into the history table."""
    from pathlib import Path

    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return

    text = path.read_text()

    # Parse nogoods.md format:
    #   ### nogood-001: Description text
    #   - Discovered: 2026-02-26
    #   - Resolution: How to fix it
    pattern = re.compile(
        r"### (nogood-\d+): (.+?)\n"
        r"- Discovered: (\S+)\n"
        r"- Resolution: (.+?)(?:\n|$)"
    )
    matches = pattern.findall(text)

    if not matches:
        print(f"No nogoods found in {filepath}")
        print("Expected format: ### nogood-NNN: Description\\n- Discovered: ...\\n- Resolution: ...")
        return

    conn = get_connection()
    added = 0
    updated = 0
    unchanged = 0

    for nogood_id, description, discovered, resolution in matches:
        summary = f"{description} → {resolution}"

        existing = conn.execute("SELECT id, summary FROM history WHERE id = ?", (nogood_id,)).fetchone()
        if existing:
            if existing["summary"] != summary:
                conn.execute(
                    "UPDATE history SET summary = ?, event_date = ? WHERE id = ?",
                    (summary, discovered, nogood_id),
                )
                updated += 1
            else:
                unchanged += 1
        else:
            conn.execute(
                "INSERT INTO history (id, event_date, event_type, summary) VALUES (?, ?, 'nogood', ?)",
                (nogood_id, discovered, summary),
            )
            added += 1

    conn.commit()
    conn.close()
    total = added + updated + unchanged
    print(f"Imported {total} nogoods from {filepath}")
    print(f"  New: {added}  Updated: {updated}  Unchanged: {unchanged}")
