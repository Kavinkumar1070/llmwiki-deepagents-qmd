> Note: `agent.py` reads this file at startup and appends its contents to
> every subagent's system prompt (see `load_subagents()`), since Deep
> Agents subagents don't auto-inherit a project-level instructions file
> the way Codex CLI auto-read AGENTS.md. This stays the single source of
> truth - edit here, no need to touch agent.py.

# Wiki schema

You maintain a persistent knowledge base in wiki/. Never edit files in raw/ —
they are the immutable source of truth.

## Page format
Every wiki/ page starts with YAML frontmatter:
  type: concept | entity | summary
  title: string
  tags: [string]
  sources: [path to raw/ file(s) this page is derived from]
  updated: YYYY-MM-DD

All wiki/ pages live flat in a single wiki/ directory — do not create
type-based subfolders (entity/, concept/, summary/). The `type` field
above is the single source of truth for a page's category; a folder
structure would just duplicate that fact in a second place that can
drift out of sync with it. Organization by type is achieved by grouping
wiki/index.md into sections (see below), not by physical layout.

## Rules
- One new source in raw/ can and should update multiple existing wiki/ pages,
  not just create a single new one.
- Every claim on a page must trace back to a specific file under raw/.
- If a new source contradicts an existing page, do not silently overwrite —
  add an inline `> CONTRADICTION:` note describing both claims and their sources.
- After any change to wiki/, update wiki/index.md and append a dated entry to
  wiki/log.md.
- Every wiki/log.md entry must record the sha256 hash of the raw/ source it
  covers, in the form `(sha256:<hash>)`. This is how ingest tells a NEW file
  apart from a CHANGED file apart from an already-processed file — file
  presence in log.md is not enough, the hash must also match.

## Retrieval: wiki/index.md vs QMD search
- wiki/index.md is a human-readable, type-grouped list of all pages
  (group entries under `## Entities`, `## Concepts`, `## Summaries`
  headers, one line per page: path + one-sentence summary). It is
  updated on every ingest and is what wiki-lint reads for its orphan-
  page and broken-link checks.
- wiki/index.md and wiki/log.md are bookkeeping files, not knowledge
  pages. Both are excluded from the `wiki` QMD collection at setup time
  and must never be returned as a search result or cited as a source.
  wiki/latency.log is excluded automatically (it isn't a .md file).
- For answering a query, use the `qmd_search_wiki` tool to find
  candidate pages instead of reading index.md directly — only open
  individual pages (via read_file) after checking search results. Fall
  back to reading index.md directly only if QMD search returns nothing.
- After an ingest run finishes writing all pages, index.md, and log.md,
  call `qmd_reindex_wiki` exactly once so QMD reflects the new state.

## Filed-back pages (from wiki-query)
- These have no raw/ source. Use `sources: [wiki/ page paths this was derived from]`
  instead of raw/ paths, and set frontmatter `derived_from_query: true`.
- Log entry format: `## [YYYY-MM-DD] query | <topic> | derived from: <wiki pages> | <new page path>`
  (no sha256 — there is no raw/ file to hash).

  ## Page format
All content pages (type: concept | entity | summary) live under wiki/pages/,
e.g. wiki/pages/rohit-tiwari.md — NOT directly under wiki/. Cross-links
between pages stay as bare relative filenames (rohit-tiwari.md ->
nvidia-ai-stack.md) since all content pages are siblings inside pages/.

wiki/index.md and wiki/log.md live directly under wiki/ (one level above
pages/), by design — this folder boundary is what keeps them out of the
QMD search index, no exclude/ignore config needed. Never move them into
pages/.