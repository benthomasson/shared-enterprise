#!/usr/bin/env python3
"""
Entry management for shared-enterprise.

Usage:
    ./scripts/entry.py add --topic TOPIC --title TITLE --content CONTENT
    ./scripts/entry.py add --topic TOPIC --title TITLE --stdin
    ./scripts/entry.py list [--topic TOPIC]
    ./scripts/entry.py show ID
    ./scripts/entry.py search QUERY
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "shared.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def generate_id(topic: str, title: str) -> str:
    """Generate a unique ID from topic, title, and timestamp."""
    ts = datetime.now().isoformat()
    data = f"{topic}:{title}:{ts}"
    return hashlib.sha256(data.encode()).hexdigest()[:12]


def extract_facets(text: str) -> dict:
    """Extract structured facets from free text using regex."""
    facets = {}

    # File paths: slash-separated with common extensions
    file_paths = re.findall(
        r'(?:^|[\s`(])([a-zA-Z0-9_./]+(?:\.py|\.js|\.ts|\.go|\.rs|\.java|\.yaml|\.yml|\.toml|\.json|\.md|\.sql))\b',
        text,
    )
    if file_paths:
        facets["file_paths"] = sorted(set(file_paths))

    # CamelCase identifiers (likely class/exception names)
    camel = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text)
    if camel:
        facets["identifiers"] = sorted(set(camel))

    # URLs
    urls = re.findall(r'https?://[^\s)>\]]+', text)
    if urls:
        facets["urls"] = sorted(set(urls))

    # snake_case identifiers (likely function/variable names, 2+ segments)
    snake = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b', text)
    # Filter out common English phrases that happen to match
    noise = {"of_the", "in_the", "to_the", "on_the", "at_the", "is_a", "has_a", "for_the"}
    snake = [s for s in snake if s not in noise and len(s) > 4]
    if snake:
        facets["functions"] = sorted(set(snake))

    return facets


def add_entry(topic: str, title: str, content: str, source_skill: str = "entry"):
    """Add a new entry with auto-extracted metadata facets."""
    conn = get_connection()
    entry_id = generate_id(topic, title)
    facets = extract_facets(content)
    metadata = json.dumps(facets) if facets else None

    conn.execute(
        """
        INSERT INTO entries (id, topic, title, content, source_skill, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
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


def list_entries(topic: str = None):
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


def show_entry(entry_id: str):
    """Show a specific entry."""
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
    row = cursor.fetchone()

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


def search_entries(query: str):
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


def main():
    parser = argparse.ArgumentParser(description="Entry management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_parser = subparsers.add_parser("add", help="Add an entry")
    add_parser.add_argument("--topic", required=True, help="Entry topic")
    add_parser.add_argument("--title", required=True, help="Entry title")
    add_parser.add_argument("--content", help="Entry content")
    add_parser.add_argument("--stdin", action="store_true", help="Read content from stdin")
    add_parser.add_argument("--source", default="entry", help="Source skill")

    # list
    list_parser = subparsers.add_parser("list", help="List entries")
    list_parser.add_argument("--topic", help="Filter by topic")

    # show
    show_parser = subparsers.add_parser("show", help="Show an entry")
    show_parser.add_argument("id", help="Entry ID")

    # search
    search_parser = subparsers.add_parser("search", help="Search entries")
    search_parser.add_argument("query", help="Search query")

    args = parser.parse_args()

    if args.command == "add":
        if args.stdin:
            content = sys.stdin.read()
        elif args.content:
            content = args.content
        else:
            print("Error: --content or --stdin required")
            sys.exit(1)
        add_entry(args.topic, args.title, content, args.source)

    elif args.command == "list":
        list_entries(args.topic)

    elif args.command == "show":
        show_entry(args.id)

    elif args.command == "search":
        search_entries(args.query)


if __name__ == "__main__":
    main()
