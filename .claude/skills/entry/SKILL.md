---
name: entry
description: Add entries to the shared-enterprise database
argument-hint: "[add|list|show|search] [args...]"
allowed-tools: Bash(python *), Bash(./scripts/*), Read, Grep
---

You are managing entries in the shared-enterprise database.

## Commands

### add
Add a new entry to the database.

```bash
python scripts/entry.py add --topic "project-analyze" --title "Architecture Review" --content "..."
```

Or with content from stdin:
```bash
echo "Content here" | python scripts/entry.py add --topic "topic" --title "Title" --stdin
```

### list
List entries, optionally filtered by topic:

```bash
python scripts/entry.py list
python scripts/entry.py list --topic "project-analyze"
```

### show
Show a specific entry by ID:

```bash
python scripts/entry.py show ENTRY_ID
```

### search
Search entries by content:

```bash
python scripts/entry.py search "keyword"
```

## Natural Language Conversion

If user says: `/entry add something about Project Analyze architecture`

Convert to:
1. Determine the topic (e.g., "project-analyze")
2. Extract or generate a title
3. Use the content provided or prompt for it
4. Run the add command

## After Adding

Confirm the entry was added and show its ID for reference.
