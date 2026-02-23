# shared-enterprise

Database-backed shared-understanding for enterprise contexts.

## Overview

This is an experiment in scaling the [shared-understanding](https://github.com/benthomasson/shared-understanding) pattern with a database backend.

**Key change:** Content lives in a SQLite database instead of markdown files, but Claude has direct SQL access for queries.

## Why

The file-based approach works well for small-to-medium contexts:
- `grep`, `read`, `glob` are fast
- Git handles versioning and distribution
- Simple to understand and debug

But at scale:
- Complex queries need SQL (JOINs, aggregations, filtering)
- Row-level security becomes important
- Multi-tenant scenarios need proper isolation

## How It Works

```
┌─────────────────────────────────────────┐
│              shared.db                   │
├─────────┬─────────┬─────────┬───────────┤
│ entries │ claims  │ history │ messages  │
└────┬────┴────┬────┴────┬────┴─────┬─────┘
     │         │         │          │
     ▼         ▼         ▼          ▼
  /entry   /beliefs  /history   /thread
   skill     skill     skill     skill
```

- **Skills own writes** - Validated INSERT/UPDATE paths
- **Claude owns reads** - Direct SQL queries
- **Git shares skills** - The schema and skills are version controlled
- **Database is local** - Each instance has its own data

## Quick Start

```bash
# Initialize database
python scripts/init-db.py

# Add an entry
python scripts/entry.py add --topic "test" --title "First Entry" --content "Hello world"

# Query
python scripts/db.py query "SELECT * FROM entries"

# Or direct sqlite
sqlite3 shared.db "SELECT * FROM entries"
```

## Skills

| Skill | Table(s) | Purpose |
|-------|----------|---------|
| /entry | entries | General content |
| /beliefs | claims | Tracked claims with staleness detection |
| /history | history | Event log |
| /thread | threads, messages | Conversations |

## Design Principles

1. **Append-mostly** - INSERT >> UPDATE >> DELETE
2. **Skills validate** - No raw INSERTs from Claude
3. **SQL for reads** - Claude writes queries as needed
4. **Local data** - Database doesn't go in git
5. **Shared schema** - Schema and skills are version controlled

## License

MIT
