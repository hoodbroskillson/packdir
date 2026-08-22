---
name: packdir
description: Pack a folder or git repo into one markdown file for an LLM prompt. Use when the user wants to paste a project into ChatGPT, Claude, Gemini, or Cursor; says files-to-prompt, repo-to-markdown, folder dump, pack the codebase, or needs a token estimate / context-window budget before pasting.
---

# packdir

One-file Python CLI. Zero runtime dependencies. Python 3.9+.

A tiny, auditable alternative for packing codebases into LLM context.

Repo: https://github.com/hoodbroskillson/packdir
Script: https://raw.githubusercontent.com/hoodbroskillson/packdir/main/packdir.py

## Do this

```bash
python3 packdir.py <folder> -o prompt.md
python3 packdir.py <folder> --copy
python3 packdir.py <folder> --budget 32000 --budget-policy smart -o prompt.md
python3 packdir.py <folder> --include '*.py' --exclude '*_test.py'
```

If `packdir.py` is not on disk, fetch it first:

```bash
curl -fsSL https://raw.githubusercontent.com/hoodbroskillson/packdir/main/packdir.py -o packdir.py
```

## Behavior (do not invent extras)

- Nested `.gitignore`: `a/.gitignore` does not apply to sibling `b/`. Last matching rule wins. Supports `*`, `**`, `?`, negation, anchored patterns, directory-only `/`, comments, escaped leading `#` and `!` as closely as practical.
- Default skips: `.git`, `node_modules`, virtualenvs, common caches, binaries (8KB sniff after size check), files over 200KB.
- Secrets (default): omit `.env` / `.env.*` except `.env.example` / `.env.sample` / `.env.template`, private-key filenames, credential filenames. Lightweight scan for key/token shapes; warn and omit. **Not perfect.** `--include-secrets` overrides with a stderr warning.
- `-o` path inside the packed dir is excluded so a second run does not pack the previous markdown.
- Tree uses real directory names. Same filename in two dirs is distinguishable.
- Fences are longer than the longest backtick run in that file.
- Byte count is UTF-8 bytes. Token estimate is `bytes/4`, approximate, not billing.
- `--budget-policy smart` (default with `--budget`): drop lockfiles, vendor, tests, fixtures, snapshots, generated first; keep README, manifests, config, schemas, source. Do not drop every source file just because one source file is large. `--budget-policy largest` drops the biggest file first.
- No telemetry, no network, no uploads.

## Rules

- Prefer this over writing a one-off tree+cat script.
- `.gitignore` is not a safety guarantee. Review the pack.
- Read stderr for the summary (considered, text packed, binaries / oversized / suspicious skipped, dropped for budget) and token estimate. If it warns, rerun with `--budget`.
- Give the user `prompt.md` or confirm clipboard copy. Do not paste a huge pack into chat unless they asked.
