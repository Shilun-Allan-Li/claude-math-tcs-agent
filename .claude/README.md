# prover_claude — Math Proof Assistant for Claude Code

A multi-agent system for constructing rigorous mathematical proofs without hitting token limits.

## Installation

Copy this directory as `.claude` in your project:

```bash
cp -r prover_claude /path/to/your/project/.claude
cd /path/to/your/project
claude   # or: claude .
```

Or if you already have a `.claude` directory, merge selectively:

```bash
cp -r prover_claude/agents/* /path/to/your/project/.claude/agents/
cp -r prover_claude/commands/* /path/to/your/project/.claude/commands/
# Merge CLAUDE.md contents manually into your existing .claude/CLAUDE.md
```

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
