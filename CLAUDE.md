# CLAUDE.md

Agent-directed retrieval lab using SQLite. Local-only, no remote.

## Quick Orientation

```bash
python3 scripts/db.py describe    # schema, row counts, sample data for all tables
python3 scripts/db.py tables      # list tables
python3 scripts/db.py search "query"   # FTS5 full-text search
```

## Database

SQLite at `shared.db`. Initialize: `python3 scripts/init-db.py` (runs `schema.sql`).

### Tables

| Table | Purpose | Rows | Script |
|-------|---------|------|--------|
| `entries` | Knowledge entries with topics, content, metadata facets | 7 | `entry.py` |
| `claims` | Tracked beliefs with status (IN/OUT/STALE), dependencies, staleness cascade | 12 | `claims.py` |
| `embeddings` | Semantic vectors (BAAI/bge-small-en-v1.5) for entries and claims | 19 | `embed.py` |
| `entry_links` | Typed relationships (related, supersedes, extends, contradicts) | 3 | `db.py` |
| `entries_fts` | FTS5 virtual table, auto-synced via triggers | — | — |
| `history` | Event log | 0 | — |
| `threads` / `messages` | Conversation context | 0 | — |
| `sources` | External source registry | 0 | — |

### Key Columns

- `entries.metadata` — JSON with auto-extracted facets: `file_paths`, `identifiers`, `urls`, `functions`
- `claims.status` — `IN` (active), `OUT` (retracted/superseded), `STALE` (needs review)
- `claims.assumes` / `claims.depends_on` — JSON arrays of claim IDs for dependency chains
- `claims.superseded_by` — points to replacement claim when resolved
- `entry_links.relation` — one of: `related`, `supersedes`, `extends`, `contradicts`

## Scripts

### `scripts/db.py` — Query and Discovery

```bash
python3 scripts/db.py query "SQL"     # run arbitrary SQL
python3 scripts/db.py tables          # list all tables
python3 scripts/db.py schema TABLE    # show column types for a table
python3 scripts/db.py search "terms"  # FTS5 full-text search (BM25 ranked)
python3 scripts/db.py describe        # full orientation: all tables, schemas, sample rows
```

### `scripts/entry.py` — Entry Management

```bash
python3 scripts/entry.py add --topic TOPIC --title TITLE --content "text"
python3 scripts/entry.py add --topic TOPIC --title TITLE --stdin  # pipe content in
python3 scripts/entry.py list [--topic TOPIC]
python3 scripts/entry.py show ID
python3 scripts/entry.py search QUERY
```

Entries auto-extract metadata facets (file paths, identifiers, URLs, functions) at insert time via regex.

### `scripts/claims.py` — Belief Management

```bash
python3 scripts/claims.py add CLAIM_ID --text "claim text" [--source SRC] [--assumes ID,ID]
python3 scripts/claims.py list [--status IN|OUT|STALE]
python3 scripts/claims.py show ID           # full details + dependents
python3 scripts/claims.py stale ID --reason "why"   # marks STALE + cascades to dependents
python3 scripts/claims.py resolve ID --superseded-by NEW_ID
python3 scripts/claims.py retract ID        # mark OUT with no replacement
python3 scripts/claims.py audit             # full status report
```

Staleness cascades: marking a claim STALE automatically propagates to all claims that assume or depend on it.

### `scripts/embed.py` — Semantic Search (requires `uv run`)

```bash
uv run python scripts/embed.py index                     # embed all entries + claims
uv run python scripts/embed.py search "query text"       # cosine similarity search
uv run python scripts/embed.py similar ID                 # find items similar to ID
uv run python scripts/embed.py contradictions             # embedding-based contradiction candidates
uv run python scripts/embed.py contradictions --verify    # + LLM second pass via claude -p
```

`embed.py` uses fastembed (uv-managed dependency) so it must be run with `uv run`. Other scripts use only stdlib.

## Patterns

- **Skills own writes, Claude owns reads.** Scripts handle INSERT/UPDATE; query freely with `db.py query`.
- **Start with `describe`** when orienting. It shows all tables, schemas, row counts, and sample data.
- **FTS5 for keyword search**, embeddings for semantic search. Use FTS5 first (free, instant), fall back to embeddings when you need meaning-based similarity.
- **Facet extraction is regex-based.** The rules are in `entry.py:extract_facets()`. They can be updated as new patterns are needed.
- **Contradiction detection is two-pass.** Embedding similarity narrows candidates (free), then LLM verifies (cheap — only N candidates instead of N² pairs).

## Gotchas

- `embed.py` requires `uv run` — fastembed is a uv-managed dependency
- Running `claude -p` from within Claude Code requires unsetting `CLAUDECODE` env var (handled in embed.py)
- This repo has **no remote** — it's a local-only lab
- Row counts in the table above are approximate; run `describe` for current state
