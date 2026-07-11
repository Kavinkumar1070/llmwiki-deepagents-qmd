"""
LLM Wiki, ported from a Codex CLI + skills setup to a LangChain Deep Agent.

Same contract as the Codex version:
  raw/         - immutable source files, never edited by the agent
  wiki/        - LLM-maintained knowledge base (index.md, log.md, generated pages)
  AGENTS.md    - shared schema/rules, single source of truth
  subagents/   - one markdown file per operation (mirrors codex-skills/),
                 each with YAML frontmatter (name, description) + a prompt
                 body, loaded and turned into a Deep Agents subagent below.

The main agent's only job is to read what the user wants and delegate to
the right subagent via the built-in `task` tool - it mirrors the
"ingest / what do we know about X / lint the wiki" phrasing from the
original README.

QMD integration: wiki-ingest re-indexes the `wiki` QMD collection as its
last step; wiki-query searches that collection first, before opening any
individual page. Requires the QMD MCP server running (`qmd mcp --http
--daemon`) and the `wiki` collection already registered once via
`qmd_ingest.ingest_folder("./wiki", "wiki", mask="**/*.md",
exclude=["index.md", "log.md"])` - see tools.py / qmd_ingest.py.

Usage:
    python agent.py "ingest the new files in raw/"
    python agent.py "what do we know about diffusion models?"
    python agent.py "lint the wiki"
    python agent.py            # drops into an interactive loop
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _win_long_path(path: Path) -> str:
    """Resolve `path` to the same canonical form Windows returns when it
    walks through a reparse point (e.g. a OneDrive-redirected Downloads
    folder) — the `\\\\?\\` extended-length prefix.

    deepagents' FilesystemBackend compares `Path(...).resolve()` (which
    goes through GetFinalPathNameByHandleW on Windows and picks up that
    prefix when the parent chain includes a reparse point) against the
    `root_dir` string it was constructed with. If root_dir was passed as
    a plain path without the prefix, every write fails with a false
    "outside root directory" ValueError, even though the path IS inside
    root_dir - it's a string-form mismatch, not a real containment
    violation. Passing an already `\\\\?\\`-prefixed root_dir here makes
    both sides of that comparison use the same canonical form.

    No-op on non-Windows platforms.
    """
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        resolved = "\\\\?\\" + resolved
    return resolved

import yaml
from dotenv import load_dotenv
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from tools import (
    read_pdf_text,
    sha256_file,
    utc_now,
    qmd_reindex_wiki,
    qmd_search_wiki,
)

PROJECT_DIR = Path(__file__).resolve().parent
SUBAGENTS_DIR = PROJECT_DIR / "subagents"
AGENTS_MD = PROJECT_DIR / "AGENTS.md"

load_dotenv(PROJECT_DIR / ".env")

# Each subagent only gets the tools its own subagents/*.md actually calls:
#   wiki-ingest hashes raw/ files, reads PDFs, and reindexes QMD after
#     writing -> needs all four
#   wiki-query searches QMD first to find candidate pages, then times its
#     latency log -> needs utc_now, qmd_search_wiki
#   wiki-lint is read-only over wiki/ content but timestamps its own
#     latency.log entry -> needs utc_now only, never touches QMD or raw/
TOOLS_BY_SUBAGENT = {
    "wiki-ingest": [sha256_file, utc_now, read_pdf_text, qmd_reindex_wiki],
    "wiki-query": [utc_now, qmd_search_wiki],
    "wiki-lint": [utc_now],
}


def load_subagents() -> list[dict]:
    """Read every subagents/*.md file and turn it into a Deep Agents
    SubAgent dict. Each file is SKILL.md-shaped: YAML frontmatter with
    name/description, then a markdown body used as the system prompt.
    AGENTS.md is appended to every body so the shared schema only has to
    live in one place.
    """
    schema = AGENTS_MD.read_text(encoding="utf-8")
    subagents = []

    for path in sorted(SUBAGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise ValueError(f"{path} is missing YAML frontmatter (---...---)")

        _, frontmatter_raw, body = text.split("---", 2)
        meta = yaml.safe_load(frontmatter_raw)

        tools = TOOLS_BY_SUBAGENT.get(meta["name"], [])
        reminders = []
        if sha256_file in tools:
            reminders.append(
                "Always call the `sha256_file` tool to hash a raw/ file - "
                "never compute or guess a hash yourself."
            )
        if utc_now in tools:
            reminders.append(
                "Always call the `utc_now` tool to get the current time - "
                "never compute or guess a timestamp yourself."
            )
        if qmd_search_wiki in tools:
            reminders.append(
                "The `qmd_search_wiki` tool returns paths and relevance "
                "scores only, never page content - always open returned "
                "paths with read_file before citing anything from them."
            )
        if qmd_reindex_wiki in tools:
            reminders.append(
                "Call `qmd_reindex_wiki` exactly once per run, as the "
                "LAST step, only after all wiki/ writes (pages, "
                "index.md, log.md) are finalized."
            )

        system_prompt = (
            f"{body.strip()}\n\n"
            "## Wiki schema (shared rules - see AGENTS.md)\n\n"
            f"{schema}"
        )
        if reminders:
            system_prompt += "\n\n" + " ".join(reminders)

        subagents.append(
            {
                "name": meta["name"],
                "description": meta["description"],
                "system_prompt": system_prompt,
                "tools": tools,
            }
        )

    return subagents


ROUTER_PROMPT = """You are the LLM Wiki orchestrator. You maintain a
persistent, compounding markdown knowledge base in wiki/, built from
immutable source files in raw/ (Karpathy's LLM Wiki pattern).

You have specialist subagents, reachable via the `task` tool. Check the
description of each available subagent to decide which one fits the
request - broadly:
  - ingesting/processing raw/ files or updating the wiki from new sources
    -> the ingest subagent
  - answering a question from already-ingested content
    -> the query subagent
  - health-checking the wiki (orphans, broken links, contradictions)
    -> the lint subagent

Do not do that work yourself in the main context - always delegate so
wiki/ operations stay isolated and only the subagent's final report (not
its intermediate tool calls) reaches you. If the request is ambiguous
(e.g. mentions both new raw files and a question), ask which they want
first, or run ingest then query in sequence if the user clearly wants
both.

When you call the `task` tool, the `description` you pass IS what the
subagent sees and IS what it logs (e.g. wiki-query writes it verbatim,
truncated to 80 chars, into wiki/latency.log). Always start the
description with the user's original wording, quoted exactly, e.g.:
  User asked: "<verbatim user message>"
  <any extra routing context you need to add>
Do not paraphrase or summarize the user's request into a generic
instruction - that paraphrase would replace their actual question in
the log.

Symmetrically: once a subagent returns its final report, relay it back
to the user VERBATIM. Do not summarize, shorten, reword, or "clean up"
the subagent's report - it already wrote the answer/citations/output in
the exact form meant for the user. Your job ends at choosing which
subagent to call and passing its report through unchanged. The only
exception is if the subagent explicitly asks you a clarifying question
on its behalf - relay that verbatim too.
"""


def build_model():
    """Return either a LangChain model string (for create_deep_agent to
    resolve via init_chat_model) or a constructed model object.

    Auto-detects Azure: if AZURE_OPENAI_DEPLOYMENT is set, builds an
    AzureChatOpenAI directly from the same AZURE_OPENAI_* variable names
    run-codex.sh used to read. LangChain's AzureChatOpenAI actually reads
    AZURE_OPENAI_ENDPOINT / OPENAI_API_VERSION from the environment by
    default, not AZURE_OPENAI_BASE_URL / AZURE_OPENAI_API_VERSION - so
    these are mapped explicitly here rather than relying on env var auto-
    detection, to avoid a silent mismatch.
    """
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    if deployment:
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_deployment=deployment,
            azure_endpoint=os.environ["AZURE_OPENAI_BASE_URL"],
            api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
        )

    return os.environ.get("WIKI_MODEL", "anthropic:claude-sonnet-4-6")


def _check_qmd_server() -> None:
    """Warn (don't hard-fail) if the QMD MCP server isn't reachable.
    wiki-lint doesn't touch QMD at all, so a router session that only
    ever lints should still work with the server down - but ingest and
    query will fail on their QMD tool calls, so surface this early and
    clearly instead of letting it show up as an opaque error mid-run.

    Also fires a one-time WARM-UP search once the server is confirmed
    reachable. QMD's local models (embeddings, and previously hyde
    generation) appear to load into memory on first use, not at daemon
    startup - observed cost: 60s+ on the very first real search against
    a freshly (re)started daemon, then sub-second on every call after.
    Paying that cold-start cost here, with a generous timeout and before
    any real user question arrives, keeps it off the user's first query.
    """
    try:
        from qmd_retrieval import health_check as qmd_health_check, search_hybrid as _qmd_search_hybrid
        import qmd_retrieval as _qmd_module
    except ImportError:
        try:
            from qmd.qmd_retrieval import health_check as qmd_health_check, search_hybrid as _qmd_search_hybrid
            import qmd.qmd_retrieval as _qmd_module
        except ImportError:
            print(
                "WARNING: qmd_retrieval module not importable - QMD search/"
                "reindex tools will fail if called.",
                file=sys.stderr,
            )
            return

    if not qmd_health_check():
        print(
            "WARNING: QMD MCP server not reachable at http://localhost:8181 - "
            "wiki-query and wiki-ingest QMD tools will fail until you run:\n"
            "  qmd mcp --http --daemon",
            file=sys.stderr,
        )
        return

    print("Warming up QMD (loading local models on first use - can take a minute)...", file=sys.stderr)
    original_timeout = getattr(_qmd_module, "MCP_TIMEOUT", 60)
    warmup_timeout = int(os.environ.get("QMD_WARMUP_TIMEOUT", "180"))
    try:
        import time

        t0 = time.time()
        _qmd_module.MCP_TIMEOUT = warmup_timeout  # generous - unknown real cold-start cost
        _qmd_search_hybrid("warmup", n=1, collections=["wiki"], transform=False)
        print(f"QMD warm-up done in {time.time() - t0:.1f}s.", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - warm-up is best-effort, never block startup on it
        print(
            f"WARNING: QMD warm-up search failed or timed out after {warmup_timeout}s ({e}) - "
            f"the first real query may still be slow. Check C:/Users/<you>/.cache/qmd/mcp.log "
            f"for what QMD is doing during that window (e.g. model loading).",
            file=sys.stderr,
        )
    finally:
        _qmd_module.MCP_TIMEOUT = original_timeout


def build_agent():
    """Construct the deep agent, backed by real files under this project
    directory (mirrors the Codex version writing directly to ./raw and
    ./wiki on disk, instead of an ephemeral in-memory filesystem)."""
    _check_qmd_server()

    backend = FilesystemBackend(root_dir=_win_long_path(PROJECT_DIR), virtual_mode=True)

    agent = create_deep_agent(
        model=build_model(),
        backend=backend,
        system_prompt=ROUTER_PROMPT,
        subagents=load_subagents(),
    )
    return agent


def main():
    agent = build_agent()
    query = " ".join(sys.argv[1:]).strip()

    if query:
        result = agent.invoke({"messages": [{"role": "user", "content": query}]})
        print(result["messages"][-1].content)
        return

    print("LLM Wiki (Deep Agents) - interactive mode. Ctrl-D to exit.")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue
        result = agent.invoke({"messages": [{"role": "user", "content": line}]})
        print(result["messages"][-1].content)


if __name__ == "__main__":
    main()