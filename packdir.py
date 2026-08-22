#!/usr/bin/env python3
"""Pack a folder into one markdown file for LLM prompts.

A tiny, auditable, zero-dependency alternative for packing codebases
into LLM context. Python 3.9+, no runtime dependencies.
"""

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
    ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", ".next", ".turbo",
    "target", ".idea", ".vscode",
}

SKIP_FILES = {".DS_Store", "Thumbs.db"}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".gz", ".tar", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
    ".mov", ".wav", ".pyc", ".so", ".dylib", ".dll", ".exe", ".bin", ".wasm",
}

MAX_FILE_BYTES = 200_000
DEFAULT_MAX_TOKENS = 128_000
SNIFF_BYTES = 8000
SECRET_NAME_ALLOW = {".env.example", ".env.sample", ".env.template"}
PRIVATE_KEY_NAMES = {
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "id_ecdsa_sk", "id_ed25519_sk",
}
SECRET_BASENAMES = {
    ".npmrc", ".pypirc", "credentials", "credentials.json",
    "credentials.yml", "credentials.yaml", "secrets.json", "secrets.yml",
    "secrets.yaml", "service-account.json", "serviceaccount.json",
}
SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}
SUSPICIOUS_RE = re.compile(
    "-----BEGIN " + r"(?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?" + "PRIVATE KEY-----"
    r"|-----BEGIN PGP " + "PRIVATE KEY BLOCK-----"
    r"|AKI" + r"A[0-9A-Z]{16}"
    r"|ASI" + r"A[0-9A-Z]{16}"
    r"|ghp" + r"_[A-Za-z0-9]{20,}"
    r"|github_pat" + r"_[A-Za-z0-9_]{20,}"
    r"|gho" + r"_[A-Za-z0-9]{20,}"
    r"|sk-" + r"[A-Za-z0-9]{20,}"
    r"|xox" + r"[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza" + r"[0-9A-Za-z\-_]{35}"
)
SOURCE_EXT = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go",
    ".rs", ".java", ".kt", ".kts", ".c", ".h", ".cpp", ".cc", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".scala", ".vue", ".svelte", ".zig", ".nim",
}
KEEP_NAMES = {
    "readme", "readme.md", "readme.rst", "readme.txt", "license", "license.md",
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "cargo.toml",
    "go.mod", "composer.json", "gemfile", "requirements.txt", "pipfile",
    "environment.yml", "makefile", "dockerfile", "procfile", "tsconfig.json",
    "jsconfig.json", "main.py", "app.py", "index.js", "index.ts", "index.mjs",
    "main.go", "main.rs", "lib.rs", "__init__.py", "__main__.py",
}
DEPRI_DIR_NAMES = {
    "vendor", "third_party", "third-party", "node_modules", "fixtures",
    "testdata", "snapshots", "tests", "test",
    "generated",
}
SCHEMA_EXT = {".graphql", ".gql", ".proto", ".avsc", ".xsd"}
CONFIG_EXT = {".toml", ".yaml", ".yml", ".ini", ".cfg", ".json"}
@dataclass
class IgnoreRule:
    regex: re.Pattern[str]
    negated: bool
    dir_only: bool
    base: str


@dataclass
class PackedFile:
    rel: str
    body: str
    kind: str
    raw: str = ""
    reason: str = ""


@dataclass
class Counts:
    considered: int = 0
    text: int = 0
    binary: int = 0
    oversized: int = 0
    suspicious: int = 0
    secret: int = 0
    error: int = 0
    dropped: int = 0
def gitignore_to_regex(pattern: str) -> re.Pattern[str]:
    if pattern.startswith("/"):
        pattern = pattern[1:]
    parts: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            parts.append("(?:.*/)?")
            i += 3
            continue
        if i <= n - 2 and pattern[i:i + 2] == "**":
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
    return re.compile("^" + "".join(parts) + "$")


