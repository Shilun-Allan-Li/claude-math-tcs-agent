# claude_prover — Math Proof Assistant for Claude Code

A multi-agent system for constructing rigorous mathematical proofs without hitting token limits.

## Installation

```bash
PROJECT=/path/to/your/project
mkdir -p $PROJECT/.claude/agents $PROJECT/.claude/commands $PROJECT/.claude/hooks

# Customer-facing prover surface
cp claude_prover/CLAUDE.md $PROJECT/.claude/CLAUDE.md
cp claude_prover/agents/*  $PROJECT/.claude/agents/
cp claude_prover/commands/* $PROJECT/.claude/commands/

# Engineer (compute helper)
cp engineers/agents/engineer.md $PROJECT/.claude/agents/
cp engineers/commands/engineer.md $PROJECT/.claude/commands/

# Hook (keeps OUTLINE.md ticks in sync with step files)
cp .claude/hooks/step_index.py $PROJECT/.claude/hooks/
# Add the PostToolUse hook entry from .claude/settings.local.json to $PROJECT/.claude/settings.local.json
```

Then `cd $PROJECT && claude .`.

## Layout

```
.claude/
├── CLAUDE.md                     ← system overview (auto-loaded)
├── agents/
│   ├── proof-orchestrator.md     ← plans, manages outline, assembles
│   ├── proof-prover.md           ← works on one step at a time
│   ├── proof-explorer.md         ← brainstorms, tries examples
│   ├── proof-formatter.md        ← PDF/tar/tex → markdown
│   ├── proof-reviewer.md         ← audits steps for correctness
│   └── engineer.md               ← compute helper
├── commands/
│   ├── prove.md                  ← /prove
│   ├── proof-step.md             ← /proof-step
│   ├── explore.md                ← /explore
│   ├── format-paper.md           ← /format-paper
│   ├── proof-status.md           ← /proof-status
│   ├── proof-outline.md          ← /proof-outline
│   └── engineer.md               ← /engineer
└── hooks/
    └── step_index.py             ← syncs OUTLINE.md ticks with step files
```

## Typical workflow

```
/format-paper papers/source/my_reference.pdf      # optional
/prove "Theorem: ..."
/proof-status
/proof-step 1
/proof-step 2
/explore "why X works"
/proof-step 3
/prove --assemble
/proof-step review
```

## Why agents instead of one big prompt?

Large proofs exceed Claude's output token limit when attempted in a single response. This system breaks every proof into numbered steps, each ~500 words. Each step is worked on by a focused agent with only the necessary context, saved to its own file (`proof/step_NN.md`), and tracked in `proof/OUTLINE.md`.

You can pause, resume, fix individual steps, and assemble at the end — without ever hitting a token wall.

## Requirements

For PDF formatting: `pdftotext` (poppler-utils) or `pandoc`.
For tar/zip extraction: standard `tar` and `unzip`.
