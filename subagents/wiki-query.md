---
name: wiki-query
description: >
  Answer a question using only the existing wiki/ knowledge base rather
  than re-reading raw sources. Use when the user asks a question about
  ingested content or says "query the wiki" / "what do we know about X".
---

# Wiki query

1. Call `qmd_search_wiki(query)` to get a ranked list of candidate wiki/
   pages. If a `type: summary` page appears among the top results, treat
   it as the fastest route to the right entity/concept pages and open it
   first in step 2. `qmd_search_wiki` returns paths and relevance scores
   only, never page content — never treat its output as page content and
   never cite directly from it; every page you cite must still be opened
   with `read_file` in step 2. If it returns zero results, fall back to
   reading wiki/index.md directly before concluding nothing relevant
   exists.
2. Open only the relevant pages returned in step 1 - do not re-read raw/
   unless a wiki page is missing detail needed to answer.
3. Synthesize an answer, citing which wiki/ pages it came from. Every
   factual claim in your answer must be traceable to a specific wiki/
   page - end the answer with a `Sources:` line listing each wiki/ page
   path you drew from, e.g.:
     Sources: wiki/retrieval-augmented-generation.md, wiki/vector-search.md
   This is part of the final report text itself, not a separate note -
   the router will relay your report to the user verbatim, so the
   citation has to already be in the text you write, and the `Sources:`
   line must be the last line of your report.
4. If the synthesis is novel (a comparison, connection, or analysis not
   already captured on any page), propose it back to the user as a new
   wiki/ page. If approved, write it, update index.md, and log it exactly
   like an ingest operation — this includes calling `qmd_reindex_wiki` if
   you have access to it after writing the new page, so it becomes
   searchable for future queries; if you don't have that tool, note in
   your report that the page won't be searchable via QMD until the next
   ingest run.

Note: wiki/latency.log is no longer written by this skill. A code-side
callback in agent.py measures real wall-clock time around this
subagent's invocation and captures your final report text (including the
`Sources:` line) directly from the return value - nothing to log here.
This is also why the `Sources:` line must be the literal last line of
your report: the code parses it out of your returned text.