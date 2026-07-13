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

import ast
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
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
from langchain_core.callbacks import BaseCallbackHandler

from tools import (
    read_pdf_text,
    sha256_file,
    qmd_reindex_wiki,
    qmd_search_wiki,
)

PROJECT_DIR = Path(__file__).resolve().parent
SUBAGENTS_DIR = PROJECT_DIR / "subagents"
AGENTS_MD = PROJECT_DIR / "AGENTS.md"
LATENCY_LOG = PROJECT_DIR / "wiki" / "latency.log"

load_dotenv(PROJECT_DIR / ".env")

# Each subagent only gets the tools its own subagents/*.md actually calls:
#   wiki-ingest hashes raw/ files, reads PDFs, and reindexes QMD after
#     writing -> needs all three
#   wiki-query searches QMD first to find candidate pages -> needs
#     qmd_search_wiki only
#   wiki-lint is read-only over wiki/ content -> needs no tools of its own
# Timing used to be a fourth reason subagents needed a tool (utc_now) -
# that's gone now. See LatencyLogger below: wall-clock timing is measured
# in code, around the `task` tool call, so no subagent has to self-report
# a timestamp.
TOOLS_BY_SUBAGENT = {
    "wiki-ingest": [sha256_file, read_pdf_text, qmd_reindex_wiki],
    "wiki-query": [qmd_search_wiki],
    "wiki-lint": [],
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


class LatencyLogger(BaseCallbackHandler):
    """Code-side, model-independent latency capture for subagent (`task`)
    invocations.

    This replaces the old scheme where each skill called a `utc_now` tool
    at several checkpoints, hand-copied the epoch values, and hand-wrote
    the subtraction into a JSON log line. That put both the clock *and*
    the arithmetic in the model's hands - it could skip a checkpoint,
    reorder one, reuse a stale value, or just write bad JSON.

    Here, timing is measured with Python's own monotonic clock around the
    `task` tool call the router uses to invoke each subagent, and the log
    line is written by this code, not by the LLM. The subagent's final
    report text comes straight from the tool's return value
    (`on_tool_end`'s `output`), so wiki-query no longer has to retype its
    own answer into the log - we just capture what it actually returned.

    Tool-call attribution uses a start-order stack, not `parent_run_id`
    equality: a subagent's own tool calls (sha256_file, read_pdf_text,
    qmd_search_wiki, qmd_reindex_wiki, ...) happen several levels down
    inside the subgraph the `task` tool invokes, so their `parent_run_id`
    doesn't point directly at the `task` run - it points at whatever
    LangGraph node called them. Instead, whenever a `task` call is open,
    every tool call that starts before it closes is attributed to it.
    This is correct for the sequential, single-subagent-at-a-time flow
    this router uses; if the router ever fires multiple `task` calls
    concurrently, calls made during the overlap would attribute to the
    most recently opened task rather than being split precisely between
    them.
    """

    TASK_TOOL_NAME = "task"

    def __init__(self, log_path: Path):
        self.log_path = log_path
        # run_id (str) -> span dict
        self._spans: dict[str, dict] = {}
        # run_ids of currently-open `task` calls, in start order (a stack)
        self._task_stack: list[str] = []

    # -- LangChain callback hooks -----------------------------------------

    def on_tool_start(self, serialized, input_str, *, run_id, parent_run_id=None, **kwargs):
        key = str(run_id)
        tool_name = (serialized or {}).get("name", "unknown")
        span = {
            "tool": tool_name,
            "start": time.perf_counter(),
            "parent_run_id": str(parent_run_id) if parent_run_id else None,
            "input": input_str,
            "error": None,
        }
        if tool_name != self.TASK_TOOL_NAME and self._task_stack:
            span["owning_task"] = self._task_stack[-1]
        self._spans[key] = span

        if tool_name == self.TASK_TOOL_NAME:
            self._task_stack.append(key)

    def on_tool_error(self, error, *, run_id, **kwargs):
        span = self._spans.get(str(run_id))
        if span is not None:
            span["error"] = str(error)
        self._finish_tool(run_id, output=None)

    def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish_tool(run_id, output=output)

    # -- internals ----------------------------------------------------------

    def _finish_tool(self, run_id, output):
        key = str(run_id)
        span = self._spans.get(key)
        if span is None or "end" in span:
            return
        span["end"] = time.perf_counter()
        span["duration_s"] = round(span["end"] - span["start"], 6)
        span["output"] = output

        if span["tool"] == self.TASK_TOOL_NAME:
            if self._task_stack and self._task_stack[-1] == key:
                self._task_stack.pop()
            elif key in self._task_stack:
                self._task_stack.remove(key)  # out-of-order close, be defensive
            self._write_log_line(key, span)

    def _owned_spans(self, run_id: str) -> list[dict]:
        """Tool calls attributed to this task while it was open, in call
        order (dict insertion order == start order)."""
        return [
            {"tool": s["tool"], "duration_s": s.get("duration_s"), "error": s["error"]}
            for rid, s in self._spans.items()
            if rid != run_id and s.get("owning_task") == run_id
        ]

    def _write_log_line(self, run_id: str, span: dict) -> None:
        subagent_type, description = self._parse_task_input(span["input"])
        report_text = self._stringify_output(span["output"])

        entry = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "op": subagent_type or "unknown",
            "query": description,
            "total_s": span["duration_s"],
            "success": span["error"] is None,
            "tool_calls": self._owned_spans(run_id),
        }
        if report_text:
            entry["report"] = report_text
            sources = self._extract_sources_line(report_text)
            if sources:
                entry["sources"] = sources
        if span["error"]:
            entry["error"] = span["error"]

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _parse_task_input(raw):
        """The `task` tool's input carries which subagent was called and
        the description/prompt passed to it. Observed in practice: this
        arrives as a plain Python dict's str()/repr() - single-quoted,
        NOT valid JSON (e.g. "{'subagent_type': 'wiki-ingest', ...}").
        Try JSON first in case a future/different LangChain version hands
        us real JSON, then fall back to ast.literal_eval for the Python-
        repr case, which is what's actually been observed."""
        data = raw
        if isinstance(raw, str):
            parsed = None
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                try:
                    parsed = ast.literal_eval(raw)
                except (ValueError, SyntaxError):
                    parsed = None
            data = parsed if parsed is not None else raw
        if isinstance(data, dict):
            return data.get("subagent_type"), data.get("description")
        return None, str(raw) if raw is not None else None

    @staticmethod
    def _stringify_output(output) -> str | None:
        if output is None:
            return None
        if isinstance(output, str):
            return output

        # Observed in practice: deepagents' `task` tool returns a
        # LangGraph `Command(update={'files': {...}, 'messages': [...]})`
        # rather than a plain string. The subagent's actual report text
        # is the content of the last message in update['messages'].
        update = getattr(output, "update", None)
        if isinstance(update, dict):
            messages = update.get("messages")
            if isinstance(messages, list) and messages:
                content = getattr(messages[-1], "content", None)
                if isinstance(content, str):
                    return content

        # ToolMessage or similar returned directly - commonly exposes .content
        content = getattr(output, "content", None)
        if isinstance(content, str):
            return content

        return str(output)

    @staticmethod
    def _extract_sources_line(report_text: str) -> list[str] | None:
        """wiki-query's report ends with a literal `Sources: a, b, c` line
        (see subagents/wiki-query.md) - pull it out for structured
        logging without asking the model to also emit a separate list."""
        match = re.search(r"^Sources:\s*(.+)$", report_text, re.MULTILINE)
        if not match:
            return None
        return [p.strip() for p in match.group(1).split(",") if p.strip()]


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

