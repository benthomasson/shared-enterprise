"""Auto-index markdown files into the shared-enterprise database."""

import hashlib
import json
import sys
from pathlib import Path

from .db import get_connection
from .entry import extract_facets


def content_hash(text: str) -> str:
    """SHA256 hash of file content for change detection."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def parse_markdown(path: Path) -> dict:
    """Extract title, date, and content from a markdown file."""
    import re

    text = path.read_text()
    lines = text.split("\n")

    title = None
    date = None

    for line in lines:
        if title is None and line.startswith("# "):
            title = line[2:].strip()
        if date is None:
            m = re.match(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", line)
            if m:
                date = m.group(1)
        if title and date:
            break

    if not title:
        title = path.stem.replace("-", " ").title()

    return {
        "title": title,
        "date": date,
        "content": text,
    }


def make_id(rel_path: str) -> str:
    """Convert relative path to entry ID."""
    if rel_path.endswith(".md"):
        rel_path = rel_path[:-3]
    return rel_path


def make_topic(rel_path: str) -> str:
    """Derive topic from filename slug."""
    return Path(rel_path).stem


def index_directory(directory: str, reindex: bool = False):
    """Walk a directory and index all markdown files."""
    base = Path(directory).resolve()
    if not base.is_dir():
        print(f"Not a directory: {base}")
        sys.exit(1)

    conn = get_connection()

    md_files = sorted(base.rglob("*.md"))
    md_files = [f for f in md_files if f.name.lower() != "readme.md"]

    if not md_files:
        print(f"No markdown files found in {base}")
        return

    indexed = 0
    skipped = 0
    updated = 0

    for path in md_files:
        rel_path = str(path.relative_to(base))
        entry_id = make_id(rel_path)
        topic = make_topic(rel_path)

        parsed = parse_markdown(path)
        file_hash = content_hash(parsed["content"])

        if not reindex:
            existing = conn.execute(
                "SELECT metadata FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if existing and existing["metadata"]:
                meta = json.loads(existing["metadata"])
                if meta.get("content_hash") == file_hash:
                    skipped += 1
                    continue

        facets = extract_facets(parsed["content"])
        facets["source_path"] = str(path)
        facets["content_hash"] = file_hash
        metadata = json.dumps(facets)

        existing = conn.execute(
            "SELECT id FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE entries SET title = ?, content = ?, topic = ?,
                       source_skill = 'index_files', metadata = ?
                WHERE id = ?
                """,
                (parsed["title"], parsed["content"], topic, metadata, entry_id),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO entries (id, topic, title, content, source_skill, metadata)
                VALUES (?, ?, ?, ?, 'index_files', ?)
                """,
                (entry_id, topic, parsed["title"], parsed["content"], metadata),
            )
            indexed += 1

    conn.commit()
    conn.close()

    total = indexed + updated + skipped
    print(f"Scanned {total} files from {base}")
    print(f"  New: {indexed}  Updated: {updated}  Unchanged: {skipped}")


def show_status():
    """Show index statistics."""
    conn = get_connection()

    total = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    indexed = conn.execute(
        "SELECT COUNT(*) FROM entries WHERE source_skill = 'index_files'"
    ).fetchone()[0]
    manual = total - indexed

    print(f"Entries: {total} total ({indexed} from files, {manual} manual)")

    if indexed > 0:
        rows = conn.execute(
            "SELECT metadata FROM entries WHERE source_skill = 'index_files' AND metadata IS NOT NULL"
        ).fetchall()
        dirs = set()
        for row in rows:
            meta = json.loads(row["metadata"])
            if "source_path" in meta:
                parts = Path(meta["source_path"]).parts
                for i, p in enumerate(parts):
                    if p == "entries" and i > 0:
                        dirs.add("/".join(parts[: i + 1]))
                        break
        if dirs:
            print(f"  Sources: {', '.join(sorted(dirs))}")

    fts_count = conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0]
    print(f"  FTS5 indexed: {fts_count}")

    try:
        emb_count = conn.execute(
            "SELECT COUNT(*) FROM embeddings WHERE source_table = 'entries'"
        ).fetchone()[0]
        print(f"  Embeddings: {emb_count}")
    except Exception:
        print("  Embeddings: (table not created)")

    conn.close()
