Build the first usable version of an installable Claude Code plugin named math-tcs for my summer mathematics/TCS formalization work.

I want to install it once and invoke either an individual stage or the whole pipeline from Claude Code. Use native skills and custom subagents, running through the existing authenticated Claude Code session. Use small scripts for deterministic work such as file handling and Lean checks.

Keep this version focused on four actions: translate, scaffold, verify, and prove. Leave graph engineering and graph-based context selection out of scope.

Commands to implement

Command	Behavior
/math-tcs:translate <source>	Produce annotated Markdown from a source excerpt or file.
/math-tcs:scaffold <annotated-md>	Produce a Lean scaffold with theorem proof stubs.
/math-tcs:verify <lean-file-or-id>	Check elaboration, review statement fidelity, and identify reuse opportunities.
/math-tcs:prove <lean-file-or-id>	Attempt proofs for eligible declarations and run final Lean checks.
/math-tcs:run <source>	Run the stages in order, continuing through proof attempts for eligible declarations.

Support --until verify on run so I can inspect the scaffold and reports before proving. Treat these arguments as part of the plugin interface and actually implement their handling.

Stage responsibilities

Translate

Preserve the original excerpt and source location. Write annotated Markdown containing stable declaration IDs, the natural-language statements and proofs, variables, assumptions, relevant definitions, and unresolved questions. Distinguish source content from the agent's interpretation. Mark missing proofs or context explicitly. This Markdown is the intermediate representation; keep its schema small.

Scaffold

Read the Markdown and inspect the target project's existing definitions and relevant Mathlib declarations before choosing representations. Generate Lean files in the project's configured module layout with imports, namespaces, explicit theorem statements, and by sorry proof bodies.

Include the natural-language theorem and proof in Lean comments, together with the source reference, declaration ID, and an estimated difficulty with a short reason. Mark difficulty as an estimate. Missing statement terms or definitions must be reported as blockers; only theorem proof bodies may be stubbed.

Verify

Run actual Lean elaboration through a helper script. Separately run two read-only reviewers concurrently when supported by the installed Claude Code version:

A semantic reviewer compares the Lean declaration with the original source and annotation, checking hypotheses, quantifiers, definitions, and mathematical meaning.
A reuse reviewer searches the codebase, Mathlib, and other already available Lean libraries. Check candidate applications where feasible and explain whether a small adaptation or new proof is needed.

Have the command coordinator combine the reports. Keep elaboration, semantic review, and recommended action separate. Use actions such as reuse, prove, repair_statement, and defer, with concrete evidence. A failed search does not by itself establish high priority. Preserve selected source records even when their formalization can reuse existing results.

Both reviewers must inspect the same declaration revision. Reports should distinguish model review from human approval and formal proof checking.

Prove

Use the reviewed statement, informal proof, relevant project files, and reuse findings. Fill proof bodies while preserving the mathematical target and relevant definitions. Return necessary statement changes for renewed review. Allow supporting lemmas, with their proof obligations tracked explicitly.

Use a configurable attempt budget and record Lean feedback. After a candidate proof succeeds, check the target's transitive axiom dependencies. Reject sorryAx and axioms outside a documented allowlist, defaulting to Lean's standard logical axioms. A proof that relies on an unfinished lemma must remain unfinished.

Packaging and operation

Inspect the repository and current official Claude Code plugin documentation first. Reuse existing pipeline components and preserve the project's pinned Lean/Mathlib environment.

Package the slash-command skills, reusable agent definitions, helper scripts, and templates using the supported plugin layout. Provide a valid manifest, a working persistent installation route, and exact installation, activation, update, and usage instructions. Test local development loading separately from persistent installation.

Keep orchestration in the command coordinator and use explicit delegation to the appropriate agents. Inherit the session's model by default. Give each command an input contract, output locations, and failure behavior.

Store generated Markdown, Lean files, and reports in the target project, outside the installed plugin directory. Keep a small file-based manifest for declaration IDs, artifact paths, revisions, and status. Preserve human edits and completed proofs on reruns. Recheck affected results when their inputs change. Give each declaration one writer at a time.