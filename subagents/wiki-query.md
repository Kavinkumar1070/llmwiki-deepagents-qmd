---
name: wiki-query
description: >
  Answer a question using only the existing wiki/ knowledge base rather
  than re-reading raw sources. Use when the user asks a question about
  ingested content or says "query the wiki" / "what do we know about X".
---

# Wiki query

0. Call `utc_now` and note the epoch value as T0.
1. Call `qmd_search_wiki(query)` to get a ranked list of candidate wiki/
   pages. If a `type: summary` page appears among the top results, treat
   it as the fastest route to the right entity/concept pages and open it
   first in step 2. `qmd_search_wiki` returns paths and relevance scores
   only, never page content — never treat its output as page content and
   never cite directly from it; every page you cite must still be opened
   with `read_file` in step 2. If it returns zero results, fall back to
   reading wiki/index.md directly before concluding nothing relevant
   exists. Call `utc_now` again and note the epoch value as T1.
2. Open only the relevant pages returned in step 1 - do not re-read raw/
   unless a wiki page is missing detail needed to answer. Call `utc_now`
   and note as T2.
3. Synthesize an answer, citing which wiki/ pages it came from. Every
   factual claim in your answer must be traceable to a specific wiki/
   page - end the answer with a `Sources:` line listing each wiki/ page
   path you drew from, e.g.:
     Sources: wiki/retrieval-augmented-generation.md, wiki/vector-search.md
   This is part of the final report text itself, not a separate note -
   the router will relay your report to the user verbatim, so the
   citation has to already be in the text you write. Call `utc_now` and
   note as T3.
4. If the synthesis is novel (a comparison, connection, or analysis not
   already captured on any page), propose it back to the user as a new
   wiki/ page. If approved, write it, update index.md, and log it exactly
   like an ingest operation — this includes calling `qmd_reindex_wiki` if
   you have access to it after writing the new page, so it becomes
   searchable for future queries; if you don't have that tool, note in
   your report that the page won't be searchable via QMD until the next
   ingest run. Call `utc_now` and note as T4 (else T4=T3).
5. Append one line to wiki/latency.log (create it if it doesn't exist):
   `{"ts":"<T4 iso value>","op":"query","query":"<user query, full text, no truncation>","answer":"<synthesized answer from step 3, full text including the Sources: line, no truncation>","sources":["<wiki/ page path>", ...],"index_read_s":<T1-T0>,"page_read_s":<T2-T1>,"synthesis_s":<T3-T2>,"writeback_s":<T4-T3>,"total_s":<T4-T0>}`

   `query` and `answer` are logged in full - do not shorten or truncate
   either field. `sources` is the same list of wiki/ page paths as the
   `Sources:` line in your answer - keep them identical, list all of them.
   `index_read_s` now times the `qmd_search_wiki` call (T1-T0) rather
   than a literal index.md read - the field name is kept as-is for log
   continuity with earlier entries.

   Before writing the line, JSON-escape `query` and `answer`: escape `"`
   as `\"`, `\` as `\\`, and replace any newline with a space, so the
   line stays valid single-line JSON.