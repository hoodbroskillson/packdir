# packdir

Pack a folder into one markdown file you can paste into ChatGPT, Claude, or Cursor.

Skips the usual junk (`.git`, `node_modules`, virtualenvs, caches), skips binaries, and caps huge files so you do not dump a 40MB prompt by accident.

## Use it

```bash
python3 packdir.py .
python3 packdir.py ./my-app -o prompt.md
```

No dependencies. Python 3.9+.

## Why this exists

You already do this by hand: copy a few files, forget one, paste a wall of text. `packdir` makes that one command.

## License

MIT
