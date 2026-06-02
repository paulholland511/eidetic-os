#!/usr/bin/env python3
"""
Commit vault changes to git with a descriptive, auto-categorised message.

Stages everything (respecting .gitignore) and writes a commit summarising how
many files were added/modified/deleted, tagged by which top-level folders
changed. Intended to be called from a nightly scheduled task so your vault has
a clean, traceable history.

Configuration is read from the environment — no hardcoded paths.

Environment variables:
    VAULT_PATH   Absolute path to the git-tracked vault (required)

Usage:
    python vault_commit.py              # Commit all changes
    python vault_commit.py --dry-run    # Report what would be committed
    python vault_commit.py --json       # Output stats as JSON
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=VAULT, capture_output=True, text=True, check=check)


def git_status() -> dict[str, list[str]]:
    """Return categorised lists of changed paths."""
    result = run(["git", "status", "--porcelain", "-u"])
    new, modified, deleted = [], [], []
    for line in result.stdout.splitlines():
        if len(line) < 3:
            continue
        xy, path = line[:2], line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        code = xy.strip()
        if "?" in xy:
            new.append(path)
        elif "D" in xy:
            deleted.append(path)
        elif code:
            modified.append(path)
    return {"new": new, "modified": modified, "deleted": deleted}


def classify_paths(paths: list[str]) -> list[str]:
    """Return commit tags based on which directories appear in the changed paths."""
    tags: set[str] = set()
    for p in paths:
        parts = Path(p).parts
        if not parts:
            continue
        top = parts[0]
        if top in ("daily",):
            tags.add("session-log")
        elif top in ("research", "wiki"):
            tags.add("research")
        elif top in ("system", "scripts", ".schemas"):
            tags.add("config")
        elif top in ("projects", "decisions"):
            tags.add("project")
        elif top in ("memory", "memory-archive"):
            tags.add("memory")
    return sorted(tags) if tags else ["content"]


def build_message(stats: dict[str, list[str]]) -> str:
    new = stats["new"]
    modified = stats["modified"]
    deleted = stats["deleted"]
    all_paths = new + modified + deleted

    counts = []
    if new:
        counts.append(f"{len(new)} new")
    if modified:
        counts.append(f"{len(modified)} modified")
    if deleted:
        counts.append(f"{len(deleted)} deleted")

    summary = "Vault update: " + ", ".join(counts)

    tags = classify_paths(all_paths)
    if tags:
        summary += f" [{', '.join(tags)}]"

    sample = all_paths[:8]
    if len(all_paths) > 8:
        sample.append(f"… and {len(all_paths) - 8} more")
    detail = "\n".join(f"  {p}" for p in sample)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{summary}\n\n{detail}\n\nIndexed-at: {ts}"


def stage_all(stats: dict[str, list[str]]) -> None:
    """Stage all changes; git add -A respects .gitignore automatically."""
    run(["git", "add", "-A"])


def main() -> None:
    subprocess.run(["git", "worktree", "prune"], cwd=VAULT, capture_output=True)
    lock_file = os.path.join(str(VAULT), ".git", "index.lock")
    if os.path.exists(lock_file):
        os.remove(lock_file)

    parser = argparse.ArgumentParser(description="Commit vault changes to git")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without committing")
    parser.add_argument("--json", action="store_true", dest="json_out", help="Output stats as JSON")
    args = parser.parse_args()

    stats = git_status()
    total = len(stats["new"]) + len(stats["modified"]) + len(stats["deleted"])

    if total == 0:
        result = {
            "status": "clean", "new": 0, "modified": 0, "deleted": 0,
            "committed": False, "message": None,
        }
        if args.json_out:
            print(json.dumps(result))
        else:
            print("Nothing to commit — vault is clean.")
        sys.exit(0)

    message = build_message(stats)

    if args.dry_run:
        result = {
            "status": "dry-run",
            "new": len(stats["new"]),
            "modified": len(stats["modified"]),
            "deleted": len(stats["deleted"]),
            "committed": False,
            "message": message,
            "files": {
                "new": stats["new"],
                "modified": stats["modified"],
                "deleted": stats["deleted"],
            },
        }
        if args.json_out:
            print(json.dumps(result))
        else:
            print(f"DRY RUN — would commit {total} change(s):\n")
            print(f"  New:      {len(stats['new'])}")
            print(f"  Modified: {len(stats['modified'])}")
            print(f"  Deleted:  {len(stats['deleted'])}")
            print(f"\nCommit message:\n{message}")
        sys.exit(0)

    stage_all(stats)
    proc = run(["git", "commit", "-m", message], check=False)

    if proc.returncode != 0:
        print(f"Git commit failed:\n{proc.stderr}", file=sys.stderr)
        sys.exit(1)

    commit_hash = ""
    for line in proc.stdout.splitlines():
        if line.startswith("["):
            parts = line.split()
            if len(parts) >= 2:
                commit_hash = parts[1].rstrip("]")
            break

    result = {
        "status": "committed",
        "new": len(stats["new"]),
        "modified": len(stats["modified"]),
        "deleted": len(stats["deleted"]),
        "committed": True,
        "commit": commit_hash,
        "message": message,
    }

    if args.json_out:
        print(json.dumps(result))
    else:
        print(f"Committed {total} change(s) [{commit_hash}]")
        print(f"  New:      {len(stats['new'])}")
        print(f"  Modified: {len(stats['modified'])}")
        print(f"  Deleted:  {len(stats['deleted'])}")


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        print("ERROR: VAULT_PATH environment variable is not set. See .env.example.",
              file=sys.stderr)
        sys.exit(1)
    main()