def _is_anchored_gitignore(pattern: str) -> bool:
    if pattern.startswith("/"):
        return True
    return "/" in pattern
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
        line = raw.rstrip("\n\r")
        if not line.strip():
            continue
        leading = line.lstrip()
        if leading.startswith("#"):
            continue
        escaped = False
        if leading.startswith("\\#") or leading.startswith("\\!"):
            line = line[: len(line) - len(leading)] + leading[1:]
            escaped = True
        else:
            line = line.strip()
        negated = (not escaped) and line.startswith("!")
        if negated:
            line = line[1:]
        dir_only = line.endswith("/")
        if dir_only:
            line = line.rstrip("/")
        if not line:
            continue
        anchored = _is_anchored_gitignore(line)
        regex = gitignore_to_regex(line)
        if not anchored:
            regex = re.compile("^(?:.*/)?" + regex.pattern[1:])
        rules.append(IgnoreRule(regex=regex, negated=negated, dir_only=dir_only, base=base))
    return rules
def _rel_under_base(rel: str, base: str):
    if not base:
        return rel
    if rel == base:
        return ""
    prefix = base + "/"
    if rel.startswith(prefix):
        return rel[len(prefix):]
    return None


def ignored(rel: str, is_dir: bool, rules: list[IgnoreRule]) -> bool:
    ignored_now = False
    for rule in rules:
        local = _rel_under_base(rel, rule.base)
        if local is None:
            continue
        if local == "" and not is_dir:
            continue
        if rule.dir_only and not is_dir:
            continue
        target = local if local else Path(rel).name
        if rule.regex.match(target):
            ignored_now = not rule.negated
        elif is_dir and local == "" and rule.regex.match(Path(rel).name):
            ignored_now = not rule.negated
    return ignored_now


def matches_any(rel: str, patterns: list[str]) -> bool:
    name = rel.split("/")[-1]
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p) for p in patterns)
def is_secret_filename(name: str) -> bool:
    if name in SECRET_NAME_ALLOW:
        return False
    if name == ".env" or name.startswith(".env."):
        return True
    if name in PRIVATE_KEY_NAMES or name in SECRET_BASENAMES:
        return True
    if name.lower() in SECRET_BASENAMES:
        return True
    if Path(name).suffix.lower() in SECRET_SUFFIXES:
        return True
    return False


def looks_suspicious(sample: bytes) -> bool:
    text = sample.decode("utf-8", errors="replace")
    return SUSPICIOUS_RE.search(text) is not None


def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return True
    try:
        with path.open("rb") as fh:
            chunk = fh.read(SNIFF_BYTES)
    except OSError:
        return True
    return b"\x00" in chunk
def collect_files(
    root: Path,
    *,
    use_gitignore: bool,
    include: list[str],
    exclude: list[str],
    exclude_resolved: Path | None = None,
) -> list[Path]:
    files: list[Path] = []
    rules_by_dir: dict[str, list[IgnoreRule]] = {}

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        rel_dir = current.relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""

        parent_key = str(current.parent) if current != root else None
        inherited: list[IgnoreRule] = []
        if parent_key is not None:
            inherited = list(rules_by_dir.get(parent_key, []))
        local: list[IgnoreRule] = []
        if use_gitignore and (current / ".gitignore").is_file():
            local = load_gitignore(current / ".gitignore", root)
        rules = inherited + local
        rules_by_dir[str(current)] = rules
        keep_dirs: list[str] = []
        for name in sorted(dirnames):
            if name in ALWAYS_SKIP_DIRS:
                continue
            if name in DEFAULT_SKIP_DIRS:
                continue
            child = f"{rel_dir}/{name}".lstrip("/") if rel_dir else name
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
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if exclude_resolved is not None and resolved == exclude_resolved:
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
def tree_lines(root: Path, rels: list[str]) -> list[str]:
    tree: dict = {}
    for rel in rels:
        parts = rel.split("/")
        node = tree
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                nxt = {}
                node[part] = nxt
            node = nxt
        node[parts[-1]] = None

    lines = [root.name + "/"]

    def walk(node: dict, indent: str) -> None:
        dirs = sorted(k for k, v in node.items() if isinstance(v, dict))
        fls = sorted(k for k, v in node.items() if v is None)
        for name in dirs:
            lines.append(f"{indent}{name}/")
            walk(node[name], indent + "  ")
        for name in fls:
            lines.append(f"{indent}{name}")

    walk(tree, "  ")
    return lines


