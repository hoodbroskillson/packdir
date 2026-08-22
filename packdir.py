#!/usr/bin/env python3
"""Pack a folder into one markdown file for LLM prompts."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALWAYS_SKIP_DIRS = {".git", ".hg", ".svn"}

DEFAULT_SKIP_DIRS = {
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
DEFAULT_MAX_TOKENS = 128_000


@dataclass
class IgnoreRule:
    regex: re.Pattern[str]
    negated: bool
    dir_only: bool


def gitignore_to_regex(pattern: str, base: str) -> re.Pattern[str]:
    anchored = pattern.startswith("/")
    if anchored:
        pattern = pattern[1:]
    if pattern.startswith("**/"):
        pattern = pattern[3:]
        anchored = False
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            parts.append(".*")
            i += 2
            continue
        ch = pattern[i]
        if ch == "*":
            parts.append("[^/]*")
        elif ch == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(ch))
        i += 1
    body = "".join(parts)
    if anchored or "/" in pattern.rstrip("/"):
        prefix = re.escape(base) + "/" if base else ""
        expr = "^" + prefix + body + "$"
    else:
        expr = "^(?:.*/)?" + body + "$"
    return re.compile(expr)


def load_gitignore(path: Path, root: Path) -> list[IgnoreRule]:
    rules: list[IgnoreRule] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rules
    base = path.parent.relative_to(root).as_posix()
    if base == ".":
        base = ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        dir_only = line.endswith("/")
        if dir_only:
            line = line.rstrip("/")
        if not line:
            continue
        rules.append(
            IgnoreRule(gitignore_to_regex(line, base), negated=negated, dir_only=dir_only)
        )
    return rules


def ignored(rel: str, is_dir: bool, rules: list[IgnoreRule]) -> bool:
    ignored_now = False
    for rule in rules:
        if rule.dir_only and not is_dir:
            continue
        if rule.regex.match(rel):
            ignored_now = not rule.negated
    return ignored_now


def matches_any(rel: str, patterns: list[str]) -> bool:
    name = rel.split("/")[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:8000]
    except OSError:
        return True
    return b"\x00" in chunk


@dataclass
class PackedFile:
    rel: str
    body: str
    kind: str  # text, binary, skipped, error


def collect_files(
    root: Path,
    *,
    use_gitignore: bool,
    include: list[str],
    exclude: list[str],
) -> list[Path]:
    rules: list[IgnoreRule] = []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""

        if use_gitignore and (current / ".gitignore").is_file():
            rules.extend(load_gitignore(current / ".gitignore", root))

        keep_dirs: list[str] = []
        for name in sorted(dirnames):
            if name in ALWAYS_SKIP_DIRS:
                continue
            child = f"{rel_dir}/{name}".lstrip("/") if rel_dir else name
            if name in DEFAULT_SKIP_DIRS:
                continue
            if use_gitignore and ignored(child, True, rules):
                continue
            if exclude and matches_any(child, exclude):
                continue
            keep_dirs.append(name)
        dirnames[:] = keep_dirs

        for name in sorted(filenames):
            if name in SKIP_FILES:
                continue
            path = current / name
            if path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if use_gitignore and ignored(rel, False, rules):
                continue
            if exclude and matches_any(rel, exclude):
                continue
            if include and not matches_any(rel, include):
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


def read_packed(root: Path, path: Path) -> PackedFile:
    rel = path.relative_to(root).as_posix()
    if is_probably_binary(path):
        return PackedFile(rel, "_binary skipped_", "binary")
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            return PackedFile(rel, f"_skipped, {size} bytes_", "skipped")
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return PackedFile(rel, f"_unreadable: {err}_", "error")
    fence = "````" if "```" in text else "```"
    return PackedFile(rel, f"{fence}\n{text.rstrip()}\n{fence}", "text")


def render(root: Path, packed: list[PackedFile], dropped: list[str]) -> str:
    files_for_tree = [root / p.rel for p in packed]
    parts = [
        f"# {root.name}",
        "",
        "Packed for an LLM prompt. Honors .gitignore. Skip binaries.",
        "",
        "## Tree",
        "",
        "```",
        *tree_lines(root, files_for_tree),
        "```",
        "",
    ]
    if dropped:
        parts += ["## Dropped to fit budget", "", *[f"- {name}" for name in dropped], ""]
    parts += ["## Files", ""]
    for item in packed:
        parts.append(f"### {item.rel}\n\n{item.body}\n")
    return "\n".join(parts).rstrip() + "\n"


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def apply_budget(
    root: Path, packed: list[PackedFile], budget: int
) -> tuple[list[PackedFile], list[str], str]:
    dropped: list[str] = []
    current = list(packed)
    markdown = render(root, current, dropped)
    while estimate_tokens(markdown) > budget:
        texts = [p for p in current if p.kind == "text"]
        if not texts:
            break
        largest = max(texts, key=lambda p: len(p.body))
        current.remove(largest)
        dropped.append(f"{largest.rel} (~{estimate_tokens(largest.body):,} tokens)")
        markdown = render(root, current, dropped)
    return current, dropped, markdown


def copy_to_clipboard(text: str) -> None:
    if sys.platform == "win32" and shutil.which("clip"):
        subprocess.run(["clip"], input=text.encode("utf-8"), check=True)
        return
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        return
    for cmd in (
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return
    raise RuntimeError("no clipboard command found (clip, pbcopy, wl-copy, xclip, or xsel)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pack a folder into one markdown file for LLM prompts."
    )
    parser.add_argument("path", nargs="?", default=".", help="Folder to pack")
    parser.add_argument("-o", "--output", help="Write to this file instead of stdout")
    parser.add_argument(
        "-c", "--copy", action="store_true", help="Copy the packed prompt to the clipboard"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Warn if the estimate is over this (default: 128000)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        metavar="TOKENS",
        help="Drop the largest files until the estimate fits this many tokens",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Only pack paths matching this glob (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Skip paths matching this glob (repeatable)",
    )
    parser.add_argument(
        "--no-gitignore",
        action="store_true",
        help="Do not read .gitignore files",
    )
    args = parser.parse_args(argv)

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"packdir: not a directory: {root}", file=sys.stderr)
        return 1

    paths = collect_files(
        root,
        use_gitignore=not args.no_gitignore,
        include=args.include,
        exclude=args.exclude,
    )
    packed = [read_packed(root, path) for path in paths]
    dropped: list[str] = []
    if args.budget is not None:
        packed, dropped, markdown = apply_budget(root, packed, args.budget)
    else:
        markdown = render(root, packed, dropped)

    tokens = estimate_tokens(markdown)
    print(
        f"{len(paths)} files considered, {len(packed)} packed, "
        f"{len(markdown)} bytes, ~{tokens:,} tokens (chars/4)",
        file=sys.stderr,
    )
    if dropped:
        print("dropped to fit budget:", file=sys.stderr)
        for name in dropped:
            print(f"  {name}", file=sys.stderr)
    limit = args.budget if args.budget is not None else args.max_tokens
    if tokens > limit:
        print(
            f"warning: ~{tokens:,} tokens is over {limit:,}. "
            "This will likely blow the context window.",
            file=sys.stderr,
        )

    if args.copy:
        try:
            copy_to_clipboard(markdown)
        except (RuntimeError, subprocess.CalledProcessError) as err:
            print(f"packdir: clipboard failed: {err}", file=sys.stderr)
            return 1
        print("copied to clipboard", file=sys.stderr)

    if args.output:
        out = Path(args.output).expanduser()
        out.write_text(markdown, encoding="utf-8")
        print(f"wrote {out}", file=sys.stderr)
    elif not args.copy:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
