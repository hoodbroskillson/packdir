# packdir

Pack a folder into one markdown file you can paste into ChatGPT, Claude, or Cursor.

Skips the usual junk (`.git`, `node_modules`, virtualenvs, caches), skips binaries, and caps huge files so you do not dump a 40MB prompt by accident.

Before you paste, it prints a rough token count and warns if you are about to blow a context window.

## Use it

```bash
python3 packdir.py .
python3 packdir.py ./my-app -o prompt.md
python3 packdir.py ./my-app --copy
python3 packdir.py ./my-app --max-tokens 32000 -o prompt.md
```

No dependencies. Python 3.9+.

`--copy` uses `clip` on Windows, `pbcopy` on macOS, or `wl-copy` / `xclip` on Linux.

Token count is `chars / 4`. It is a fit-check, not a billing meter.

## Example

```bash
python3 packdir.py . -o prompt.md
```

stderr:

```
1842 bytes, ~461 tokens (chars/4)
wrote prompt.md
```

`prompt.md` starts with a tree, then each text file. Paste it into any chat model.

## Why this exists

You already do this by hand: copy a few files, forget one, paste a wall of text. `packdir` makes that one command, and tells you if the result is too big to paste.

## License

MIT
