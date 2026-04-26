---
name: skill-creator
description: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Claude's capabilities with specialized knowledge, workflows, or tool integrations.
license: Complete terms in LICENSE.txt
---

# Skill Creator

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Claude's capabilities by providing
specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
domains or tasks—they transform Claude from a general-purpose agent into a specialized agent
equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. Specialized workflows - Multi-step procedures for specific domains
2. Tool integrations - Instructions for working with specific file formats or APIs
3. Domain expertise - Company-specific knowledge, schemas, business logic
4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks

### Anatomy of a Skill

Every skill consists of a required SKILL.md file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation intended to be loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

#### SKILL.md (required)

**Metadata Quality:** The `name` and `description` in YAML frontmatter determine when Claude will use the skill. Be specific about what the skill does and when to use it. Use the third-person (e.g. "This skill should be used when..." instead of "Use this skill when...").

#### Bundled Resources (optional)

##### Scripts (`scripts/`)

Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments

##### References (`references/`)

Documentation and reference material intended to be loaded as needed into context to inform Claude's process and thinking.

- **When to include**: For documentation that Claude should reference while working
- **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
- **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
- **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.

##### Assets (`assets/`)

Files not intended to be loaded into context, but rather used within the output Claude produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
- **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
- **Benefits**: Separates output resources from documentation, enables Claude to use files without loading them into context

### Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

1. **Metadata (name + description)** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<5k words)
3. **Bundled resources** - As needed by Claude (Unlimited*)

*Unlimited because scripts can be executed without reading into context window.

## phds Context: from knowledge_db to skills

This document supports two skill-authoring contexts:

1. **Generic** — user-driven, examples-first. The Anthropic flow in `## Skill Creation Process` below. Use when a user is hand-specifying a skill from scratch.
2. **phds context** — pipeline-driven. The input is a distilled pack already sitting in `phds/knowledge_db/`, produced upstream by `distill/`. Use when the organizer is converting curated knowledge into a capability multiplier.

**When operating in phds context, this section's rules take precedence over the generic flow.** The generic Steps 1–6 still apply, but with the adaptations below.

### Inputs

The organizer reads from `phds/knowledge_db/`:

- `individuals/<surname>.md` — heuristic-mind packs distilled from a single mathematician.
- `batches/<vertical>-<window>.md` — domain-playbook packs distilled from a domain slice.

These packs already conform to `distill/reference/extraction-framework.md` — every `INCLUDE` rule has been gate-tested for recurrence, predictive power, and exclusivity. The organizer does not re-litigate those gates; it applies a different one.

### The capability-multiplier test

A pack-rule earns a skill slot only if it passes:

> If a proving-agent reads this skill before tackling an in-scope problem, would it behave measurably differently — pick a different first move, reach for a different tool, write the proof in a different shape — than a vanilla Claude would?

If the honest answer is "Claude already does this" or "this is just a definition," the rule does **not** become a skill. It stays in `knowledge_db/` as the phds' working memory and is read on demand.

This test is **stricter** than the framework's three gates. The framework asks "is this a real pattern in the source?" The capability-multiplier test asks "does Claude need this *added*?" Many real patterns don't need to be added — Claude already has them.

### Skill output categories

Capability-multiplier skills land under `skills/` in one of:

- `skills/styles/` — written-style packs that shape Claude's prose (e.g. `concise_math_style.md`).
- `skills/techniques/` — technique patterns that shape route choice (e.g. "invariant-first for algorithm proofs").
- `skills/attacks/` — attack heuristics that shape the first move (e.g. "for monotone problems, try extremal before constructive").

Categories may grow as needs emerge; do not pre-create empty ones.

### Sorting responsibility

As packs accumulate in `knowledge_db/`, the organizer also **sorts cross-cutting patterns**. If three different individuals' packs all contain a rule about "extremal-first for combinatorics problems," that rule is more skill-worthy than a rule appearing in a single pack — even if every individual rule passed the framework's gates separately. **Cross-pack recurrence is the strongest signal.**

When the organizer notices cross-pack recurrence, it consolidates into a single skill that cites all source packs, rather than authoring parallel near-duplicate skills per source.

