"""
flow_logger.py — lightweight, always-on step tracer so you can WATCH the
ingest/query/lint flow happen tool-call by tool-call, instead of only
seeing the one final JSON line each subagent writes to wiki/latency.log
at the very end.

This is deliberately separate from latency.log:
  - wiki/latency.log  = one structured JSON line per completed run
                        (query, sources, timings) — for later analysis.
  - this module        = live, human-readable trace of every individual
                        tool call as it happens — for watching/debugging
                        the flow in real time.

Usage: wrap any plain function with @log_call() BEFORE applying
LangChain's @tool decorator (i.e. write it as the innermost decorator),
so @tool still sees the original name/signature/docstring via
functools.wraps:

    @tool
    @log_call()
    def my_tool(x: str) -> str:
        ...

Config via environment variables (set before running agent.py):
  WIKI_FLOW_LOG        "1" (default) to print to console, "0" to silence.
  WIKI_FLOW_LOG_FILE   optional path, e.g. ./wiki/flow.log — if set, the
                       trace is ALSO appended to this file in addition
                       to console output.
"""
from __future__ import annotations

import functools
import logging
import os
import sys
import time
from typing import Callable

_ENABLED = os.environ.get("WIKI_FLOW_LOG", "1") != "0"
_LOG_FILE = os.environ.get("WIKI_FLOW_LOG_FILE")

logger = logging.getLogger("wiki_flow")
logger.propagate = False
logger.setLevel(logging.DEBUG if _ENABLED else logging.CRITICAL + 1)

if _ENABLED and not logger.handlers:
    fmt = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if _LOG_FILE:
        os.makedirs(os.path.dirname(_LOG_FILE) or ".", exist_ok=True)
        file_handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)


def _truncate(value, limit: int = 400) -> str:
    """Keep the trace readable — full page content or long CLI output
    would otherwise flood the console on every call."""
    text = repr(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...<+{len(text) - limit} chars truncated>"


def log_call(label: str | None = None) -> Callable:
    """Decorator: logs entry (args/kwargs) and exit (result, duration, or
    error) around any plain function. Use as the innermost decorator on
    tools so LangChain's @tool still introspects the real signature.
    """
    def decorator(func: Callable) -> Callable:
        name = label or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.info(f"\u2192 CALL  {name}  args={_truncate(args)} kwargs={_truncate(kwargs)}")
            t0 = time.time()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - re-raised after logging
                dt = time.time() - t0
                logger.error(f"\u2717 FAIL  {name}  after {dt:.2f}s  error={exc}")
                raise
            dt = time.time() - t0
            logger.info(f"\u2190 DONE  {name}  in {dt:.2f}s  ->  {_truncate(result)}")
            return result

        return wrapper

    return decorator


def log_event(message: str) -> None:
    """Free-form trace line for router/subagent-level milestones that
    aren't a single function call (e.g. 'routing to wiki-query',
    'starting ingest run for 3 files')."""
    logger.info(message)