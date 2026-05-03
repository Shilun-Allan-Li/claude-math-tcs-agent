# config/

Per-user configuration. None of the generated files are committed — they live only on your machine. The single committed file is the generator.

## Files

| File         | What it captures                                           | How it's filled                                            |
|--------------|------------------------------------------------------------|------------------------------------------------------------|
| `user.md`    | identity, focus area, comfort level, prose style           | git auto + 6 user picks                                    |
| `soul.md`    | which great-mathematician heuristic mind to inject         | REGISTRY auto + 1 user pick                                |
| `agents.md`  | which proving agents are enabled                           | filesystem auto + 3 user picks                             |
| `tools.md`   | which CLI tools / fetchers are wired in                    | `which`-probe auto + 4 user picks                          |

All four are gitignored — see `.gitignore`.

## First-time setup

```bash
python3 config/generate.py            # interactive — asks ~14 picks total
python3 config/generate.py --defaults # non-interactive — writes <USER> markers and defaults
```

Re-running is idempotent: existing files are skipped unless `--force` is passed. Regenerate one file at a time with `--only soul` (or `user`, `agents`, `tools`).

## Half-auto contract

Each file has two sections:

1. **Auto** — filled from environment (git config, `shutil.which`, on-disk agent definitions, REGISTRY in `distill_mathematicians/lib/collect.py`).
2. **User** — picks the script can't infer; defaults are documented inline so `--defaults` produces a usable file even without prompting.

If you change machines or install new tools, re-run `python3 config/generate.py --force --only tools` to refresh the auto sections without losing your picks (back up your old file first if you want to merge by hand).
