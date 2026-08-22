# packdir

Pack a folder into one markdown file you can paste into ChatGPT, Claude, or Cursor.

Honors `.gitignore` (so `.env` stays out). Skips the usual junk dirs, skips binaries, and caps huge files.

Before you paste, it prints a rough token count. `--budget` drops the largest files until the pack fits.

## Use it

```bash
python3 packdir.py .
python3 packdir.py ./my-app -o prompt.md
python3 packdir.py ./my-app --copy
python3 packdir.py ./my-app --include '*.py' --exclude '*_test.py'
python3 packdir.py ./my-app --budget 32000 -o prompt.md
```

No dependencies. Python 3.9+.

`--copy` uses `clip` on Windows, `pbcopy` on macOS, or `wl-copy` / `xclip` on Linux.

Token count is `chars / 4`. It is a fit-check, not a billing meter.

`--no-gitignore` if you really want everything.

## Example

```bash
python3 packdir.py . --budget 8000 -o prompt.md
```

stderr:

```
12 files considered, 9 packed, 18420 bytes, ~4,605 tokens (chars/4)
dropped to fit budget:
  vendor/big.js (~9,200 tokens)
wrote prompt.md
```

## Why this exists

You already do this by hand: copy a few files, forget one, paste a wall of text. `packdir` makes that one command, respects what git already ignores, and tells you if the result is too big to paste.

## License

MIT
