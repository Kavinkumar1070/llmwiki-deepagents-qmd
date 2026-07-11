#!/usr/bin/env python3
"""
qmd_retrieval.py — QMD query/retrieval functions only.

Talks to a running QMD MCP HTTP server for hybrid search over the `wiki`
collection. Returns paths + scores only — content is fetched separately
by the calling subagent via its existing read_file tool, not through
QMD, so the citation chain in wiki-query.md stays a clean
path -> read_file -> cite hop.

Flow tracing: the transport layer (_rpc) and the two public search
entry points are wrapped with @log_call() so you can watch each MCP
round-trip (method, args, response) as it happens. See flow_logger.py
to configure/silence this.

Prereq: start the server once with `qmd mcp --http --daemon`
"""

import json
import os
import requests

from flow_logger import log_call, logger
from qmd.query_transform import transform_query

MCP_URL = "http://localhost:8181/mcp"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}

# Confirmed via QMD's own mcp.log: two consecutive `vec`-inclusive
# queries on the SAME already-running daemon took 170.9s and then
# 146.4s. If this were a one-time cold-start model load, the second
# call would have been fast - it wasn't. The ~150-170s cost is PER
# CALL, most likely because the embedding model isn't staying loaded
# in memory between requests. 60s was never long enough for this
# server's real behavior - default raised to actually cover it.
# Increase further via QMD_MCP_TIMEOUT if you still see timeouts.
MCP_TIMEOUT = int(os.environ.get("QMD_MCP_TIMEOUT", "200"))

# hyde is OFF by default - see search_hybrid's docstring. Kept separate
# from the vec slowness below; hyde adds its own server-side generation
# on top and has caused outright hangs beyond even the ~170s vec cost.
ENABLE_HYDE = os.environ.get("QMD_ENABLE_HYDE", "1") == "1"
HYDE_ATTEMPT_TIMEOUT = int(os.environ.get("QMD_HYDE_TIMEOUT", "60"))

# vec is ON by default but is the confirmed source of the ~150-170s
# per-call cost. Set QMD_ENABLE_VEC=0 for a fast (near-instant),
# lex-only search while you investigate/fix the underlying embedding
# model config (check `qmd status` for which model is loaded).
ENABLE_VEC = os.environ.get("QMD_ENABLE_VEC", "1") != "0"

_session = requests.Session()
_session_id = None
_initialized = False

# Bookkeeping files that must never surface as search results, even if
# they slipped into the index because they were somehow indexed. This is
# a SAFETY NET, not the primary control — the primary control is that
# wiki/pages/ (the folder QMD is pointed at) structurally excludes
# index.md and log.md, which live one level up in wiki/. Keep both: if
# anything ever changes the ingest folder, this still stops them being
# cited.
BOOKKEEPING_FILES = {"index.md", "log.md"}


# ----------------------------------------------------------------------
# Transport layer (session handling) — internal
# ----------------------------------------------------------------------

def _parse(resp):
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise RuntimeError(f"No data in SSE response: {resp.text}")
    return resp.json()


@log_call("mcp_rpc")
def _rpc(method: str, params: dict, id_: int = 1, notify: bool = False, timeout: int | None = None):
    global _session_id
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        payload["id"] = id_

    headers = dict(HEADERS)
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id

    resp = _session.post(MCP_URL, json=payload, headers=headers, timeout=timeout or MCP_TIMEOUT)

    if "Mcp-Session-Id" in resp.headers:
        _session_id = resp.headers["Mcp-Session-Id"]

    resp.raise_for_status()
    if notify:
        return None
    return _parse(resp)


def _initialize():
    global _initialized
    if _initialized:
        return
    _rpc("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "python-client", "version": "1.0"},
    })
    _rpc("notifications/initialized", {}, notify=True)
    _initialized = True


def _call_tool(name: str, arguments: dict, timeout: int | None = None) -> dict:
    _initialize()
    return _rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)


