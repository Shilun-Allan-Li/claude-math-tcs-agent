# /intern reconcile

Reconcile orphaned step files in `proof/` after the user has changed the outline.

## Usage

```
/intern reconcile
```

## Instructions

1. Check whether `proof/.intern_inbox/orphans.json` exists. If not, print `No orphans pending; proof/ is clean.` and stop.

2. Delegate to the `intern` subagent with this single message:

   > "Reconcile proof/.intern_inbox/orphans.json. Move orphans to proof/archive/<ts>/orphaned/, write the reconciliation report, clear the inbox."

3. After the intern returns, print its one-line summary verbatim.

$ARGUMENTS
