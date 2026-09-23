---
name: ping
description: Diagnostic for the math-tcs plugin — shows how the plugin sees its arguments, plugin root, and agents. Use when the user runs /math-tcs:ping.
argument-hint: "[any words] [--until stage]"
allowed-tools: Bash(python3 *mathtcs.py*), Bash(echo *)
---

Injected args: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/mathtcs.py" args ping $ARGUMENTS`
Plugin root: !`echo "${CLAUDE_PLUGIN_ROOT}"`
Raw ARGUMENTS: $ARGUMENTS

Reply with exactly the three lines above (Injected args / Plugin root / Raw ARGUMENTS), verbatim, and nothing else. Do not run any tools.
