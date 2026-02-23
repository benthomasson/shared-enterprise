# Shared Enterprise

Database-backed shared-understanding for enterprise contexts.

## Concept

This repo implements the shared-understanding pattern with a database backend:
- **Skills own writes** (INSERT/UPDATE go through controlled paths)
- **Claude owns reads** (direct SQL queries as needed)
- **Distribution via git** (schema + skills, not data)

## Database

SQLite with WAL mode at `shared.db`. Initialize with:

```bash
python scripts/init-db.py
```

## Querying

You have direct database access. Query freely:

```bash
python scripts/db.py query "SELECT * FROM entries WHERE topic = 'architecture'"
python scripts/db.py tables
python scripts/db.py schema entries
```

Or use sqlite3 directly:

```bash
sqlite3 shared.db "SELECT * FROM claims WHERE status = 'IN'"
```

## Schema

| Table | Purpose | Write Skill |
|-------|---------|-------------|
| entries | General content | /entry |
| claims | Tracked beliefs | /beliefs |
| history | Event log | /history |
| threads | Conversation threads | /thread |
| messages | Thread messages | /thread |
| sources | External source registry | /source |

## Skills

- `/entry add` - Add entries to database
- `/beliefs` - Manage claims (from beliefs package)
- More to be added

## Pattern

1. User or automation triggers skill
2. Skill validates and INSERTs
3. Claude queries as needed for context
4. Changes committed to git (schema, not data)
5. Database is local, skills are shared