### Adapting Steps 1–6 to phds context

- **Step 1 (concrete examples)** — *replace* user-driven examples with the source pack(s). The pack *is* the example library.
- **Step 2 (planning reusable contents)** — examine each `INCLUDE` rule for capability-multiplier value and **named consumer fit** (which proving-agent uses it). A rule with no consumer is not a skill.
- **Steps 3–5 (init, edit, package)** — unchanged.
- **Step 6 (iterate)** — when the source pack changes, re-run the capability-multiplier test on the affected skill; do not silently regenerate.

## Skill Creation Process

To create a skill, follow the "Skill Creation Process" in order, skipping steps only if there is a clear reason why they are not applicable.

### Step 1: Understanding the Skill with Concrete Examples

Skip this step only when the skill's usage patterns are already clearly understood. It remains valuable even when working with an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from either direct user examples or generated examples that are validated with user feedback.

For example, when building an image-editor skill, relevant questions include:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "I can imagine users asking for things like 'Remove the red-eye from this image' or 'Rotate this image'. Are there other ways you imagine this skill being used?"
- "What would a user say that should trigger this skill?"

To avoid overwhelming users, avoid asking too many questions in a single message. Start with the most important questions and follow up as needed for better effectiveness.

Conclude this step when there is a clear sense of the functionality the skill should support.

### Step 2: Planning the Reusable Skill Contents

To turn concrete examples into an effective skill, analyze each example by:

1. Considering how to execute on the example from scratch
2. Identifying what scripts, references, and assets would be helpful when executing these workflows repeatedly

Example: When building a `pdf-editor` skill to handle queries like "Help me rotate this PDF," the analysis shows:

1. Rotating a PDF requires re-writing the same code each time
2. A `scripts/rotate_pdf.py` script would be helpful to store in the skill

Example: When designing a `frontend-webapp-builder` skill for queries like "Build me a todo app" or "Build me a dashboard to track my steps," the analysis shows:

1. Writing a frontend webapp requires the same boilerplate HTML/React each time
2. An `assets/hello-world/` template containing the boilerplate HTML/React project files would be helpful to store in the skill

Example: When building a `big-query` skill to handle queries like "How many users have logged in today?" the analysis shows:

1. Querying BigQuery requires re-discovering the table schemas and relationships each time
2. A `references/schema.md` file documenting the table schemas would be helpful to store in the skill

To establish the skill's contents, analyze each concrete example to create a list of the reusable resources to include: scripts, references, and assets.

### Step 3: Initializing the Skill

At this point, it is time to actually create the skill.

Skip this step only if the skill being developed already exists, and iteration or packaging is needed. In this case, continue to the next step.

When creating a new skill from scratch, always run the `init_skill.py` script. The script conveniently generates a new template skill directory that automatically includes everything a skill requires, making the skill creation process much more efficient and reliable.

Usage:

```bash
scripts/init_skill.py <skill-name> --path <output-directory>
```

The script:

- Creates the skill directory at the specified path
- Generates a SKILL.md template with proper frontmatter and TODO placeholders
- Creates example resource directories: `scripts/`, `references/`, and `assets/`
- Adds example files in each directory that can be customized or deleted

After initialization, customize or remove the generated SKILL.md and example files as needed.

### Step 4: Edit the Skill

When editing the (newly-generated or existing) skill, remember that the skill is being created for another instance of Claude to use. Focus on including information that would be beneficial and non-obvious to Claude. Consider what procedural knowledge, domain-specific details, or reusable assets would help another Claude instance execute these tasks more effectively.

#### Start with Reusable Skill Contents

To begin implementation, start with the reusable resources identified above: `scripts/`, `references/`, and `assets/` files. Note that this step may require user input. For example, when implementing a `brand-guidelines` skill, the user may need to provide brand assets or templates to store in `assets/`, or documentation to store in `references/`.

Also, delete any example files and directories not needed for the skill. The initialization script creates example files in `scripts/`, `references/`, and `assets/` to demonstrate structure, but most skills won't need all of them.

#### Update SKILL.md

**Writing Style:** Write the entire skill using **imperative/infinitive form** (verb-first instructions), not second person. Use objective, instructional language (e.g., "To accomplish X, do Y" rather than "You should do X" or "If you need to do X"). This maintains consistency and clarity for AI consumption.

