---
name: wiki-ingest
description: >
  Ingest new source files from raw/ into the wiki/ knowledge base, updating
  cross-references, index.md, and log.md. Use when the user adds new files
  to raw/ or asks to "ingest", "process new sources", or "update the wiki".
---

# Wiki ingest

1. For every file in raw/, call the `sha256_file` tool on it. Compare
   against the hash recorded in that file's most recent wiki/log.md entry:
   - No log entry for this path -> NEW.
   - Log entry exists but hash differs -> CHANGED.
   - Log entry exists and hash matches -> up to date, skip it.
   Only files marked NEW or CHANGED proceed to step 2.
2. For each new/changed source:
   - Read it fully. **If the file is a .pdf, use the `read_pdf_text` tool,
     not the generic `read_file` tool** — `read_file` returns raw PDF
     bytes as a multimodal block that some model providers reject
     outright. `read_pdf_text` extracts plain text instead.
   - Identify every existing wiki/ page it should update (not just the
     "obvious" one - check for entities, related concepts, summaries).
   - Identify any new pages it requires.
   - **Always create or update exactly one `type: summary` page for this
     source**, in addition to any `type: entity` / `type: concept` pages.
     This page is a short (3-6 sentence) overview of what the source
     document is and what it covers, plus a bullet list linking to every
     entity/concept page this ingest created or touched. Name it after the
     source, not the entity (e.g. a source `raw/Rohit Tiwari.pdf` that
     spawns `rohit-tiwari.md` (entity) and `nvidia-ai-stack.md` (concept)
     also gets a `wiki/rohit-tiwari-summary.md` (type: summary) tying them
     together) — entity/concept pages hold the granular facts, the summary
     page is the "start here" index for that source. If a summary page for
     this source already exists (CHANGED case), update it rather than
     creating a duplicate.
   - Write/update those pages per the frontmatter schema in AGENTS.md.
   - Update cross-links between affected pages.
3. If a source contradicts an existing page, flag it with `> CONTRADICTION:`
   instead of overwriting, and surface it in your final report before
   finalizing. For a CHANGED source specifically:
   - If the new content only adds information without conflicting with what
     a page already says, append/merge it into the relevant page(s) and add
     the file's new hash to sources - do not touch unrelated claims.
   - If the new content conflicts with an existing claim, do not overwrite;
     use `> CONTRADICTION:` citing both the old hash/claim and the new
     hash/claim, and ask the user which is correct.
4. Update wiki/index.md with one line per touched or new page.
5. Append one entry per ingested source to wiki/log.md, including the
   sha256 hash (from `sha256_file`) so future runs can detect edits.
   Use today's date exactly as given to you in the task description
   (the router provides it as "today's date: YYYY-MM-DD (UTC)") - never
   guess a date and never fall back on your own training-cutoff date:
   `## [YYYY-MM-DD] ingest | <source path> (sha256:<hash>) | <pages touched>`
6. If more than one reasonable way to file a source exists, ask the user
   before writing.
7. Once ALL wiki/ writes for this run are finalized (pages from step 2,
   index.md from step 4, log.md from step 5 — everything), call
   `qmd_reindex_wiki` so QMD's search index reflects the final on-disk
   state. Call this exactly once per run, after writing is complete —
   never mid-run, never per-page, and never before log.md is updated.
   If this run touched zero NEW/CHANGED sources (everything was already
   up to date in step 1), skip this call — there is nothing new to index.

Note: wiki/latency.log is no longer written by this skill. Timing
(total_s) and the final report text are captured automatically by a
code-side callback in agent.py that measures real wall-clock time around
this subagent's invocation - nothing to do here.