def fence_for(text: str) -> str:
    longest = 0
    run = 0
    for ch in text:
        if ch == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return "`" * max(3, longest + 1)
def read_packed(root: Path, path: Path, *, include_secrets: bool) -> PackedFile:
    rel = path.relative_to(root).as_posix()
    name = path.name
    try:
        size = path.stat().st_size
    except OSError as err:
        return PackedFile(rel, f"_unreadable: {err}_", "error", reason="unreadable")

    if size > MAX_FILE_BYTES:
        return PackedFile(
            rel,
            f"_skipped, {size} bytes (over {MAX_FILE_BYTES})_",
            "oversized",
            reason="oversized",
        )

    if not include_secrets and is_secret_filename(name):
        return PackedFile(rel, "_secret filename omitted_", "secret", reason="secret-filename")

    if path.suffix.lower() in BINARY_SUFFIXES:
        return PackedFile(rel, "_binary skipped_", "binary", reason="binary")
    try:
        with path.open("rb") as fh:
            sample = fh.read(SNIFF_BYTES)
    except OSError as err:
        return PackedFile(rel, f"_unreadable: {err}_", "error", reason="unreadable")

    if b"\x00" in sample:
        return PackedFile(rel, "_binary skipped_", "binary", reason="binary")

    if not include_secrets and looks_suspicious(sample):
        return PackedFile(
            rel,
            "_omitted: looks like a secret (heuristic, not perfect)_",
            "suspicious",
            reason="suspicious-content",
        )

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as err:
        return PackedFile(rel, f"_unreadable: {err}_", "error", reason="unreadable")

    reason = ""
    if include_secrets and looks_suspicious(sample):
        reason = "suspicious-included"
    fence = fence_for(text)
    return PackedFile(rel, f"{fence}\n{text.rstrip()}\n{fence}", "text", raw=text, reason=reason)
def drop_rank(rel: str) -> int:
    name = rel.split("/")[-1].lower()
    parts = [p.lower() for p in rel.split("/")]
    ext = Path(name).suffix.lower()
    parents = parts[:-1]
    if name.endswith(".lock") or name.endswith(".sum"):
        return 100
    if any(p in DEPRI_DIR_NAMES for p in parents):
        return 90
    if name.endswith(".snap") or ".generated." in name:
        return 85
    if name.startswith("test_") or name.endswith("_test.py"):
        return 80
    if name.endswith(".test.js") or name.endswith(".spec.ts"):
        return 80
    if name in KEEP_NAMES or name.startswith("readme"):
        return 0
    if ext in SCHEMA_EXT:
        return 5
    if ext in CONFIG_EXT:
        return 10
    if ext in SOURCE_EXT:
        return 20
    return 50
def drop_reason(rel: str, policy: str) -> str:
    if policy == "largest":
        return "largest"
    rank = drop_rank(rel)
    if rank >= 100:
        return "lockfile"
    if rank >= 90:
        return "vendor/test/fixture"
    if rank >= 85:
        return "generated/snapshot"
    if rank >= 80:
        return "test"
    if rank >= 50:
        return "other"
    if rank >= 20:
        return "source"
    return "kept-class"


