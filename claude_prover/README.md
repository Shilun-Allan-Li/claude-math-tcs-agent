# claude_prover — Math Proof Assistant for Claude Code

A multi-agent system for constructing rigorous mathematical proofs without hitting token limits.

## Installation

The customer-facing surface is `claude_prover/`, but it depends on the engineer (compute service) and the intern (file housekeeping) to function end-to-end. Copy all three plus the deterministic hooks into your target project's `.claude/` tree:

```bash
PROJECT=/path/to/your/project
mkdir -p $PROJECT/.claude/agents $PROJECT/.claude/commands $PROJECT/.claude/hooks

# 1. Customer-facing prover surface
cp claude_prover/CLAUDE.md $PROJECT/.claude/CLAUDE.md
cp claude_prover/agents/*  $PROJECT/.claude/agents/
cp claude_prover/commands/* $PROJECT/.claude/commands/

# 2. Engineer (compute service the prover and explorer dispatch via Task)
cp engineers/agents/engineer.md $PROJECT/.claude/agents/
cp engineers/commands/engineer.md $PROJECT/.claude/commands/
cp -r engineers/lib $PROJECT/.claude/engineer_lib   # the audit harness

# 3. Intern (proof/ tree housekeeping after outline edits)
cp interns/agents/intern.md $PROJECT/.claude/agents/
cp interns/commands/intern.md $PROJECT/.claude/commands/
cp .claude/hooks/*.py $PROJECT/.claude/hooks/

# 4. Settings (hooks must be registered)
# Merge .claude/settings.local.json hooks block into $PROJECT/.claude/settings.local.json
```

Then `cd $PROJECT && claude .`.

If you only want the prover and skip computation/housekeeping, install (1) alone — the prover degrades gracefully (no engineer = no computational delegation; no intern = manual `proof/` cleanup).

## What's Included

```
.claude/
├── CLAUDE.md                     ← System overview (auto-loaded by Claude Code)
├── agents/
│   ├── proof-orchestrator.md     ← Plans proofs, manages outline, assembles results
│   ├── proof-prover.md           ← Works on one proof step at a time
│   ├── proof-explorer.md         ← Brainstorms strategies, tries examples
│   ├── proof-formatter.md        ← Converts PDF/tar/tex to agent-readable markdown
│   └── proof-reviewer.md         ← Audits completed steps for correctness
└── commands/
    ├── prove.md                  ← /prove
    ├── proof-step.md             ← /proof-step
    ├── explore.md                ← /explore
    ├── format-paper.md           ← /format-paper
    ├── proof-status.md           ← /proof-status
    └── proof-outline.md          ← /proof-outline
```

## Typical Workflow

```
# 1. (Optional) Convert a reference paper to readable format
/format-paper papers/source/my_reference.pdf

# 2. Start a new proof
/prove "Theorem (Bolzano-Weierstrass): Every bounded sequence in R^n has a convergent subsequence."

# 3. Check the generated plan
/proof-status

# 4. Work through steps one at a time
/proof-step 1
/proof-step 2
/proof-step 3

# 5. If stuck, explore before continuing
/explore "why the diagonal argument works in step 4"
/proof-step 4   # retry with exploration notes available

# 6. Check progress at any time
/proof-status

# 7. Assemble when all steps complete
/prove --assemble

# 8. Review the assembled proof
/proof-step review
```

## Design Philosophy

**Why agents instead of one big prompt?**

Large proofs exceed Claude's output token limit when attempted in a single response. This system breaks every proof into numbered steps, each ~500 words. Each step is:
- Worked on by a focused agent with only the necessary context
- Saved to its own file (`proof/step_NN.md`)
- Tracked in a central `proof/OUTLINE.md`

This means you can pause, resume, fix individual steps, and assemble at the end — without ever hitting a token wall.

**File layout at runtime:**
```
proof/
  OUTLINE.md       ← master TODO list (managed by orchestrator)
  step_01.md       ← individual step results (managed by prover)
  step_02.md
  ...
  exploration.md   ← strategy notes (managed by explorer)
  assembled.md     ← final assembled proof (produced by /prove --assemble)
  review_*.md      ← review reports (produced by reviewer)
  archive/         ← old proofs (archived by /prove --reset)
papers/
  *.md             ← formatted papers (produced by /format-paper)
```

## Requirements

For PDF formatting, one of these must be installed:
- `pdftotext` (from `poppler-utils`): `brew install poppler` / `apt install poppler-utils`
- `pandoc`: `brew install pandoc` / `apt install pandoc`

For tar/zip extraction: standard `tar` and `unzip` (available on macOS and Linux by default).
