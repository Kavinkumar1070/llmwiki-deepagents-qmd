#!/usr/bin/env python3
"""
qmd_ingest.py — QMD ingestion functions only.

Handles getting data INTO the QMD index: registering folders/files,
indexing them, and generating embeddings. Uses the CLI under the hood
since QMD's MCP server does not expose ingest tools (only query/get/status).

Usage:
    from qmd_ingest import ingest_folder, ingest_existing_collection, reindex, embed_all, get_status

    # one-time setup (not per-turn / not called by the agent):
    ingest_folder("./wiki/pages", "wiki", mask="**/*.md")

    # per wiki-ingest run, after all wiki/*.md writes are finalized:
    ingest_existing_collection()
"""

import shutil
import subprocess
from pathlib import Path

from flow_logger import log_call

# Bookkeeping files that live in wiki/ (one level ABOVE wiki/pages/) and
# are never knowledge pages. They are never indexed because they sit
# outside WIKI_FOLDER entirely — this set exists only as a defensive
# check inside ingest_file(), in case someone passes one of these paths
# directly. wiki/latency.log is excluded for free (not a .md file and
# also outside pages/).
BOOKKEEPING_FILES = {"index.md", "log.md"}

# Fixed config for THE wiki collection specifically. These are constants,
# not caller-supplied arguments — that's what makes ensure_wiki_collection()
# below safe to call unconditionally from an agent tool: the LLM never
# chooses the folder/name/mask, so there's no risk of it registering an
# arbitrary or misconfigured collection.
#
# wiki/pages/ holds only content pages (type: concept/entity/summary).
# wiki/index.md and wiki/log.md live one level up, OUTSIDE this folder,
# so they are structurally out of scope for the QMD collection — no
# --exclude/ignore_patterns mechanism needed. QMD's own `collection
# exclude <name>` subcommand turned out to toggle an entire collection
# off default queries rather than excluding a file pattern, so this
# folder-boundary approach is used instead: simpler and doesn't depend
# on an undocumented/ambiguous CLI feature.
WIKI_FOLDER = "./wiki/pages"
WIKI_COLLECTION_NAME = "wiki"
WIKI_MASK = "**/*.md"
WIKI_EXCLUDES: list[str] = []  # not needed — folder boundary handles it


@log_call("qmd_cli")
def _run_cli(args: list[str]) -> str:
    qmd = shutil.which("qmd")
    if qmd is None:
        raise RuntimeError("qmd not found on PATH")

    # NOTE: previously this called subprocess.run([qmd, *args], shell=True),
    # which is broken on POSIX — shell=True with a list argument only runs
    # arg[0] through the shell and silently mishandles the rest. shutil.which
    # already resolves .exe/.cmd on Windows, so shell=False is correct and
    # portable; no shell=True needed on either platform.
    result = subprocess.run(
        [qmd, *args],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"qmd CLI error:\n{result.stderr}\n{result.stdout}")

    return result.stdout


def ingest_folder(folder_path: str, collection_name: str, mask: str = "**/*.md",
                   embed: bool = True, exclude: list[str] | None = None) -> dict:
    """
    One-time (or rare) setup call: register folder_path as a QMD
    collection, index it, and embed it. NOT meant to be called by the
    agent per-turn — call this once when standing up the project (or
    again if you deliberately want to re-register/change the mask).

    exclude: filenames/patterns to keep out of the index even though they
    match `mask`. For the wiki collection this is normally empty — the
    wiki/pages/ folder boundary already keeps index.md/log.md out, since
    they live in wiki/ (one level up), not wiki/pages/. This parameter is
    kept for other collections that don't have that folder separation.
    NOTE: there is no `--exclude` flag on `collection add` — QMD's real
    syntax is the separate subcommand `qmd collection exclude
    <collection-name> <pattern>`, run AFTER the collection is created.
    Confirmed via `qmd collection add --help` showing:
      qmd collection exclude archive
    as a top-level example, not an add-time flag.
    """
    log = {}

    add_args = [
        "collection", "add",
        folder_path,
        "--name", collection_name,
        "--mask", mask,
    ]

    try:
        log["add"] = _run_cli(add_args)
    except RuntimeError as e:
        if "already exists" in str(e):
            log["add"] = "Collection already exists. Skipping add."
        else:
            raise

    exclude_logs = []
    for pattern in (exclude or []):
        try:
            exclude_logs.append(_run_cli(["collection", "exclude", collection_name, pattern]))
        except RuntimeError as e:
            # Tolerate "already excluded" so this function stays safe to
            # call repeatedly (idempotent) — only re-raise genuinely
            # unexpected errors.
            if "already" in str(e).lower():
                exclude_logs.append(f"{pattern}: already excluded, skipped")
            else:
                raise
    if exclude_logs:
        log["exclude"] = "\n".join(exclude_logs)

    log["update"] = _run_cli(["update"])

    if embed:
        log["embed"] = _run_cli(["embed"])

    log["status"] = _run_cli(["status"])
    return log