def render(root: Path, packed: list[PackedFile], dropped: list[str]) -> str:
    rels = [p.rel for p in packed]
    parts = [
        f"# {root.name}",
        "",
        "Packed for an LLM prompt. Honors nested .gitignore. Skips binaries and, by default, likely secrets.",
        "",
        "## Tree",
        "",
        "```",
        *tree_lines(root, rels),
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
    return max(1, (len(text.encode("utf-8")) + 3) // 4)
def apply_budget(
    root: Path,
    packed: list[PackedFile],
    budget: int,
    policy: str,
) -> tuple[list[PackedFile], list[str], str]:
    dropped: list[str] = []
    current = list(packed)
    markdown = render(root, current, dropped)

    def drop_key(item: PackedFile) -> tuple:
        size = len(item.body.encode("utf-8"))
        if policy == "largest":
            return (size, item.rel)
        return (drop_rank(item.rel), size, item.rel)

    while estimate_tokens(markdown) > budget:
        texts = [p for p in current if p.kind == "text"]
        if not texts:
            break
        if policy == "smart":
            candidate = max(texts, key=drop_key)
        else:
            candidate = max(texts, key=lambda p: (len(p.body.encode("utf-8")), p.rel))
        current.remove(candidate)
        tokens = estimate_tokens(candidate.body)
        why = drop_reason(candidate.rel, policy)
        dropped.append(f"{candidate.rel} (~{tokens:,} tokens, {why})")
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


def summarize(packed: list[PackedFile]) -> Counts:
    c = Counts()
    c.considered = len(packed)
    for p in packed:
        if p.kind == "text":
            c.text += 1
        elif p.kind == "binary":
            c.binary += 1
        elif p.kind == "oversized":
            c.oversized += 1
        elif p.kind == "suspicious":
            c.suspicious += 1
        elif p.kind == "secret":
            c.secret += 1
        elif p.kind == "error":
            c.error += 1
    return c
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Pack a folder into one markdown file for LLM prompts. "
            "Tiny, auditable, zero-dependency."
        )
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
        help="Drop files until the estimate fits this many tokens",
    )
    parser.add_argument(
        "--budget-policy",
        choices=("smart", "largest"),
        default=None,
        help="How to choose drops when --budget is set (default: smart)",
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
    parser.add_argument(
        "--include-secrets",
        action="store_true",
        help="Do not auto-omit secret filenames or heuristic secret matches (unsafe)",
    )
    args = parser.parse_args(argv)

    if args.budget_policy and args.budget is None:
        print("packdir: --budget-policy requires --budget", file=sys.stderr)
        return 2
    policy = args.budget_policy or "smart"

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        print(f"packdir: not a directory: {root}", file=sys.stderr)
        return 1
    exclude_resolved = None
    out_path = None
    if args.output:
        out_path = Path(args.output).expanduser()
        try:
            resolved_out = out_path.resolve()
        except OSError:
            resolved_out = out_path
        try:
            resolved_out.relative_to(root)
            exclude_resolved = resolved_out
        except ValueError:
            exclude_resolved = None

    if args.include_secrets:
        print(
            "WARNING: --include-secrets is on. .env, keys, and heuristic secret "
            "matches will be packed. Detection is not perfect. Review the output.",
            file=sys.stderr,
        )

    paths = collect_files(
        root,
        use_gitignore=not args.no_gitignore,
        include=args.include,
        exclude=args.exclude,
        exclude_resolved=exclude_resolved,
    )
    packed = [read_packed(root, path, include_secrets=args.include_secrets) for path in paths]
    counts = summarize(packed)
    for item in packed:
        if item.kind == "secret":
            print(f"omitted secret filename: {item.rel}", file=sys.stderr)
        elif item.kind == "suspicious":
            print(f"omitted suspicious file (heuristic): {item.rel}", file=sys.stderr)
        elif item.reason == "suspicious-included":
            print(f"warning: included suspicious file (heuristic): {item.rel}", file=sys.stderr)

    dropped: list[str] = []
    visible = [p for p in packed if p.kind == "text"]
    notes = [p for p in packed if p.kind != "text"]
    if args.budget is not None:
        visible, dropped, _md = apply_budget(root, visible, args.budget, policy)
        markdown = render(root, visible + notes, dropped)
    else:
        markdown = render(root, visible + notes, dropped)

    counts.dropped = len(dropped)
    token_bytes = len(markdown.encode("utf-8"))
    tokens = estimate_tokens(markdown)
    print(
        f"{counts.considered} considered, {len(visible)} text packed, "
        f"{counts.binary} binaries skipped, {counts.oversized} oversized skipped, "
        f"{counts.suspicious + counts.secret} suspicious skipped, "
        f"{counts.dropped} dropped for budget, "
        f"{token_bytes} bytes (utf-8), ~{tokens:,} tokens (bytes/4, approximate)",
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

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)
    elif not args.copy:
        sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
