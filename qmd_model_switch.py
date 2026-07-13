#!/usr/bin/env python3
"""
qmd_model_switch.py — Change QMD's embedding/reranking/generation
models programmatically instead of typing terminal commands by hand.

This does NOT bypass QMD's actual mechanism (env vars read at daemon
startup) - it automates setting them, restarting the daemon with them
in its environment, and re-embedding. There is no MCP tool or HTTP
endpoint to change models on a running daemon; the daemon must be
restarted with new env vars, because models are loaded once at process
start, not per-request.

Usage:
    python qmd_model_switch.py --embed-model "hf:Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"
    python qmd_model_switch.py --rerank-model "..." --generate-model "..."
    python qmd_model_switch.py --embed-model "..." --index wiki-qwen3   # side-by-side, don't touch existing DB
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

QMD_ENV_VARS = {
    "embed_model": "QMD_EMBED_MODEL",
    "rerank_model": "QMD_RERANK_MODEL",
    "generate_model": "QMD_GENERATE_MODEL",
}

# Persisted here so the NEXT time you start the daemon (e.g. via your
# normal start-up flow, not just this script) it still picks these up.
# This is a plain env file the daemon's shell should `source`/load -
# separate from qmd_retrieval.py's own .env, which is your Python
# client's config, not the daemon's.
QMD_DAEMON_ENV_FILE = Path.home() / ".config" / "qmd" / "daemon.env"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, check=False, capture_output=True, text=True, **kwargs)


def stop_daemon() -> None:
    result = run(["qmd", "mcp", "stop"])
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and "not running" not in (result.stderr or "").lower():
        print(f"WARNING: qmd mcp stop returned {result.returncode}: {result.stderr}", file=sys.stderr)


def start_daemon(env: dict) -> None:
    """Start the daemon with `env` merged into its process environment.
    This is the actual mechanism - the daemon reads QMD_EMBED_MODEL etc.
    ONLY at startup, so env vars set after this point have no effect
    until the next restart."""
    full_env = {**os.environ, **env}
    result = run(["qmd", "mcp", "--http", "--daemon"], env=full_env)
    if result.returncode != 0:
        print(f"ERROR starting daemon: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout.strip())


def persist_to_daemon_env_file(env: dict) -> None:
    """Write these vars to a file the daemon's own startup routine
    should load on every future launch (e.g. your systemd unit /
    launchd plist / start script), so this isn't a one-off that's lost
    on next reboot."""
    QMD_DAEMON_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if QMD_DAEMON_ENV_FILE.exists():
        existing = QMD_DAEMON_ENV_FILE.read_text(encoding="utf-8").splitlines()
        keys_being_set = set(env.keys())
        lines = [l for l in existing if not any(l.startswith(f"{k}=") for k in keys_being_set)]
    lines += [f"{k}={v}" for k, v in env.items()]
    QMD_DAEMON_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Persisted to {QMD_DAEMON_ENV_FILE} - point your daemon start-up script "
          f"at this file (e.g. `source {QMD_DAEMON_ENV_FILE}` before `qmd mcp --http --daemon`) "
          f"so future restarts pick it up automatically.")


def reembed(index: str | None, force: bool) -> None:
    cmd = ["qmd"]
    if index:
        cmd += ["--index", index]
    cmd += ["embed"]
    if force:
        cmd.append("-f")
    result = run(cmd)
    print(result.stdout.strip())
    if result.returncode != 0:
        print(f"ERROR during embed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def verify(index: str | None) -> None:
    cmd = ["qmd"]
    if index:
        cmd += ["--index", index]
    cmd += ["status"]
    result = run(cmd)
    print(result.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--embed-model", help="HF GGUF URI, e.g. hf:org/repo/file.gguf")
    p.add_argument("--rerank-model")
    p.add_argument("--generate-model")
    p.add_argument("--index", help="Use a separate named DB instead of the default "
                                    "(recommended when comparing models side-by-side "
                                    "rather than overwriting existing vectors)")
    p.add_argument("--no-reembed", action="store_true",
                    help="Skip auto re-embed (you'll need to run `qmd embed -f` yourself "
                         "before the new embedding model actually takes effect on search)")
    p.add_argument("--persist", action="store_true",
                    help="Also write these vars to a daemon env file for future restarts")
    args = p.parse_args()

    env = {}
    if args.embed_model:
        env[QMD_ENV_VARS["embed_model"]] = args.embed_model
    if args.rerank_model:
        env[QMD_ENV_VARS["rerank_model"]] = args.rerank_model
    if args.generate_model:
        env[QMD_ENV_VARS["generate_model"]] = args.generate_model

    if not env:
        p.error("Provide at least one of --embed-model / --rerank-model / --generate-model")

    changing_embed_model = "QMD_EMBED_MODEL" in env

    print("Stopping existing daemon (if running)...")
    stop_daemon()
    time.sleep(1)  # let the PID file/port release fully before relaunching

    print("Starting daemon with new model env vars...")
    start_daemon(env)

    if args.persist:
        persist_to_daemon_env_file(env)

    if changing_embed_model and not args.no_reembed:
        print("Embedding model changed - vectors are not cross-compatible between "
              "models, forcing full re-embed (`qmd embed -f`)...")
        reembed(args.index, force=True)
    elif changing_embed_model:
        print("WARNING: --no-reembed set but embedding model changed - search will "
              "error on dimension mismatch until you run `qmd embed -f` yourself.",
              file=sys.stderr)

    print("\nVerifying active config:")
    verify(args.index)


if __name__ == "__main__":
    main()