#!/usr/bin/env python3
"""
Embedding-based semantic search for shared-enterprise.

Usage:
    ./scripts/embed.py index                    # Embed all entries and claims
    ./scripts/embed.py search "query text"      # Find semantically similar items
    ./scripts/embed.py similar ID               # Find items similar to a given ID
    ./scripts/embed.py contradictions            # Find potential contradictions among claims
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

DB_PATH = Path(__file__).parent.parent / "shared.db"
MODEL_NAME = "BAAI/bge-small-en-v1.5"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_model():
    return TextEmbedding(model_name=MODEL_NAME)


def store_embedding(conn, item_id, source_table, vector):
    """Store an embedding vector as a numpy blob."""
    blob = vector.astype(np.float32).tobytes()
    conn.execute(
        """
        INSERT OR REPLACE INTO embeddings (id, source_table, vector, model)
        VALUES (?, ?, ?, ?)
        """,
        (item_id, source_table, blob, MODEL_NAME),
    )


def load_embeddings(conn, source_table=None):
    """Load all embeddings, optionally filtered by source table."""
    if source_table:
        rows = conn.execute(
            "SELECT id, source_table, vector FROM embeddings WHERE source_table = ?",
            (source_table,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT id, source_table, vector FROM embeddings").fetchall()

    results = []
    for row in rows:
        vec = np.frombuffer(row["vector"], dtype=np.float32)
        results.append((row["id"], row["source_table"], vec))
    return results


def cosine_similarity(a, b):
    """Compute cosine similarity between two vectors."""
    dot = np.dot(a, b)
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def index_all():
    """Embed all entries and claims."""
    conn = get_connection()

    # Ensure embeddings table exists
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            source_table TEXT NOT NULL,
            vector BLOB NOT NULL,
            model TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    model = get_model()

    # Collect texts to embed
    items = []

    entries = conn.execute("SELECT id, title, content FROM entries").fetchall()
    for e in entries:
        text = f"{e['title']}. {e['content']}"
        items.append((e["id"], "entries", text))

    claims = conn.execute("SELECT id, text FROM claims").fetchall()
    for c in claims:
        items.append((c["id"], "claims", c["text"]))

    if not items:
        print("Nothing to embed")
        return

    # Batch embed
    texts = [item[2] for item in items]
    print(f"Embedding {len(texts)} items with {MODEL_NAME}...")
    vectors = list(model.embed(texts))

    for (item_id, source_table, _text), vector in zip(items, vectors):
        store_embedding(conn, item_id, source_table, vector)

    conn.commit()
    conn.close()
    print(f"Indexed {len(items)} items ({len(entries)} entries, {len(claims)} claims)")


def search(query):
    """Find items semantically similar to a query string."""
    conn = get_connection()
    model = get_model()

    query_vec = list(model.embed([query]))[0]
    all_embeddings = load_embeddings(conn)

    if not all_embeddings:
        print("No embeddings indexed. Run: python scripts/embed.py index")
        return

    # Score all items
    scored = []
    for item_id, source_table, vec in all_embeddings:
        sim = cosine_similarity(query_vec, vec)
        scored.append((sim, item_id, source_table))

    scored.sort(reverse=True)

    # Show top results
    print(f"Search: \"{query}\"\n")
    for sim, item_id, source_table in scored[:10]:
        if sim < 0.3:
            break

        # Fetch the actual text
        if source_table == "entries":
            row = conn.execute("SELECT title, content FROM entries WHERE id = ?", (item_id,)).fetchone()
            label = row["title"] if row else item_id
        else:
            row = conn.execute("SELECT text FROM claims WHERE id = ?", (item_id,)).fetchone()
            label = row["text"][:80] if row else item_id

        print(f"  {sim:.3f}  [{source_table}] {item_id}: {label}")

    conn.close()


def similar(item_id):
    """Find items similar to a given ID."""
    conn = get_connection()

    # Find the target embedding
    row = conn.execute("SELECT vector FROM embeddings WHERE id = ?", (item_id,)).fetchone()
    if not row:
        print(f"No embedding for: {item_id}")
        print("Run: python scripts/embed.py index")
        return

    target_vec = np.frombuffer(row["vector"], dtype=np.float32)
    all_embeddings = load_embeddings(conn)

    scored = []
    for eid, source_table, vec in all_embeddings:
        if eid == item_id:
            continue
        sim = cosine_similarity(target_vec, vec)
        scored.append((sim, eid, source_table))

    scored.sort(reverse=True)

    # Get label for target
    entry = conn.execute("SELECT title FROM entries WHERE id = ?", (item_id,)).fetchone()
    claim = conn.execute("SELECT text FROM claims WHERE id = ?", (item_id,)).fetchone()
    target_label = (entry["title"] if entry else claim["text"][:80] if claim else item_id)

    print(f"Similar to: {item_id} ({target_label})\n")
    for sim, eid, source_table in scored[:10]:
        if sim < 0.3:
            break
        if source_table == "entries":
            r = conn.execute("SELECT title FROM entries WHERE id = ?", (eid,)).fetchone()
            label = r["title"] if r else eid
        else:
            r = conn.execute("SELECT text FROM claims WHERE id = ?", (eid,)).fetchone()
            label = r["text"][:80] if r else eid
        print(f"  {sim:.3f}  [{source_table}] {eid}: {label}")

    conn.close()


async def llm_check_contradiction(text_a, text_b, id_a, id_b):
    """Ask an LLM whether two claims contradict each other."""
    prompt = f"""Do these two claims contradict each other? Answer with a JSON object.

