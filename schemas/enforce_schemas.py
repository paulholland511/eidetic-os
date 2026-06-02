#!/usr/bin/env python3
"""
Frontmatter schema enforcement for a markdown vault.

Scans markdown files, validates YAML frontmatter against per-folder schemas,
and fills in missing required fields with sensible defaults (inferring date and
title from the filename where possible). This keeps a vault consistent enough
for reliable RAG indexing and dashboard rendering.

Configuration is read from the environment — no hardcoded paths. Edit the
SCHEMAS dict to match your own folder layout.

Environment variables:
    VAULT_PATH   Absolute path to the vault (required)

Usage:
    python3 enforce_schemas.py [--dry-run] [--folder FOLDER] [--verbose]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


# ── Configuration ─────────────────────────────────────────────────────────────

VAULT_DIR = Path(os.path.expanduser(os.environ.get("VAULT_PATH", "."))).resolve()

SKIP_DIRS: set[str] = {
    ".obsidian", ".git", ".rag", ".scripts", ".schemas", ".claude", ".raw",
    "skills", "templates",
}

# Per-folder schemas. Adjust these to match your vault's top-level folders.
SCHEMAS: dict[str, dict[str, Any]] = {
    "research": {
        "required": ["tags", "type", "date"],
        "defaults": {"type": "note", "tags": [], "status": "draft"},
    },
    "research-archive": {
        "required": ["tags", "type", "date"],
        "defaults": {"type": "note", "tags": [], "status": "archived"},
    },
    "code-solutions": {
        "required": ["title", "date", "type", "tags", "author", "commit",
                     "complexity", "files_changed", "indexed"],
        "defaults": {"author": "Atlas", "indexed": True, "tags": [],
                     "complexity": "moderate", "commit": "unknown", "files_changed": 0},
    },
    "memory": {
        "required": ["tags", "date"],
        "defaults": {"type": "session-log", "tags": [], "source": "workspace"},
    },
    "memory-archive": {
        "required": ["tags", "date"],
        "defaults": {"type": "session-log", "tags": [], "source": "workspace"},
    },
    "learning": {
        "required": ["tags", "date", "type"],
        "defaults": {"type": "concept-extraction", "tags": []},
    },
    "system": {
        "required": ["tags", "type", "date"],
        "defaults": {"type": "note", "tags": []},
    },
    "projects": {
        "required": ["tags", "type", "date", "title", "status"],
        "defaults": {"type": "note", "tags": [], "status": "active"},
    },
    "decisions": {
        "required": ["tags", "type", "date", "title"],
        "defaults": {"type": "decision", "tags": [], "status": "draft"},
    },
    "guides": {
        "required": ["tags", "type", "date", "title"],
        "defaults": {"type": "guide", "tags": []},
    },
    "wiki": {
        "required": ["type", "title", "created", "updated", "tags", "status"],
        "defaults": {"type": "reference", "tags": [], "status": "seed"},
    },
    "daily": {
        "required": ["date", "tags", "type"],
        "defaults": {"type": "synthesis", "tags": []},
    },
    "inbox": {
        "required": ["tags", "type", "date"],
        "defaults": {"type": "note", "tags": []},
    },
    "archive": {
        "required": ["tags", "type", "date"],
        "defaults": {"type": "note", "tags": []},
    },
}


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class ProcessResult:
    file_path: Path
    status: str  # "ok", "updated", "error", "skipped"
    fields_added: list[str]
    error_message: str | None = None


@dataclass
class Stats:
    files_scanned: int = 0
    files_complete: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    files_error: int = 0
    fields_added: dict[str, int] | None = None

    def __post_init__(self) -> None:
        if self.fields_added is None:
            self.fields_added = defaultdict(int)


# ── Frontmatter parsing ───────────────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
DATE_IN_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None, "", text

    fm_raw = match.group(1)
    body = text[match.end():]

    try:
        fm_dict = yaml.safe_load(fm_raw)
        if fm_dict is None:
            fm_dict = {}
        if not isinstance(fm_dict, dict):
            return None, fm_raw, body
        return fm_dict, fm_raw, body
    except yaml.YAMLError:
        return None, fm_raw, body


def serialize_frontmatter(fm: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in fm.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif value is None:
            lines.append(f"{key}:")
        else:
            str_val = str(value)
            if any(c in str_val for c in [":", "#", "'", '"', "\n"]):
                lines.append(f'{key}: "{str_val}"')
            else:
                lines.append(f"{key}: {str_val}")
    return "\n".join(lines)


# ── Field inference ───────────────────────────────────────────────────────────


def infer_date(file_path: Path) -> str:
    filename = file_path.stem
    match = DATE_IN_FILENAME_RE.match(filename)
    if match:
        return match.group(1)
    mtime = file_path.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def infer_title(file_path: Path) -> str:
    filename = file_path.stem
    match = DATE_IN_FILENAME_RE.match(filename)
    if match:
        filename = filename[len(match.group(1)):].lstrip("-_")
    return filename.replace("-", " ").replace("_", " ").title()


def infer_field_value(field: str, file_path: Path, schema_defaults: dict[str, Any]) -> Any:
    if field in ("date", "created", "updated"):
        return infer_date(file_path)
    elif field == "title":
        return infer_title(file_path)
    elif field in schema_defaults:
        return schema_defaults[field]
    return None


# ── File processing ───────────────────────────────────────────────────────────


def get_folder_name(file_path: Path, vault_dir: Path) -> str:
    try:
        rel = file_path.relative_to(vault_dir)
        parts = rel.parts
        return parts[0] if len(parts) > 1 else ""
    except ValueError:
        return ""


def should_skip_folder(folder: str) -> bool:
    return folder in SKIP_DIRS or folder == ""


def get_schema_for_folder(folder: str) -> dict[str, Any] | None:
    return SCHEMAS.get(folder)


def check_date_requirement(fm: dict[str, Any], required: list[str]) -> bool:
    if "date" not in required:
        return True
    if fm.get("date"):
        return True
    if fm.get("updated"):
        return True
    return False


def process_file(file_path: Path, vault_dir: Path, dry_run: bool, verbose: bool) -> ProcessResult:
    folder = get_folder_name(file_path, vault_dir)

    if should_skip_folder(folder):
        return ProcessResult(file_path, "skipped", [])

    schema = get_schema_for_folder(folder)
    if schema is None:
        return ProcessResult(file_path, "skipped", [])

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return ProcessResult(file_path, "error", [], str(e))

    fm, fm_raw, body = parse_frontmatter(text)

    if fm is None and fm_raw:
        return ProcessResult(file_path, "error", [], "Malformed YAML frontmatter")

    if fm is None:
        fm = {}
        has_frontmatter = False
    else:
        has_frontmatter = True

    required = schema["required"]
    defaults = schema.get("defaults", {})

    fields_to_add: list[str] = []
    new_values: dict[str, Any] = {}

    for field in required:
        if field == "date" and folder in ("memory", "memory-archive"):
            if not check_date_requirement(fm, required):
                value = infer_field_value(field, file_path, defaults)
                if value is not None:
                    fields_to_add.append(field)
                    new_values[field] = value
        elif field not in fm or fm[field] is None or fm[field] == "":
            value = infer_field_value(field, file_path, defaults)
            if value is not None:
                fields_to_add.append(field)
                new_values[field] = value

    if not fields_to_add:
        return ProcessResult(file_path, "ok", [])

    updated_fm = dict(fm)
    for field in fields_to_add:
        updated_fm[field] = new_values[field]

    if not dry_run:
        new_fm_str = serialize_frontmatter(updated_fm)
        if has_frontmatter:
            new_text = f"---\n{new_fm_str}\n---\n{body}"
        else:
            new_text = f"---\n{new_fm_str}\n---\n\n{text}"

        tmp_path = file_path.with_suffix(".md.tmp")
        try:
            tmp_path.write_text(new_text, encoding="utf-8")
            os.replace(tmp_path, file_path)
        except OSError as e:
            if tmp_path.exists():
                tmp_path.unlink()
            return ProcessResult(file_path, "error", [], str(e))

    return ProcessResult(file_path, "updated", fields_to_add)


# ── File discovery ────────────────────────────────────────────────────────────


def iter_md_files(vault_dir: Path, folder_filter: str | None = None) -> list[Path]:
    files: list[Path] = []

    if folder_filter:
        target = vault_dir / folder_filter
        if not target.exists():
            return []
        for root, dirs, filenames in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in filenames:
                if fn.endswith(".md"):
                    files.append(Path(root) / fn)
    else:
        for root, dirs, filenames in os.walk(vault_dir):
            rel_root = Path(root).relative_to(vault_dir)
            root_parts = rel_root.parts
            if root_parts and root_parts[0] in SKIP_DIRS:
                dirs[:] = []
                continue
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in filenames:
                if fn.endswith(".md"):
                    files.append(Path(root) / fn)

    return sorted(files)


# ── Main ──────────────────────────────────────────────────────────────────────


def run(dry_run: bool = False, folder_filter: str | None = None, verbose: bool = False) -> Stats:
    print(f"Scanning vault at {VAULT_DIR}...")
    print(f"Skipping: {', '.join(sorted(SKIP_DIRS))}\n")

    files = iter_md_files(VAULT_DIR, folder_filter)
    stats = Stats()

    files_by_folder: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        folder = get_folder_name(f, VAULT_DIR)
        files_by_folder[folder].append(f)

    for folder in sorted(files_by_folder.keys()):
        folder_files = files_by_folder[folder]

        if should_skip_folder(folder):
            stats.files_skipped += len(folder_files)
            continue

        schema = get_schema_for_folder(folder)
        if schema is None:
            stats.files_skipped += len(folder_files)
            continue

        print(f"Processing folder: {folder} ({len(folder_files)} files)")

        for file_path in folder_files:
            result = process_file(file_path, VAULT_DIR, dry_run, verbose)
            stats.files_scanned += 1

            if result.status == "ok":
                stats.files_complete += 1
                if verbose:
                    print(f"  {file_path.relative_to(VAULT_DIR)}: OK (complete)")
            elif result.status == "updated":
                stats.files_updated += 1
                fields_str = ", ".join(result.fields_added)
                print(f"  {file_path.relative_to(VAULT_DIR)}: added [{fields_str}]")
                for field in result.fields_added:
                    stats.fields_added[field] += 1  # type: ignore[index]
            elif result.status == "error":
                stats.files_error += 1
                print(f"  {file_path.relative_to(VAULT_DIR)}: ERROR - {result.error_message}")
            elif result.status == "skipped":
                stats.files_skipped += 1

    print("\n=== Summary ===")
    total = stats.files_scanned
    complete_pct = (stats.files_complete / total * 100) if total > 0 else 0
    updated_pct = (stats.files_updated / total * 100) if total > 0 else 0

    print(f"Files scanned:    {stats.files_scanned}")
    print(f"Files complete:   {stats.files_complete} ({complete_pct:.1f}%)")
    print(f"Files updated:    {stats.files_updated} ({updated_pct:.1f}%)")
    print(f"Files skipped:    {stats.files_skipped} (non-schema folders)")
    if stats.files_error > 0:
        print(f"Files with errors: {stats.files_error}")

    total_fields = sum(stats.fields_added.values())  # type: ignore[union-attr]
    print(f"Fields added:     {total_fields}")

    for field, count in sorted(stats.fields_added.items(),  # type: ignore[union-attr]
                               key=lambda x: x[1], reverse=True):
        print(f"  - {field}:{' ' * max(1, 14 - len(field))}{count}")

    if dry_run:
        print("\n(dry-run: no changes written)")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce frontmatter schemas on a markdown vault.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--folder", type=str, default=None, help="Only process this top-level folder")
    parser.add_argument("--verbose", action="store_true", help="Show each file processed")
    args = parser.parse_args()

    run(dry_run=args.dry_run, folder_filter=args.folder, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    if not os.environ.get("VAULT_PATH"):
        print("ERROR: VAULT_PATH environment variable is not set. See .env.example.",
              file=sys.stderr)
        sys.exit(1)
    sys.exit(main())
