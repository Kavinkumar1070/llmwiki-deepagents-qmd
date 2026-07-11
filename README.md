# LLM Wiki — Deep Agents + QMD

A persistent, self-updating markdown knowledge base built on [Deep Agents](https://github.com/langchain-ai/deepagents), ported from an earlier Codex CLI + skills setup. New source documents get ingested once, distilled into cross-linked wiki pages, and answered back through hybrid search — instead of re-reading raw sources on every question.

Inspired by Andrej Karpathy's "LLM Wiki" pattern: raw sources are immutable, the wiki compounds over time, and every claim traces back to a source.

## How it works

```
raw/            immutable source files (PDFs, docs) — never edited by the agent
wiki/pages/     LLM-maintained knowledge pages (type: entity | concept | summary)
wiki/index.md   human-readable, type-grouped page index (bookkeeping)
wiki/log.md     dated ingest log with sha256 hashes (bookkeeping)
wiki/latency.log  append-only JSONL activity/timing log for every operation
```

A router agent reads the request and delegates to one of three subagents via Deep Agents' `task` tool. Each subagent is a single markdown file (YAML frontmatter + prompt body) with its own scoped toolset, does its work in an isolated context, and returns just the final report:

| Subagent | Trigger | What it does |
|---|---|---|
| **wiki-ingest** | new files in `raw/`, "ingest", "process new sources" | Hashes each source (sha256), skips unchanged files, writes/updates entity/concept/summary pages, flags contradictions instead of overwriting, updates `index.md` + `log.md`, reindexes QMD |
| **wiki-query** | "what do we know about X", general questions | Hybrid-searches the wiki via QMD, opens only the matched pages, synthesizes a cited answer, optionally proposes a new page for novel synthesis |
| **wiki-lint** | "lint the wiki", periodic health checks | Read-only report on orphan pages, broken links, unresolved contradictions, stale pages, missing frontmatter |

The underlying model is Azure OpenAI (GPT), auto-detected from environment variables — falls back to any LangChain-resolvable model string otherwise.

## Retrieval: QMD hybrid search

Instead of the agent reading `index.md` by hand, `wiki-query` searches first and only opens what comes back:

```
question → qmd_search_wiki → [ranked {file, score}, ...] → read_file each → cited answer
```

Search runs three sub-query types together against QMD's local MCP server:

- **lex** — lexical/BM25 term matching
- **vec** — embedding similarity (nearest-neighbor over pre-computed vectors)
- **hyde** — QMD generates its own hypothetical answer server-side, then embeds that (HyDE technique)

Search results are **paths and scores only** — never treated as page content. Every citation must come from an actual `read_file` call, keeping the grounding chain honest.

### Query rewriting

Before searching, the raw question is rewritten into a keyword-dense phrase for the lexical sub-query specifically (stopwords and question-phrasing stripped, since BM25 rewards exact term overlap). Vector and HyDE searches keep the original question unchanged — HyDE does its own answer-generation internally and expects a question, not a pre-rewritten one.

Toggle without touching code:
```bash
export QMD_QUERY_TRANSFORM=0   # disable the keyword rewrite step
```

### Folder-boundary exclusion

`index.md` and `log.md` are bookkeeping, not knowledge — they must never be searchable or cited. Rather than relying on QMD's `--exclude` patterns, the QMD collection is registered against `wiki/pages/` only; `index.md`/`log.md` live one level up in `wiki/` and are structurally out of scope for the scan. A defensive filename filter in the search layer is a second safety net on top.

## Flow logging

Every tool call (search, MCP round-trips, CLI subcommands) is traced live via `flow_logger.py` — separate from `wiki/latency.log`, which stays a clean one-line-JSON summary per completed run.

```bash
export WIKI_FLOW_LOG=1              # on by default; set to 0 to silence
export WIKI_FLOW_LOG_FILE=./wiki/flow.log   # optionally also persist to a file
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment (`.env` in the project root):
   ```
   AZURE_OPENAI_DEPLOYMENT=<your-deployment>
   AZURE_OPENAI_BASE_URL=<your-endpoint>
   AZURE_OPENAI_API_KEY=<your-key>
   AZURE_OPENAI_API_VERSION=2024-12-01-preview
   ```
3. Start the QMD MCP server:
   ```bash
   qmd mcp --http --daemon
   ```
4. One-time: register the wiki collection:
   ```python
   from qmd_ingest import ingest_folder
   ingest_folder("./wiki/pages", "wiki", mask="**/*.md")
   ```

## Usage

```bash
python agent.py "ingest the new files in raw/"
python agent.py "define rag and explain types of vector search?"
python agent.py "lint the wiki"
python agent.py            # interactive mode
```

## Project structure

```
agent.py            router agent + subagent loader
AGENTS.md           shared wiki schema/rules, appended to every subagent's prompt
subagents/
  wiki-ingest.md
  wiki-query.md
  wiki-lint.md
tools.py             deterministic tools (hashing, timestamps, PDF text) + QMD-facing tools
qmd_ingest.py         QMD CLI wrapper — collection setup, reindexing, embedding
qmd_retrieval.py       QMD MCP client — hybrid search, session handling
qmd_inspect.py         read-only QMD/SQLite inspector for debugging
query_transform.py     LLM-based keyword-query rewriting for the lexical sub-search
flow_logger.py         live step-by-step tool-call tracer
raw/                  immutable source documents
wiki/pages/           generated knowledge pages
wiki/index.md         page index (bookkeeping)
wiki/log.md           ingest log with source hashes (bookkeeping)
wiki/latency.log       per-run timing/activity summaries (JSONL)
```

## Notes

- Windows users: if you hit `ValueError: Path ... outside root directory` on write, this is a known path-canonicalization mismatch when the project sits under a reparse-point-backed folder (e.g. OneDrive-redirected `Downloads`). Handled in `agent.py` via `_win_long_path()` — see comments there, or move the project to a plain local path if it persists.