To complete SKILL.md, answer the following questions:

1. What is the purpose of the skill, in a few sentences?
2. When should the skill be used?
3. In practice, how should Claude use the skill? All reusable skill contents developed above should be referenced so that Claude knows how to use them.

### Step 5: Packaging a Skill

Once the skill is ready, it should be packaged into a distributable zip file that gets shared with the user. The packaging process automatically validates the skill first to ensure it meets all requirements:

```bash
scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory specification:

```bash
scripts/package_skill.py <path/to/skill-folder> ./dist
```

The packaging script will:

1. **Validate** the skill automatically, checking:
   - YAML frontmatter format and required fields
   - Skill naming conventions and directory structure
   - Description completeness and quality
   - File organization and resource references

2. **Package** the skill if validation passes, creating a zip file named after the skill (e.g., `my-skill.zip`) that includes all files and maintains the proper directory structure for distribution.

If validation fails, the script will report the errors and exit without creating a package. Fix any validation errors and run the packaging command again.

### Step 6: Iterate

After testing the skill, users may request improvements. Often this happens right after using the skill, with fresh context of how the skill performed.

**Iteration workflow:**
1. Use the skill on real tasks
2. Notice struggles or inefficiencies
3. Identify how SKILL.md or bundled resources should be updated
4. Implement changes and test again

## Evaluation

These checks apply to skills produced in the **phds context** — capability multipliers landing under `skills/`. Skills produced via the generic flow (user-driven, no knowledge_db source) are evaluated by the standard skill-creator rules above.

A skill passes evaluation if all hold:

- **Procedural shape** — the body instructs Claude what to *do*, not what is *true*. No definitions, no theorem statements, no glossary entries. Verbs over nouns.
- **Capability-multiplier** — answers yes to: would loading this skill change a vanilla Claude's behavior on an in-scope problem? "Already in weights" is a fail.
- **Named consumer** — the skill explicitly names which proving-agent(s) read it (explorer, prover, reviewer, formatter) and what task pattern triggers loading. Skills with no named consumer are not skills.
- **Source-cited** — references the `phds/knowledge_db/` pack(s) the skill was distilled from. Skills without a knowledge_db source are flagged for review.
- **Scope-tight** — one task pattern per skill. Don't bundle "linear algebra problem-solving" into one skill; split into specific patterns ("spectral-first for symmetric matrices").
- **No fact restatement** — skills do not restate textbook facts. If a skill needs a definition mid-procedure, the proving-agent already has it from training.
- **Imperative register** — write in third-person or imperative form, not second-person.

## Verification

Mechanical checks to run on each generated skill:

1. **Path** — lives at `skills/<category>/<skill-name>/SKILL.md` (full package) or `skills/<category>/<skill-name>.md` (single-file). `<category>` is one of `styles`, `techniques`, `attacks`, or a category authored by the regulator.
2. **Frontmatter / heading** — full-package SKILL.md has valid YAML frontmatter with `name` and `description`. Single-file skills have a top-level `# <name>` heading on line 1.
3. **Source citation** — body contains a `Source:` line referencing a pack path under `phds/knowledge_db/` and ideally the specific `INCLUDE` rule the skill operationalizes:
   ```bash
   grep -E "^Source:.*phds/knowledge_db/" <skill-file>
   ```
   should return a match.
4. **Consumer named** — body names at least one proving-agent role:
   ```bash
   grep -nE "\b(explorer|prover|reviewer|formatter)\b" <skill-file>
   ```
   should return a match.
5. **No second-person** — imperative-form check:
   ```bash
   grep -nE "\b(you|your)\b" <skill-file>
   ```
   should return no matches.
6. **Discoverable** — the skill is findable by its task-pattern keyword:
   ```bash
   grep -rl "<task-pattern-keyword>" skills/
   ```
   should return this file.

If any check fails, **do not patch the skill to mechanically satisfy the rule**. The underlying issue is usually that the rule didn't pass the capability-multiplier test in the first place; route the skill back through evaluation, or reject. The regulator (`phds/skill-regulator/`) is the gate.