You'll see a system message giving today's date in UTC. When you
delegate to the ingest subagent, always include that date in the task
description (e.g. "Today's date: 2026-07-13 (UTC)") - it has no other
way to know the real current date and needs it for the wiki/log.md
changelog entry it writes. Other subagents don't need it.

When you call the `task` tool, the `description` you pass IS what the
subagent sees, and it is also what the harness records as `query` in
wiki/latency.log (that logging happens automatically in code around this
tool call - you don't write to latency.log yourself). Always start the
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
    ./wiki on disk, instead of an ephemeral in-memory filesystem).

    Returns (agent, invoke_config): pass invoke_config into every
    `agent.invoke(...)` call (as the `config=` kwarg) so the LatencyLogger
    callback is attached to the run. It's returned rather than bound with
    `.with_config()` so this works the same regardless of whether the
    installed deepagents/langgraph version supports callback binding on
    the compiled graph itself.
    """
    _check_qmd_server()

    backend = FilesystemBackend(root_dir=_win_long_path(PROJECT_DIR), virtual_mode=True)

    agent = create_deep_agent(
        model=build_model(),
        backend=backend,
        system_prompt=ROUTER_PROMPT,
        subagents=load_subagents(),
    )

    latency_logger = LatencyLogger(LATENCY_LOG)
    invoke_config = {"callbacks": [latency_logger]}
    return agent, invoke_config


def _log_invoke_total(message: str, total_s: float) -> None:
    """True end-to-end wall time for one agent.invoke() call - from the
    user's message going in to the final assistant reply coming out.

    This is deliberately a *separate* log entry from the per-subagent
    ("op": "wiki-ingest" / "wiki-query" / "wiki-lint") lines LatencyLogger
    writes. Those only cover the `task` tool's own span - they exclude
    the router's own LLM turn to decide which subagent to call and draft
    its description (before the task call starts) and its turn to relay
    the subagent's report back to you (after the task call ends). Compare
    this "invoke" total_s against the nearest "wiki-*" total_s logged in
    the same window to see how much time sat outside the subagent - i.e.
    router overhead, or anything else outside the graph's tool calls.
    """
    entry = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "op": "invoke",
        "query": message,
        "total_s": round(total_s, 6),
    }
    LATENCY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LATENCY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _invoke_and_print(agent, message: str, invoke_config: dict) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    messages = [
        {
            "role": "system",
            "content": f"Today's date: {today} (UTC). This is ground truth from the "
            "host system clock, not a guess - use it for anything date-related "
            "(e.g. wiki/log.md entries), never your own training-cutoff date.",
        },
        {"role": "user", "content": message},
    ]

    t0 = time.perf_counter()
    result = agent.invoke({"messages": messages}, config=invoke_config)
    t1 = time.perf_counter()
    _log_invoke_total(message, t1 - t0)
    print(result["messages"][-1].content)


def main():
    agent, invoke_config = build_agent()
    query = " ".join(sys.argv[1:]).strip()

    if query:
        _invoke_and_print(agent, query, invoke_config)
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
        _invoke_and_print(agent, line, invoke_config)


if __name__ == "__main__":
    main()