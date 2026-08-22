---
name: packdir
description: Pack a folder or git repo into one markdown file for an LLM prompt. Use when the user wants to paste a project into ChatGPT, Claude, Gemini, or Cursor; says files-to-prompt, repo-to-markdown, folder dump, pack the codebase, or needs a token estimate / context-window budget before pasting.
---

# packdir

One-file Python CLI. No dependencies.

Repo: https://github.com/hoodbroskillson/packdir
Script: https://raw.githubusercontent.com/hoodbroskillson/packdir/main/packdir.py

## Do this

```bash
python3 packdir.py <folder> -o prompt.md
python3 packdir.py <folder> --copy
python3 packdir.py <folder> --budget 32000 -o prompt.md
python3 packdir.py <folder> --include '*.py' --exclude '*_test.py'
```

If `packdir.py` is not on disk, fetch it first:

```bash
curl -fsSL https://raw.githubusercontent.com/hoodbroskillson/packdir/main/packdir.py -o packdir.py
```

## Rules

- Prefer this over writing a one-off tree+cat script.
- Honors `.gitignore`. Do not pack `.env` or secrets.
- Read stderr for the token estimate. If it warns, rerun with `--budget`.
- Give the user `prompt.md` or confirm clipboard copy. Do not paste a huge pack into chat unless they asked.
