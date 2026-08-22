#!/usr/bin/env python3
"""Pack a folder into one markdown file for LLM prompts."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".turbo",
    "target",
    ".idea",
    ".vscode",
}

SKIP_FILES = {".DS_Store", "Thumbs.db"}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp3",
    ".mp4",
    ".mov",
    ".wav",
    ".pyc",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bin",
    ".wasm",
}

MAX_FILE_BYTES = 200_000


def should_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".git")


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:8000]
    except OSError:
        return True
    return b"\x00" in chunk


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not should_skip_dir(d))
        for name in sorted(filenames):
            if name in SKIP_FILES:
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            files.append(path)
    return files


def tree_lines(root: Path, files: list[Path]) -> list[str]:
    rels = [p.relative_to(root).as_posix() for p in files]
    lines = [root.name + "/"]
    for rel in rels:
        depth = rel.count("/")
        name = rel.split("/")[-1]
        lines.append(("  " * (depth + 1)) + name)
    return lines


def pack(root: Path) -> str:
    files = collect_files(root)
    parts = [
        f"# {root.name}",
        "",
        "Packed for an LLM prompt. Skip junk dirs. Skip binaries.",
        "",
        "## Tree",
        "",
        "```",
        *tree_lines(root, files),
        "```",
        "",
        "## Files",
        "",
    ]
    for path in files:
        rel = path.relative_to(root).as_posix()
        if is_probably_binary(path):
            parts.append(f"### {rel}\n\n_binary skipped_\n")
            continue
        try:
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                parts.append(f"### {rel}\n\n_skipped, {size} bytes_\n")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            parts.append(f"### {rel}\n\n_unreadable: {err}_\n")
            continue
        fence = "```"
        if "```" in text:
            fence = "````"
        parts.append(f"### {rel}\n\n{fence}\n{text.rstrip()}\n{fence}\n")
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack a folder into one markdown file for LLM prompts."
    )
    parser.add_argument("path", nargs="?", default=".", help="Folder to pack")
    parser.add_argument("-o", "--output", help="Write to this file instead of stdout")
    args = parser.parse_args(argv)

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"packdir: not a directory: {root}", file=sys.stderr)
        return 1

    markdown = pack(root)
    if args.output:
        out = Path(args.output).expanduser()
        out.write_text(markdown, encoding="utf-8")
        print(f"wrote {out} ({len(markdown)} bytes)", file=sys.stderr)
    else:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
