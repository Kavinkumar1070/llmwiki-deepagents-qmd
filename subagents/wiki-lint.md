---
name: wiki-lint
description: >
  Run a health check over the wiki/ knowledge base - orphan pages, broken
  links, unresolved contradictions, stale pages. Use when the user asks to
  "lint the wiki" or periodically after several ingests.
---

# Wiki lint

0. Call `utc_now` and note the epoch value as T0.

Check for and report (do not auto-fix without confirmation):
1. Orphan pages - no inbound links from any other page or from index.md.
2. Broken cross-links - links pointing to pages that don't exist.
3. Unresolved `> CONTRADICTION:` flags older than one ingest cycle.
4. Pages not updated in 90+ days that reference sources contradicted by
   more recent ingests.
5. Pages missing required frontmatter fields (type, title, tags, sources,
   updated).
6. Sources in wiki/log.md with no corresponding `type: summary` page —
   every ingested source should have exactly one.

Output a short report grouped by check, then ask the user which findings
to act on. This subagent is read-only for wiki/*.md content - never
modify any existing page here.

Logging is the one exception to read-only: after producing the report,
call `utc_now` again and note the epoch value as T1, then append one
line to wiki/latency.log (create it if it doesn't exist - this is an
append-only activity log, not wiki content):
`{"ts":"<T1 iso value>","op":"lint","orphans":<count>,"broken_links":<count>,"unresolved_contradictions":<count>,"stale_pages":<count>,"missing_frontmatter":<count>,"missing_summary":<count>,"total_s":<T1-T0>}`