Claim A ({id_a}): {text_a}
Claim B ({id_b}): {text_b}

Respond ONLY with JSON:
{{"contradicts": true/false, "explanation": "one sentence why or why not"}}"""

    import os
    env = {**os.environ}
    env.pop("CLAUDECODE", None)
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", prompt, "--model", "haiku",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        return {"contradicts": None, "explanation": f"LLM error: {stderr.decode().strip()}"}

    response = stdout.decode().strip()
    # Extract JSON from response
    try:
        # Handle case where LLM wraps in markdown
        if "```" in response:
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
        return json.loads(response)
    except (json.JSONDecodeError, IndexError):
        return {"contradicts": None, "explanation": f"Could not parse: {response[:100]}"}


def find_contradictions(verify=False):
    """Find potential contradictions among IN claims by high similarity."""
    conn = get_connection()

    # Load only IN claims
    in_claims = conn.execute("SELECT id, text FROM claims WHERE status = 'IN'").fetchall()
    claim_embeddings = load_embeddings(conn, source_table="claims")

    # Filter to only IN claims
    in_ids = {c["id"] for c in in_claims}
    claim_vecs = [(eid, vec) for eid, _, vec in claim_embeddings if eid in in_ids]

    if len(claim_vecs) < 2:
        print("Need at least 2 IN claims to check for contradictions")
        return

    # Find high-similarity pairs
    pairs = []
    for i, (id_a, vec_a) in enumerate(claim_vecs):
        for id_b, vec_b in claim_vecs[i + 1:]:
            sim = cosine_similarity(vec_a, vec_b)
            if sim > 0.6:
                pairs.append((sim, id_a, id_b))

    pairs.sort(reverse=True)

    if not pairs:
        print("No high-similarity claim pairs found (threshold: 0.6)")
        return

    print(f"Embedding filter: {len(in_ids)} claims -> {len(pairs)} candidate pairs\n")

    if not verify:
        print("Candidate pairs (use --verify for LLM second pass):\n")
        for sim, id_a, id_b in pairs:
            text_a = conn.execute("SELECT text FROM claims WHERE id = ?", (id_a,)).fetchone()["text"]
            text_b = conn.execute("SELECT text FROM claims WHERE id = ?", (id_b,)).fetchone()["text"]
            print(f"  {sim:.3f}  {id_a} <-> {id_b}")
            print(f"    A: {text_a}")
            print(f"    B: {text_b}")
            print()
    else:
        print(f"Running LLM verification on {len(pairs)} pairs...\n")
        results = asyncio.run(_verify_pairs(conn, pairs))

        contradictions = [(sim, id_a, id_b, r) for (sim, id_a, id_b), r in zip(pairs, results) if r.get("contradicts")]
        compatible = [(sim, id_a, id_b, r) for (sim, id_a, id_b), r in zip(pairs, results) if r.get("contradicts") is False]
        errors = [(sim, id_a, id_b, r) for (sim, id_a, id_b), r in zip(pairs, results) if r.get("contradicts") is None]

        if contradictions:
            print(f"CONTRADICTIONS FOUND ({len(contradictions)}):\n")
            for sim, id_a, id_b, result in contradictions:
                text_a = conn.execute("SELECT text FROM claims WHERE id = ?", (id_a,)).fetchone()["text"]
                text_b = conn.execute("SELECT text FROM claims WHERE id = ?", (id_b,)).fetchone()["text"]
                print(f"  {sim:.3f}  {id_a} <-> {id_b}")
                print(f"    A: {text_a}")
                print(f"    B: {text_b}")
                print(f"    Why: {result.get('explanation', '')}")
                print()
        else:
            print("No contradictions found.\n")

        if compatible:
            print(f"Compatible pairs ({len(compatible)}): {[(id_a, id_b) for _, id_a, id_b, _ in compatible]}")

        if errors:
            print(f"Errors ({len(errors)}):")
            for _, id_a, id_b, r in errors:
                print(f"  {id_a} <-> {id_b}: {r.get('explanation', 'unknown')}")

    conn.close()


async def _verify_pairs(conn, pairs):
    """Run LLM verification on all candidate pairs concurrently."""
    tasks = []
    for sim, id_a, id_b in pairs:
        text_a = conn.execute("SELECT text FROM claims WHERE id = ?", (id_a,)).fetchone()["text"]
        text_b = conn.execute("SELECT text FROM claims WHERE id = ?", (id_b,)).fetchone()["text"]
        tasks.append(llm_check_contradiction(text_a, text_b, id_a, id_b))
    return await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="Embedding-based semantic search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("index", help="Embed all entries and claims")

    search_p = subparsers.add_parser("search", help="Semantic search")
    search_p.add_argument("query", help="Search query")

    similar_p = subparsers.add_parser("similar", help="Find similar items")
    similar_p.add_argument("id", help="Item ID")

    contra_p = subparsers.add_parser("contradictions", help="Find potential contradictions")
    contra_p.add_argument("--verify", action="store_true", help="Use LLM to verify candidates")

    args = parser.parse_args()

    if args.command == "index":
        index_all()
    elif args.command == "search":
        search(args.query)
    elif args.command == "similar":
        similar(args.id)
    elif args.command == "contradictions":
        find_contradictions(verify=args.verify)


if __name__ == "__main__":
    main()
