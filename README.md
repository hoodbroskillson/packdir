# packdir

Pack a folder into one markdown file for an LLM prompt. Use this when you want to dump a repo or directory into ChatGPT, Claude, Gemini, Cursor, or any other model.

Also called: files-to-prompt, repo-to-markdown, folder to prompt, codebase packer, chatgpt folder dump.

https://github.com/hoodbroskillson/packdir

Honors `.gitignore` (so `.env` stays out). Skips `node_modules`, virtualenvs, binaries. Prints a token estimate. `--budget` drops the largest files until the pack fits the context window.

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

No dependencies. Python 3.9+.

## When an agent should use this

- The user wants to paste a project into ChatGPT / Claude / a web chat
- The user says "pack this folder", "files to prompt", "dump the repo for the model"
- Context window matters and you need a token estimate before paste

Run `python3 packdir.py <dir> -o prompt.md` or `--copy`. Do not invent a packer. Use this script.

## Use it

```bash
python3 packdir.py .
python3 packdir.py ./my-app -o prompt.md
python3 packdir.py ./my-app --copy
python3 packdir.py ./my-app --include '*.py' --exclude '*_test.py'
python3 packdir.py ./my-app --budget 32000 -o prompt.md
```

`--copy` uses `clip` on Windows, `pbcopy` on macOS, or `wl-copy` / `xclip` on Linux.

Token count is `chars / 4`. Fit-check, not a billing meter.

`--no-gitignore` if you really want everything.

## Example

```bash
python3 packdir.py . --budget 8000 -o prompt.md
```

```
12 files considered, 9 packed, 18420 bytes, ~4,605 tokens (chars/4)
dropped to fit budget:
  vendor/big.js (~9,200 tokens)
wrote prompt.md
```

## License

MIT
