---
name: shared-enterprise
description: Manage the shared-enterprise knowledge base — index files, search, query, manage beliefs and entries
argument-hint: "[command] [args...]"
allowed-tools: Bash(shared-enterprise *), Bash(uvx *shared-enterprise*), Read, Grep
---

You are managing a shared-enterprise knowledge base. This tool indexes markdown files into SQLite for structured retrieval. Files are for authoring, the database is a read index.

## Installation

```bash
# Install as uv tool (from local checkout)
uv tool install -e /path/to/shared-enterprise

# Or run directly with uvx
uvx --from git+https://github.com/benthomasson/shared-enterprise shared-enterprise [command]
```

## Setup

```bash
# Initialize database in current directory
shared-enterprise init

# Index markdown files
shared-enterprise index entries/
shared-enterprise index entries/ --reindex  # force re-index all

# Full sync: index + beliefs + nogoods in one command
shared-enterprise sync
shared-enterprise sync --reindex  # force re-index all

# Check index status
shared-enterprise status
```

## Search & Retrieval

```bash
# Full-text search (FTS5)
shared-enterprise search "convergence"

# Multi-source context retrieval (FTS + claims + history + facets + embeddings)
shared-enterprise context "query planning"

# Raw SQL
shared-enterprise query "SELECT id, title FROM entries WHERE topic = 'retrieval'"

# Explore database structure
shared-enterprise describe
shared-enterprise tables
shared-enterprise schema entries
```

## Entry Management

```bash
# Add an entry
shared-enterprise entry add --topic "retrieval" --title "Query Experiment" --content "..."

# List entries
shared-enterprise entry list
shared-enterprise entry list --topic "retrieval"

# Show entry details
shared-enterprise entry show ENTRY_ID

# Search entries by content
shared-enterprise entry search "keyword"

# Re-extract facets for entries missing metadata
shared-enterprise entry backfill
```

## Belief/Claim Management

```bash
# Add a claim
shared-enterprise claims add claim-name --text "What I learned" --source "repo:path/to/file"

# List claims
shared-enterprise claims list
shared-enterprise claims list --status IN

# Show claim with linked entries and history
shared-enterprise claims show claim-name

# Mark stale (cascades to dependents)
shared-enterprise claims stale claim-name --reason "source file changed"

# Resolve or retract
shared-enterprise claims resolve old-claim --superseded-by new-claim
shared-enterprise claims retract old-claim

# Link claim to entry
shared-enterprise claims link claim-name ENTRY_ID --relation related

# Full audit
shared-enterprise claims audit
```

## Embedding Search (requires fastembed)

```bash
# Install with embeddings support
uv tool install -e ".[embeddings]" /path/to/shared-enterprise

# Build embedding index
shared-enterprise embed index

# Semantic search
shared-enterprise embed search "multi-agent orchestration"

# Find similar items
shared-enterprise embed similar ITEM_ID

# Find contradictions among IN claims
shared-enterprise embed contradictions
shared-enterprise embed contradictions --verify  # LLM second pass
```

## Source Conventions

When adding claims, use these source prefixes:
- `repo:path/to/file` — traceable to a file (staleness-checkable)
- `observation:context` — observed behavior
- `analysis:context` — derived from reasoning
- `experience:context` — learned from practice

## Workflow

1. Write markdown files in `entries/` (files for authoring)
2. Run `shared-enterprise index entries/` to index into SQLite
3. Use `shared-enterprise context "topic"` for multi-source retrieval
4. Distill key findings into claims with `shared-enterprise claims add`
5. Run `shared-enterprise claims audit` periodically to check health

## Natural Language

If the user says something like:
- "search for X" → `shared-enterprise search "X"` or `shared-enterprise context "X"`
- "add a belief that..." → `shared-enterprise claims add ...`
- "what do we know about X" → `shared-enterprise context "X"`
- "index the entries" → `shared-enterprise index entries/`
