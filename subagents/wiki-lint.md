---
name: wiki-lint
description: >
  Run a health check over the wiki/ knowledge base - orphan pages, broken
  links, unresolved contradictions, stale pages. Use when the user asks to
  "lint the wiki" or periodically after several ingests.
---

# Wiki lint

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
modify any existing page here, and never write to wiki/latency.log
yourself either.

Note: wiki/latency.log is written automatically by a code-side callback
in agent.py, which measures real wall-clock time around this subagent's
invocation and captures your final report text from the return value -
nothing to log here.