# Math TCS

Formalize, review, and simplify individual Lean declarations in an existing project,
using Claude Code or Codex. No demo or textbook pipeline is required.

See the repository [quick start](../../README.md#quick-start) for installation.

- `formalize`: translate a statement or complete a selected `sorry`.
- `review`: inspect a declaration without editing its Lean source.
- `simplify`: improve a proof while preserving the statement.

These skills use the [ordinary-file harness](docs/agent-loop.md): independent semantic
review, bounded proof attempts, Lean/axiom checks, and checked application to your file.
Reports are saved in your project's `math-tcs/tasks/<id>/task.json`.

The retired batch commands are no longer exposed. Internal legacy modules and fixtures
remain only for regression coverage; the public CLI does not dispatch to them.

[Detailed usage](docs/everyday.md) · [Validation status](docs/validation.md)
