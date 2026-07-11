"""
Small deterministic tools that stand in for the `sha256sum` / `date` shell
calls the original Codex SKILL.md files told the model to run itself,
plus QMD search/reindex tools for the wiki-query and wiki-ingest
subagents.

Doing hashing/timestamps in real Python instead of trusting the model to
compute (or transcribe) them is the one behavioral change from the Codex
version worth calling out: it removes a class of error where the model
"helpfully" reformats a hash or fabricates a plausible-looking timestamp.

Flow tracing: every tool below is wrapped with @log_call() so you can
watch each call happen live (console, and optionally a file) instead of
only seeing the final wiki/latency.log summary line. See flow_logger.py
for how to configure/silence this.

QMD setup note (one-time, NOT run by the agent):
    from qmd_ingest import ingest_folder
    ingest_folder("./wiki/pages", "wiki", mask="**/*.md")
Run this once when standing up the project (or after changing the mask),
and make sure `qmd mcp --http --daemon` is running before invoking the
agent. The tools below assume the `wiki` collection already exists.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from langchain_core.tools import tool

from flow_logger import log_call
from qmd.qmd_ingest import ensure_wiki_collection
from qmd.qmd_retrieval import search_wiki_filtered, health_check as qmd_health_check


@tool
@log_call()
def read_pdf_text(path: str) -> str:
    """Extract plain text from a PDF under the project root and return it
    as a string.

    Use this instead of the generic read_file tool for any .pdf source in
    raw/. read_file returns PDF content as a raw multimodal file block,
    which some providers' Chat Completions APIs (e.g. Azure OpenAI)
    reject outright with a 400 error. Extracting text here keeps the
    model's context provider-agnostic and avoids sending binary bytes
    through the conversation at all.

    Text-only extraction: this will not capture content that's an image
    within the PDF (scanned pages, embedded diagrams). If a page comes
    back empty, that page may be scanned/image-only and its content is
    not retrievable this way.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return "ERROR: pypdf is not installed. Run: pip install pypdf"

    try:
        reader = PdfReader(path)
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except Exception as e:  # noqa: BLE001 - surface any pypdf parse error to the model
        return f"ERROR: could not open {path} as a PDF: {e}"

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001
            text = f"[ERROR extracting page {i + 1}: {e}]"
        pages.append(f"--- page {i + 1} ---\n{text.strip()}")

    return "\n\n".join(pages) if pages else "ERROR: no pages found in PDF"


@tool
@log_call()
def sha256_file(path: str) -> str:
    """Compute the sha256 hex digest of a file under the project root.

    Use this on every file in raw/ during ingest to detect NEW vs CHANGED
    vs already-processed sources, exactly like `sha256sum raw/<file>` did
    in the Codex version. Path is relative to the backend root_dir
    (e.g. "raw/paper.pdf").
    """
    try:
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return digest
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except OSError as e:
        return f"ERROR: could not read {path}: {e}"


@tool
@log_call()
def utc_now() -> str:
    """Return the current UTC time, once as a Unix epoch float (for latency
    math, replacing `date +%s.%N`) and once as ISO-8601 (for log entries,
    replacing `date -u +%FT%TZ`).

    Returns a string like: "epoch=1737992400.123456 iso=2026-07-09T12:00:00Z"
    """
    now = datetime.now(timezone.utc)
    epoch = now.timestamp()
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"epoch={epoch:.6f} iso={iso}"


@tool
@log_call()
def qmd_reindex_wiki() -> str:
    """Re-scan wiki/pages/ and regenerate embeddings so QMD search
    reflects the pages this ingest run just wrote.

    Call this as the LAST step of an ingest run, after all wiki/*.md
    writes, index.md, and log.md updates are finalized - so QMD indexes
    the final on-disk state, not a half-written one.

    Indexes only content pages under wiki/pages/ (type: concept/entity/
    summary frontmatter pages). index.md and log.md live one level up in
    wiki/ and are structurally outside the scanned folder - never
    returned as search hits. latency.log is excluded automatically (not
    a .md file, also outside pages/).

    Self-healing: if the `wiki` collection was never registered, or got
    removed (e.g. `qmd collection remove wiki`), this creates it fresh
    with the correct fixed folder/mask instead of silently doing nothing
    - so a missing collection fixes itself on the next ingest run rather
    than requiring you to remember to re-run setup by hand. Uses fixed
    constants only (WIKI_FOLDER/WIKI_COLLECTION_NAME/WIKI_MASK in
    qmd_ingest.py) - never anything caller- or model-supplied.
    """
    if not qmd_health_check():
        return "ERROR: QMD MCP server not reachable. Start with: qmd mcp --http --daemon"
    log = ensure_wiki_collection(embed=True)
    return log.get("status", "reindex ran, no status returned")


@tool
@log_call()
def qmd_search_wiki(query: str, top_k: int = 5, min_score: float = 0.3) -> list[dict]:
    """Search the wiki/pages/ QMD index (hybrid lex+vec+hyde) for
    candidate pages relevant to `query`. Returns a ranked list of
    {file, score, ...} - PATHS ONLY, not page content. Open the returned
    wiki/ paths with read_file before citing anything from them; do not
    quote or paraphrase from this tool's output directly.

    Scoped to the `wiki` collection only - never searches raw/. Also
    filters out index.md and log.md defensively even if they were
    somehow indexed, since they are bookkeeping files, not knowledge
    pages, and must never be cited as a source.
    """
    if not qmd_health_check():
        return [{"error": "QMD MCP server not reachable. Start with: qmd mcp --http --daemon"}]
    return search_wiki_filtered(query, n=top_k, min_score=min_score)