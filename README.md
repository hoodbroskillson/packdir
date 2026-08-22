# packdir

A tiny, auditable, zero-dependency alternative for packing codebases into LLM context.

Pack a folder into one markdown file for ChatGPT, Claude, Gemini, Cursor, or any other model. One Python file. No pip packages. You can read the whole program.

Also called: files-to-prompt, repo-to-markdown, folder to prompt, codebase packer, chatgpt folder dump.

https://github.com/hoodbroskillson/packdir

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/hoodbroskillson/packdir/main/packdir.py -o packdir.py
python3 packdir.py .
```

Or clone:

```bash
git clone https://github.com/hoodbroskillson/packdir
python3 packdir/packdir.py /path/to/project -o prompt.md
```

Agent skill:

```bash
npx skills@latest add hoodbroskillson/packdir -y -g
```

No runtime dependencies. Python 3.9+.

## Use it

```bash
python3 packdir.py .
python3 packdir.py ./my-app -o prompt.md
python3 packdir.py ./my-app --copy
python3 packdir.py ./my-app --include '*.py' --exclude '*_test.py'
python3 packdir.py ./my-app --budget 32000 -o prompt.md
python3 packdir.py ./my-app --budget 32000 --budget-policy largest
```

`--copy` uses `clip` on Windows, `pbcopy` on macOS, or `wl-copy` / `xclip` on Linux.

The token figure is `utf-8 bytes / 4`. Approximate fit-check, not a billing meter.

`--no-gitignore` skips `.gitignore` rules (default skip dirs and secret heuristics still apply).

## Security

By default packdir:

- Honors **nested** `.gitignore` (a rule in `a/.gitignore` does not apply to sibling `b/`)
- Auto-omits `.env`, `.env.*` (except `.env.example` / `.env.sample` / `.env.template`), private key filenames (`id_rsa`, `*.pem`, …), and common credential filenames
- Runs a **lightweight, imperfect** scan for private-key headers and typical API-key/token shapes, then omits those files and warns on stderr
- Skips binaries (8KB sniff, after a size check) and files over 200KB

`.gitignore` is not a security boundary. Do not treat an ignored tree as “safe to paste.” Review the markdown before you send it.

`--include-secrets` packs secret filenames and heuristic matches anyway, and prints a prominent warning. Detection is not perfect.

Writing `-o` to a path inside the packed directory excludes that exact file so `packdir.py . -o prompt.md` twice does not swallow the previous pack.

## Budget policies

`--budget N` drops files until the estimate is at most N tokens.

| Policy | Flag | Behavior |
| --- | --- | --- |
| **smart** (default) | `--budget-policy smart` | Drop lockfiles, vendor, tests, fixtures, snapshots, generated files first. Keep README, manifests, config, schemas, entry points, and source. Among source files, drop the largest first so one huge file does not wipe the rest of the source tree. |
| **largest** | `--budget-policy largest` | Always drop the largest remaining text file (old behavior). |

Each drop is listed with a path, approximate tokens, and a reason. Order is deterministic.

## Example

```bash
python3 packdir.py . --budget 8000 --budget-policy smart -o prompt.md
```

```
12 considered, 9 text packed, 1 binaries skipped, 0 oversized skipped, 0 suspicious skipped, 1 dropped for budget, 18420 bytes (utf-8), ~4,605 tokens (bytes/4, approximate)
dropped to fit budget:
  vendor/big.js (~9,200 tokens, vendor/test/fixture)
wrote prompt.md
```

## Comparison-friendly features

- Single-file script you can curl and audit
- Zero runtime dependencies, no telemetry, no uploads
- Nested `.gitignore` with negation, anchors, directory-only rules
- Real directory tree (same filename in two folders stays distinguishable)
- Markdown fences sized to the longest backtick run in each file
- UTF-8 byte counts (not Latin-1 character counts)
- Secret filename + heuristic content filter (opt-in override)
- Smart vs largest context budget

## Limitations

- Gitignore support is practical, not a full git implementation (no `**` corner-case identity with libgit2)
- Secret scanning is heuristic. It will miss real secrets and can flag lookalikes
- Token estimates are not model-specific and are not for billing
- Default directory skips (`node_modules`, `.venv`, …) are built in, not only `.gitignore`
- No network, no archive upload, no editor integration

## When an agent should use this

- The user wants to paste a project into ChatGPT / Claude / a web chat
- The user says "pack this folder", "files to prompt", "dump the repo for the model"
- Context window matters and you need a token estimate before paste

Run `python3 packdir.py <dir> -o prompt.md` or `--copy`. Do not invent a packer.

## License

MIT
