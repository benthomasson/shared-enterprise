# CLAUDE.md

Files for authoring, database as read index.

## Quick Start

```bash
# Install
uv tool install -e .

# Initialize and index
shared-enterprise init
shared-enterprise index entries/

# Search
shared-enterprise search "query"
shared-enterprise context "topic"    # multi-source retrieval
shared-enterprise describe          # orientation: tables, schemas, samples
```

## CLI Reference

```bash
shared-enterprise init                              # create shared.db from schema.sql
shared-enterprise index DIRECTORY [--reindex]        # index markdown files
shared-enterprise status                             # index stats
shared-enterprise search "terms"                     # FTS5 search
shared-enterprise context "query"                    # multi-source retrieval
shared-enterprise describe                           # full orientation
shared-enterprise query "SQL"                        # raw SQL
shared-enterprise tables                             # list tables
shared-enterprise schema TABLE                       # show table schema
shared-enterprise entry add --topic T --title T ...  # manual entry
shared-enterprise entry list [--topic T]
shared-enterprise entry show ID
shared-enterprise entry search "query"
shared-enterprise entry backfill                     # re-extract facets
shared-enterprise claims add ID --text "..." [--source SRC]
shared-enterprise claims list [--status IN]
shared-enterprise claims show ID                     # details + links + history
shared-enterprise claims stale ID --reason "..."     # cascade to dependents
shared-enterprise claims resolve ID --superseded-by X
shared-enterprise claims retract ID
shared-enterprise claims link ID ENTRY_ID
shared-enterprise claims audit                       # full health report
shared-enterprise embed index                        # requires fastembed
shared-enterprise embed search "query"
shared-enterprise embed similar ID
shared-enterprise embed contradictions [--verify]
```

## Database

SQLite at `shared.db` in the current working directory.

### Tables

| Table | Purpose |
|-------|---------|
| `entries` | Knowledge entries with topics, content, metadata facets |
| `claims` | Tracked beliefs with status (IN/OUT/STALE), dependencies |
| `embeddings` | Semantic vectors (BAAI/bge-small-en-v1.5) |
| `entry_links` | Typed relationships (related, supersedes, extends, contradicts) |
| `entries_fts` | FTS5 virtual table, auto-synced via triggers |
| `history` | Event log with related_ids |
| `history_refs` | Normalized reverse index from history.related_ids |

### Key Columns

- `entries.metadata` — JSON with auto-extracted facets: `file_paths`, `identifiers`, `urls`, `functions`
- `claims.status` — `IN` (active), `OUT` (retracted/superseded), `STALE` (needs review)
- `claims.assumes` / `claims.depends_on` — JSON arrays of claim IDs
- `entry_links.relation` — one of: `related`, `supersedes`, `extends`, `contradicts`

## Source Conventions

| Prefix | Meaning | Staleness checkable | Example |
|--------|---------|---------------------|---------|
| `repo:path` | File in a git repo | Yes | `agents-python:src/.../client.py` |
| `observation:` | Direct observation | No | `observation:gcloud-sdk-model-list` |
| `analysis:` | Reasoning in a document | No | `analysis:sdd-counterargument` |
| `experience:` | Hands-on experience | No | `experience:code-explainer` |

## Patterns

- **Start with `describe`** when orienting — shows all tables, schemas, row counts, sample data.
- **`context` for multi-source retrieval** — searches FTS5 entries, claims, history, facets, and embeddings in one call.
- **Staleness cascades** — marking a claim STALE propagates to all claims that assume or depend on it.
- **Embeddings are optional** — install with `uv tool install -e ".[embeddings]"` or `uv run --extra embeddings shared-enterprise embed ...`
- **Contradiction detection is two-pass** — embedding similarity narrows candidates, `--verify` runs LLM second pass.
