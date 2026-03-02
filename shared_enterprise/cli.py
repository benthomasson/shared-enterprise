"""Unified CLI for shared-enterprise."""

import argparse
import sys

from . import __version__


def main():
    parser = argparse.ArgumentParser(
        prog="shared-enterprise",
        description="Files for authoring, database as read index",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # -- init --
    subparsers.add_parser("init", help="Initialize database from schema.sql")

    # -- index --
    index_p = subparsers.add_parser("index", help="Index markdown files from a directory")
    index_p.add_argument("directory", help="Directory to scan")
    index_p.add_argument("--reindex", action="store_true", help="Force re-index all files")

    # -- status --
    subparsers.add_parser("status", help="Show index statistics")

    # -- search --
    search_p = subparsers.add_parser("search", help="Full-text search across entries")
    search_p.add_argument("terms", help="Search terms")

    # -- context --
    context_p = subparsers.add_parser("context", help="Multi-source retrieval for a topic")
    context_p.add_argument("terms", help="Topic to gather context for")

    # -- describe --
    subparsers.add_parser("describe", help="Describe all tables with schema and samples")

    # -- query --
    query_p = subparsers.add_parser("query", help="Execute raw SQL query")
    query_p.add_argument("sql", help="SQL query to execute")

    # -- tables --
    subparsers.add_parser("tables", help="List all tables")

    # -- schema --
    schema_p = subparsers.add_parser("schema", help="Show table schema")
    schema_p.add_argument("table", help="Table name")

    # -- import-beliefs --
    import_p = subparsers.add_parser("import-beliefs", help="Import claims from a beliefs.md file")
    import_p.add_argument("file", help="Path to beliefs.md")

    # -- import-nogoods --
    import_ng = subparsers.add_parser("import-nogoods", help="Import nogoods from a nogoods.md file")
    import_ng.add_argument("file", help="Path to nogoods.md")

    # -- entry (subgroup) --
    entry_p = subparsers.add_parser("entry", help="Entry management")
    entry_sub = entry_p.add_subparsers(dest="entry_command")

    entry_add = entry_sub.add_parser("add", help="Add a new entry")
    entry_add.add_argument("--topic", required=True, help="Entry topic")
    entry_add.add_argument("--title", required=True, help="Entry title")
    entry_add.add_argument("--content", help="Entry content")
    entry_add.add_argument("--stdin", action="store_true", help="Read content from stdin")

    entry_list = entry_sub.add_parser("list", help="List entries")
    entry_list.add_argument("--topic", help="Filter by topic")

    entry_show = entry_sub.add_parser("show", help="Show an entry")
    entry_show.add_argument("id", help="Entry ID")

    entry_search = entry_sub.add_parser("search", help="Search entries")
    entry_search.add_argument("query", help="Search query")

    entry_sub.add_parser("backfill", help="Re-extract facets for entries with NULL metadata")

    # -- claims (subgroup) --
    claims_p = subparsers.add_parser("claims", help="Belief/claim management")
    claims_sub = claims_p.add_subparsers(dest="claims_command")

    claims_add = claims_sub.add_parser("add", help="Add a new claim")
    claims_add.add_argument("id", help="Claim ID")
    claims_add.add_argument("--text", required=True, help="Claim text")
    claims_add.add_argument("--source", help="Source reference")
    claims_add.add_argument("--assumes", nargs="*", help="Assumed claim IDs")
    claims_add.add_argument("--depends-on", nargs="*", help="Dependency claim IDs")

    claims_list = claims_sub.add_parser("list", help="List claims")
    claims_list.add_argument("--status", help="Filter by status (IN, OUT, STALE)")

    claims_show = claims_sub.add_parser("show", help="Show claim details")
    claims_show.add_argument("id", help="Claim ID")

    claims_stale = claims_sub.add_parser("stale", help="Mark a claim as stale")
    claims_stale.add_argument("id", help="Claim ID")
    claims_stale.add_argument("--reason", required=True, help="Reason for staleness")

    claims_resolve = claims_sub.add_parser("resolve", help="Resolve a stale claim")
    claims_resolve.add_argument("id", help="Claim ID to resolve")
    claims_resolve.add_argument("--superseded-by", required=True, help="Replacement claim ID")

    claims_retract = claims_sub.add_parser("retract", help="Retract a claim")
    claims_retract.add_argument("id", help="Claim ID")

    claims_link = claims_sub.add_parser("link", help="Link a claim to an entry")
    claims_link.add_argument("id", help="Claim ID")
    claims_link.add_argument("entry_id", help="Entry ID to link to")
    claims_link.add_argument("--relation", default="related", help="Relationship type")

    claims_sub.add_parser("audit", help="Run a full belief audit")

    # -- embed (subgroup) --
    embed_p = subparsers.add_parser("embed", help="Embedding-based semantic search")
    embed_sub = embed_p.add_subparsers(dest="embed_command")

    embed_sub.add_parser("index", help="Embed all entries and claims")

    embed_search = embed_sub.add_parser("search", help="Semantic search")
    embed_search.add_argument("query", help="Search query")

    embed_similar = embed_sub.add_parser("similar", help="Find similar items")
    embed_similar.add_argument("id", help="Item ID")

    embed_contra = embed_sub.add_parser("contradictions", help="Find potential contradictions")
    embed_contra.add_argument("--verify", action="store_true", help="Use LLM to verify")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # -- Dispatch --
    if args.command == "init":
        from .db import init_db
        init_db()

    elif args.command == "index":
        from .index_files import index_directory
        index_directory(args.directory, reindex=args.reindex)

    elif args.command == "status":
        from .index_files import show_status
        show_status()

    elif args.command == "search":
        from .db import search
        search(args.terms)

    elif args.command == "context":
        from .db import context
        context(args.terms)

    elif args.command == "describe":
        from .db import describe
        describe()

    elif args.command == "query":
        from .db import query
        query(args.sql)

    elif args.command == "tables":
        from .db import tables
        tables()

    elif args.command == "schema":
        from .db import schema
        schema(args.table)

    elif args.command == "import-beliefs":
        from .claims import import_beliefs
        import_beliefs(args.file)

    elif args.command == "import-nogoods":
        from .claims import import_nogoods
        import_nogoods(args.file)

    elif args.command == "entry":
        if not args.entry_command:
            entry_p.print_help()
            sys.exit(1)
        from . import entry as entry_mod
        if args.entry_command == "add":
            content = args.content
            if args.stdin:
                content = sys.stdin.read()
            if not content:
                print("Error: --content or --stdin required")
                sys.exit(1)
            entry_mod.add_entry(args.topic, args.title, content)
        elif args.entry_command == "list":
            entry_mod.list_entries(topic=args.topic)
        elif args.entry_command == "show":
            entry_mod.show_entry(args.id)
        elif args.entry_command == "search":
            entry_mod.search_entries(args.query)
        elif args.entry_command == "backfill":
            entry_mod.backfill_facets()

    elif args.command == "claims":
        if not args.claims_command:
            claims_p.print_help()
            sys.exit(1)
        from . import claims as claims_mod
        if args.claims_command == "add":
            claims_mod.add_claim(args.id, args.text, source=args.source,
                                assumes=args.assumes, depends_on=args.depends_on)
        elif args.claims_command == "list":
            claims_mod.list_claims(status=args.status)
        elif args.claims_command == "show":
            claims_mod.show_claim(args.id)
        elif args.claims_command == "stale":
            claims_mod.mark_stale(args.id, args.reason)
        elif args.claims_command == "resolve":
            claims_mod.resolve(args.id, args.superseded_by)
        elif args.claims_command == "retract":
            claims_mod.retract(args.id)
        elif args.claims_command == "link":
            claims_mod.link_claim(args.id, args.entry_id, relation=args.relation)
        elif args.claims_command == "audit":
            claims_mod.audit()

    elif args.command == "embed":
        if not args.embed_command:
            embed_p.print_help()
            sys.exit(1)
        from . import embed as embed_mod
        if args.embed_command == "index":
            embed_mod.index_all()
        elif args.embed_command == "search":
            embed_mod.search_embeddings(args.query)
        elif args.embed_command == "similar":
            embed_mod.similar(args.id)
        elif args.embed_command == "contradictions":
            embed_mod.find_contradictions(verify=args.verify)


if __name__ == "__main__":
    main()