def ingest_existing_collection(embed: bool = True) -> dict:
    """
    Re-scan + re-embed an already-registered collection. This is the
    function the wiki-ingest agent tool should call — it assumes
    `ingest_folder(...)` was already run once during project setup, so
    the folder/mask are already baked into the collection's registration
    and don't need to be repeated here.
    """
    log = {}
    log["update"] = _run_cli(["update"])
    if embed:
        log["embed"] = _run_cli(["embed"])
    log["status"] = _run_cli(["status"])
    return log


def ingest_file(file_path: str, collection_name: str, embed: bool = True) -> dict:
    """
    Ingest a single .md file. QMD only indexes folders, so this wraps the
    file in its own dedicated subfolder first, then indexes that.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Not a file: {file_path}")
    if p.name in BOOKKEEPING_FILES:
        raise ValueError(f"{p.name} is a bookkeeping file and must not be indexed")

    target_dir = p.parent / f"_qmd_single_{p.stem}"
    target_dir.mkdir(exist_ok=True)
    dest = target_dir / p.name
    dest.write_bytes(p.read_bytes())

    return ingest_folder(str(target_dir), collection_name, embed=embed)


def reindex(collection_name: str | None = None) -> str:
    """Re-scan and re-index existing collections without adding new ones."""
    return _run_cli(["update"])


def embed_all(force: bool = False) -> str:
    """Generate embeddings for documents that don't have them yet."""
    args = ["embed"]
    if force:
        args.append("-f")
    return _run_cli(args)


def add_context(virtual_path: str, description: str) -> str:
    """Attach a description to a collection/path to improve search relevance."""
    return _run_cli(["context", "add", virtual_path, description])


def list_collections() -> str:
    """List all registered collections."""
    return _run_cli(["collection", "list"])


def remove_collection(collection_name: str) -> str:
    """Remove a collection from the registry (does not delete source files)."""
    return _run_cli(["collection", "remove", collection_name])


def get_status() -> str:
    """Raw index status: document count, vector count, models, collections."""
    return _run_cli(["status"])


def cleanup() -> str:
    """Clean up orphaned cache/index data."""
    return _run_cli(["cleanup"])


def ensure_wiki_collection(embed: bool = True) -> dict:
    """
    Idempotent setup+refresh for THE wiki collection, using the fixed
    WIKI_* constants above (never caller-supplied). Safe to call every
    time, from anywhere:
      - collection doesn't exist yet -> creates it pointed at
        wiki/pages/ (not wiki/), updates, embeds (this is what fixes the
        "Files: 0" problem you hit when qmd_reindex_wiki ran before the
        collection existed).
      - collection already exists -> ingest_folder's own "already
        exists" handling skips the add step, then updates + embeds as
        normal.
    This is the function the qmd_reindex_wiki agent tool should call
    instead of ingest_existing_collection(), so a missing/removed
    collection self-heals on the next ingest run instead of silently
    no-op'ing.

    Points at wiki/pages/ specifically (not wiki/), so index.md and
    log.md — which live one level up in wiki/ — are structurally out of
    scope for the scan. No --exclude patterns needed; the folder
    boundary is the whole mechanism.
    """
    return ingest_folder(
        WIKI_FOLDER,
        WIKI_COLLECTION_NAME,
        mask=WIKI_MASK,
        embed=embed,
        exclude=WIKI_EXCLUDES,
    )


def exclude_from_collection(collection_name: str, pattern: str) -> str:
    """Exclude a file/pattern from an already-registered collection.
    This is the correct, standalone equivalent of the qmd CLI's
    `qmd collection exclude <name> <pattern>` — call this directly if a
    collection already exists and you just need to add exclusions
    without re-running the full add/update/embed cycle. Not needed for
    the wiki collection itself (folder boundary handles that case), but
    kept here for any other collection that lacks that separation.
    """
    return _run_cli(["collection", "exclude", collection_name, pattern])


if __name__ == "__main__":
    # One-time setup example — run this manually once, not via the agent.
    print(ingest_folder(
        WIKI_FOLDER,
        WIKI_COLLECTION_NAME,
        mask=WIKI_MASK,
    ))