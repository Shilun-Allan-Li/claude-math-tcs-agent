# claude-math-tcs-agent

**Formalize · review · simplify** Lean proofs with either **Codex or Claude Code**.
Dedicated agents handle the mathematics; a Python harness checks the results with Lean.

## Quick start

You need Python 3.11+, either Codex or Claude Code, and an existing Lean project with `lake` on your PATH,
dependencies already built, and a `lake-manifest.json` file.

Choose your tool below. Install from GitHub—no personal filesystem paths are needed.
The GitHub instructions use the published version; local changes must be pushed first.

### Codex

Run these commands in your terminal:

```bash
codex plugin marketplace add Shilun-Allan-Li/claude-math-tcs-agent
codex plugin add math-tcs@math-tcs-local
```

Open your **Lean project** in a new Codex thread. Select the plugin's `formalize`, `review`,
or `simplify` skill and describe the task, for example:

```text
Use formalize to complete Demo.my_theorem in Main.lean.
Use review to compare Demo.my_theorem in Main.lean with its statement in notes.md.
Use simplify on Demo.my_theorem in Main.lean without changing its statement.
```

### Claude Code

In Claude Code, send these two commands separately:

```text
/plugin marketplace add Shilun-Allan-Li/claude-math-tcs-agent
/plugin install math-tcs@math-tcs-local
```

Start a new session in your **Lean project**, then send one of these commands using your
own file and theorem names:

```text
/math-tcs:formalize In Main.lean, formalize: for every natural number n, 0 + n = n.
/math-tcs:review Compare Demo.my_theorem in Main.lean with its statement in notes.md.
/math-tcs:simplify Simplify the proof of Demo.my_theorem in Main.lean without changing its statement.
```

`formalize` and `simplify` apply changes after review and Lean checks; `review` leaves your
Lean files unchanged. The agent handles the harness commands. Task reports are saved under
`math-tcs/tasks/<id>/task.json` in your Lean project, including any unfinished attempts.

More details: [everyday guide](plugins/math-tcs/docs/everyday.md) ·
[validation status](plugins/math-tcs/docs/validation.md).