def _extract_results(mcp_response: dict) -> list[dict]:
    return (
        mcp_response.get("result", {})
        .get("structuredContent", {})
        .get("results", [])
    )


# ----------------------------------------------------------------------
# Public search — hybrid only (closest to CLI `qmd query` behavior)
# ----------------------------------------------------------------------

@log_call("search_hybrid")
def search_hybrid(text: str, n: int = 5, collections: list[str] | None = None,
                   min_score: float = 0.0, transform: bool = True) -> list[dict]:
    """lex + vec by default. hyde is opt-in - see ENABLE_HYDE above.

    transform=True (default): lex gets its own rewritten query string
    via transform_query() - a keyword-dense phrase, since that's the
    only sub-type with a clear case for rewriting. vec always gets the
    raw, unmodified `text`.

    If ENABLE_HYDE=1: hyde is added to the search using the raw `text`
    (QMD's `type: "hyde"` does its own generation server-side and
    expects a question, not a pre-rewritten one). The combined call
    uses a short HYDE_ATTEMPT_TIMEOUT budget (20s default) and falls
    back to a lex+vec-only retry on timeout - but note this fallback
    has ALSO been observed to time out in production, most likely
    because the abandoned hyde generation keeps running inside QMD's
    daemon and blocks the next request rather than being cancelled.
    That's a server-side issue a client-side retry cannot fully fix -
    leave ENABLE_HYDE off unless you've confirmed the daemon handles
    concurrent/cancelled requests properly.

    transform=False: skip the lex rewrite too, send `text` unchanged.
    """
    lex_query = transform_query(text) if transform else text

    searches = [
        {"type": "lex", "query": lex_query},
        {"type": "vec", "query": text},
    ]
    if ENABLE_HYDE:
        searches.append({"type": "hyde", "query": text})

    args = {"searches": searches, "limit": n, "minScore": min_score}
    if collections:
        args["collections"] = collections

    if not ENABLE_HYDE:
        return _extract_results(_call_tool("query", args))

    try:
        return _extract_results(_call_tool("query", args, timeout=HYDE_ATTEMPT_TIMEOUT))
    except requests.exceptions.ReadTimeout:
        logger.warning(
            f"search_hybrid: full search (incl. hyde) exceeded {HYDE_ATTEMPT_TIMEOUT}s "
            f"- retrying with hyde dropped (lex+vec only). NOTE: if this retry ALSO "
            f"times out, the QMD daemon is likely wedged by the abandoned hyde call - "
            f"restart it (`qmd mcp --http --daemon`) rather than waiting longer."
        )
        args["searches"] = [s for s in searches if s["type"] != "hyde"]
        return _extract_results(_call_tool("query", args))


def mcp_status() -> dict:
    """Index health via the MCP status tool."""
    return _call_tool("status", {})


def health_check() -> bool:
    """Check whether the QMD MCP HTTP server is reachable."""
    try:
        return requests.get("http://localhost:8181/health", timeout=5).status_code == 200
    except requests.RequestException:
        return False


def _is_bookkeeping(file_path: str) -> bool:
    return file_path.rsplit("/", 1)[-1] in BOOKKEEPING_FILES


@log_call("search_wiki_filtered")
def search_wiki_filtered(text: str, n: int = 5, min_score: float = 0.3, transform: bool = True) -> list[dict]:
    """
    Hybrid search scoped to the `wiki` collection only (never `raw`),
    with bookkeeping files (index.md, log.md) filtered out defensively
    even if they ended up indexed. Over-fetches slightly to compensate
    for anything the filter drops, then trims back to n.

    transform: forwarded to search_hybrid - True (default) rewrites the
    query per sub-type (keyword/vector/hyde) via query_transform.py
    before searching; False sends the raw text unchanged to all three,
    as it did previously.
    """
    raw_results = search_hybrid(text, n=n + 2, collections=["wiki"], min_score=min_score, transform=transform)
    filtered = [r for r in raw_results if not _is_bookkeeping(r.get("file", ""))]
    return filtered[:n]