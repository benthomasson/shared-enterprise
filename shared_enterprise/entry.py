"""Entry management for shared-enterprise."""

import hashlib
import json
import re
import sys
from datetime import datetime

from .db import get_connection


def generate_id(topic, title):
    """Generate a unique ID from topic, title, and timestamp."""
    ts = datetime.now().isoformat()
    data = f"{topic}:{title}:{ts}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def extract_facets(text):
    """Extract structured facets from free text using regex."""
    facets = {}
    file_paths = re.findall(
        r'(?:^|[\s`(])([a-zA-Z0-9_./]+(?:\.py|\.js|\.ts|\.go|\.rs|\.java|\.yaml|\.yml|\.toml|\.json|\.md|\.sql))\b',
        text,
    )
    if file_paths:
        facets["file_paths"] = sorted(set(file_paths))
    camel = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text)
    if camel:
        facets["identifiers"] = sorted(set(camel))
    urls = re.findall(r'https?://[^\s)>\]]+', text)
    if urls:
        facets["urls"] = sorted(set(urls))
    snake = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b', text)
    noise = {"of_the", "in_the", "to_the", "on_the", "at_the", "is_a", "has_a", "for_the"}
    snake = [s for s in snake if s not in noise and len(s) > 4]
    if snake:
        facets["functions"] = sorted(set(snake))
    return facets


def add_entry(topic, title, content, source_skill="entry"):
    """Add a new entry with auto-extracted metadata facets."""
    conn = get_connection()
    entry_id = generate_id(topic, title)
    facets = extract_facets(content)
    metadata = json.dumps(facets) if facets else None
    conn.execute(
        "INSERT INTO entries (id, topic, title, content, source_skill, metadata) VALUES (?, ?, ?, ?, ?, ?)",
        (entry_id, topic, title, content, source_skill, metadata),
    )
    conn.commit()
    conn.close()
    print(f"Added entry: {entry_id}")
    print(f"  Topic: {topic}")
    print(f"  Title: {title}")
    if facets:
        print(f"  Facets: {json.dumps(facets, indent=2)}")
    return entry_id


def list_entries(topic=None):
    """List entries."""
    conn = get_connection()
    if topic:
        cursor = conn.execute(
            "SELECT id, created_at, topic, title FROM entries WHERE topic = ? ORDER BY created_at DESC",
            (topic,),
        )
    else:
        cursor = conn.execute(
            "SELECT id, created_at, topic, title FROM entries ORDER BY created_at DESC"
        )
    rows = cursor.fetchall()
    if not rows:
        print("No entries found")
        return
    for row in rows:
        print(f"{row['id']} | {row['created_at'][:16]} | {row['topic']} | {row['title']}")
    print(f"\n({len(rows)} entries)")
    conn.close()


def show_entry(entry_id):
    """Show a specific entry."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        print(f"Entry not found: {entry_id}")
        return
    print(f"ID: {row['id']}")
    print(f"Created: {row['created_at']}")
    print(f"Topic: {row['topic']}")
    print(f"Title: {row['title']}")
    print(f"Source: {row['source_skill']}")
    print(f"\n{row['content']}")
    conn.close()


def search_entries(query):
    """Search entries by content."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT id, created_at, topic, title FROM entries WHERE content LIKE ? OR title LIKE ? ORDER BY created_at DESC",
        (f"%{query}%", f"%{query}%"),
    )
    rows = cursor.fetchall()
    if not rows:
        print(f"No entries matching: {query}")
        return
    for row in rows:
        print(f"{row['id']} | {row['created_at'][:16]} | {row['topic']} | {row['title']}")
    print(f"\n({len(rows)} matches)")
    conn.close()


def backfill_facets():
    """Re-extract facets for entries with NULL metadata."""
    conn = get_connection()
    rows = conn.execute("SELECT id, title, content FROM entries WHERE metadata IS NULL").fetchall()
    if not rows:
        print("All entries already have metadata")
        return
    updated = 0
    for row in rows:
        facets = extract_facets(row["content"])
        if facets:
            conn.execute(
                "UPDATE entries SET metadata = ? WHERE id = ?",
                (json.dumps(facets), row["id"]),
            )
            print(f"  {row['id']} ({row['title']}): {list(facets.keys())}")
            updated += 1
        else:
            print(f"  {row['id']} ({row['title']}): no facets found")
    conn.commit()
    conn.close()
    print(f"\nBackfilled {updated}/{len(rows)} entries")
