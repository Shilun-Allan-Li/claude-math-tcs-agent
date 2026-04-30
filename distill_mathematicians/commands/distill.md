# /distill

Step the distillation pipeline forward by one item.

## Usage

```
/distill                    # auto-pick: distill next pending source, or skill the next pending distilled file
/distill <source_id>        # distill a specific source (e.g. /distill 2401.12345)
/distill skill <id>         # create a skill from a specific distilled file
/distill status             # show the queue (no dispatch)
```

## Instructions

1. If argument is `status` (or empty and the user wants a peek): run
   ```
   python3 -m distill_mathematicians.lib.run
   ```
   and print the output verbatim.

2. If a specific source id is given: dispatch the `distiller` agent:

   > "Distill source `<source_id>`. Read `distill_mathematicians/manifest.json` for the entry, fetch the source, write findings to `distill_mathematicians/distilled/<source_id>.md`."

3. If `skill <id>` is given: dispatch the `skill-creator` agent:

   > "Read `distill_mathematicians/distilled/<id>.md`. If any pattern passes the capability-multiplier test, write one skill into `skills/<category>/<skill-slug>.md`. Otherwise print the no-skill verdict."

4. **No argument (auto-step):** ask the queue for the next pending item:
   ```
   python3 -m distill_mathematicians.lib.run --next
   ```
   Output is `distill <id>`, `skill <id>`, or `none`. Dispatch accordingly. If `none`, print "Pipeline empty — collect more sources via `python3 -m distill_mathematicians.lib.collect`."

5. After dispatch, run `python3 -m distill_mathematicians.lib.run` again and print the new queue state so the user can see what's next.

$ARGUMENTS
