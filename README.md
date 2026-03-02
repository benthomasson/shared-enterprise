# shared-enterprise

Files for authoring, database as a read index.

## Overview

Write markdown files naturally. Auto-index them into SQLite for structured querying — FTS5 keyword search, embedding-based semantic search, facet extraction, claim tracking, and multi-source convergence retrieval.

This started as an experiment in scaling the [shared-understanding](https://github.com/benthomasson/shared-understanding) pattern with a database backend. The key finding: files and databases complement rather than compete. Files are better for authoring; databases are better for retrieval. Use both.

## Quick Start

```bash
# Initialize database
python3 scripts/init-db.py

# Index markdown files from any directory
python3 scripts/index_files.py index ~/path/to/entries

# Search
python3 scripts/db.py search "query"              # FTS5 keyword search
python3 scripts/db.py context "topic"              # multi-source retrieval (4 sources)
uv run python scripts/db.py context "topic"        # multi-source retrieval (5 sources, + embeddings)

# Orientation
python3 scripts/db.py describe                     # all tables, schemas, sample data
python3 scripts/index_files.py status              # index statistics
```

## How It Works

```
  Markdown Files                    SQLite (shared.db)
  ─────────────                    ──────────────────
  entries/                    ┌──→  entries (FTS5 indexed)
    2026/03/02/              │      claims (IN/OUT/STALE)
      my-finding.md  ────────┘      embeddings (semantic vectors)
      analysis.md    ────────┘      entry_links (knowledge graph)
                                    history + history_refs
                                    sources
```

- **Files are source of truth** — write markdown, edit freely, commit to git
- **Database is a derived index** — rebuilt from files at any time
- **Five retrieval methods** — FTS5, claims, history, facets, embeddings
- **Convergence = confidence** — when multiple methods agree, the answer is reliable

## Scripts

| Script | Purpose | Requires `uv run` |
|--------|---------|-------------------|
| `index_files.py` | Auto-index markdown files into entries table | No |
| `db.py` | Query, search, describe, context (unified retrieval) | No (`context` adds embeddings under `uv run`) |
| `entry.py` | Manual entry management, facet backfill | No |
| `claims.py` | Belief tracking with staleness cascade, entry linking | No |
| `embed.py` | Embedding index, semantic search, contradiction detection | Yes |

## Key Features

**Auto-indexing** — `index_files.py` parses markdown headers, extracts facets (file paths, identifiers, URLs, functions), and upserts into SQLite. Content hashing skips unchanged files on re-index.

**Unified retrieval** — `db.py context "query"` searches FTS5 entries, claims, history, facet metadata, and semantic embeddings in one call. Each source is independent; convergence across sources indicates high confidence.

**Belief management** — `claims.py` tracks claims with status (IN/OUT/STALE), dependency chains, staleness cascade, and typed links to entries via the knowledge graph.

**Semantic search** — `embed.py` uses fastembed (BAAI/bge-small-en-v1.5) for local embedding. Two-pass contradiction detection: embedding similarity narrows candidates, LLM verifies.

**Knowledge graph** — `entry_links` table connects entries and claims with typed relationships (related, supersedes, extends, contradicts).

## Source Conventions

Claims track where knowledge came from using prefixed source strings:

| Prefix | Meaning | Staleness checkable |
|--------|---------|---------------------|
| `repo:path` | File in a git repo | Yes |
| `observation:` | Tool/system output | No |
| `analysis:` | Reasoning in an entry | No |
| `experience:` | Hands-on experience | No |

## Design Principles

1. **Files for authoring, database for retrieval** — don't force a choice
2. **Independence enables convergence** — keep retrieval methods separate
3. **Pay tokens once, run free forever** — write a regex/rule/embedding once, reuse deterministically
4. **No artifact is disposable** — every traversal between representations costs tokens
5. **Local data, shared schema** — database is gitignored, scripts are version controlled

## License

MIT
