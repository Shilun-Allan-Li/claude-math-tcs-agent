# /review-dissertation

You are the **Dissertation Review Orchestrator**. Your job is to thoroughly review `UC_Berkeley_Dissertation.pdf` using a team of specialized agents and produce a comprehensive report in the `check/` directory.

---

## Step 1 — Read & Summarize the Dissertation

Read `UC_Berkeley_Dissertation.pdf` using the Read tool. Extract:
- Title, author, committee, department, year
- Abstract (verbatim or close paraphrase)
- Chapter titles and one-sentence summaries
- Core thesis claim(s)
- Primary methods used (mathematical, statistical, experimental, etc.)
- Key results/contributions claimed

Print a concise summary to the user (≤400 words), then proceed immediately to Step 2.

---

## Step 2 — Spawn Review Agents (run in parallel batches)

Use the **Agent tool** to spawn all agents below. Launch them in parallel — include as many as possible in each parallel batch. Each agent must:
1. Read `UC_Berkeley_Dissertation.pdf` using the Read tool (read the whole document or as many pages as needed)
2. Perform its specific check
3. Write a structured Markdown report to its assigned output file using the Write tool
4. Return a one-line status to you

All output files go in the `check/` directory relative to the working directory `/Users/allanli/Documents/Berkeley/Trivedi_Dissertation/`.

### Agent Definitions

**Agent 1 — Math Errors Checker**
- Output: `check/math_errors.md`
- Task: Read the full dissertation. Identify every mathematical error: incorrect derivations, wrong equation transformations, algebraic mistakes, incorrect use of calculus (derivatives, integrals), wrong matrix/linear algebra operations, incorrect probability calculations. For each issue: quote the erroneous expression, give the correct form, and cite the page/equation number. Rate overall severity (Critical / Major / Minor). Write a structured report with sections: Summary, Detailed Findings (table: Location | Error | Correct Form | Severity), Overall Assessment.

**Agent 2 — Math Parameters Checker**
- Output: `check/math_parameters.md`
- Task: Read the full dissertation. Check every variable, parameter, and symbol: Is each defined before first use? Is it defined consistently throughout? Are there symbol collisions (same symbol used for two things)? Missing definitions? Parameters that appear in results but were never defined? Are subscripts/superscripts used consistently? Write a structured report: Summary, Symbol Table (Symbol | First Defined | Definition | Issues Found), Detailed Findings, Recommendations.

**Agent 3 — Math Notation Checker**
- Output: `check/math_notation.md`
- Task: Read the full dissertation. Check mathematical notation for: non-standard usage, inconsistent notation for the same concept across chapters, notation that contradicts the field's conventions, missing/ambiguous notation for sets/functions/spaces. Write a structured report: Summary, Notation Inventory, Inconsistencies Found, Non-Standard Usages, Recommendations.

**Agent 4 — Numerical Computations Checker**
- Output: `check/numerical_computations.md`
- Task: Read the full dissertation. Verify all numerical results, bounds, constants, and computations: Are arithmetic results correct? Do stated bounds hold? Are reported numerical values consistent across the document? Are units consistent? Do example computations produce the stated output? Rate each issue. Write a structured report: Summary, Verified Computations, Errors Found (Location | Stated Value | Correct Value | Notes), Overall Assessment.

**Agent 5 — Statistical Methods Checker**
- Output: `check/statistical_methods.md`
- Task: Read the full dissertation. Evaluate every statistical method used: Are statistical tests appropriate for the data type and distribution? Are assumptions of tests stated and justified? Are p-values interpreted correctly? Are confidence intervals computed correctly? Is sample size adequate (power analysis)? Are effect sizes reported? Are multiple-comparison corrections applied where needed? Write a structured report: Summary, Statistical Methods Inventory, Issues Found, Recommendations.

**Agent 6 — Logic & Proof Checker**
- Output: `check/logic_proofs.md`
- Task: Read the full dissertation. For every formal proof and logical argument: Identify invalid inference steps, missing intermediate steps, circular reasoning, false dichotomies, unproven lemmas used as facts, incorrect application of theorems, quantifier errors (∀ vs ∃ confusion), non sequiturs. Write a structured report: Summary, Proof-by-Proof Analysis (Theorem | Location | Assessment | Issues), Critical Gaps, Recommendations.

**Agent 7 — Theorem Statements Checker**
- Output: `check/theorem_statements.md`
- Task: Read the full dissertation. Evaluate every theorem, lemma, corollary, and proposition: Is the statement precise and unambiguous? Are all necessary conditions/hypotheses stated? Is the result actually proved in the text (vs. just claimed)? Are theorems numbered consistently? Are there theorems that contradict known results in the field? Write a structured report: Summary, Theorem Inventory (Number | Statement Summary | Conditions Complete? | Proved? | Issues), Recommendations.

**Agent 8 — Assumptions Checker**
- Output: `check/assumptions.md`
- Task: Read the full dissertation. Identify all assumptions — stated and unstated: Are assumptions clearly labeled? Are they justified? Are any assumptions hidden in proofs or derivations? Are there assumptions that may be violated in practice? Are assumptions consistent across chapters? Does the conclusion depend on assumptions that are only weakly motivated? Write a structured report: Summary, Assumption Registry (Assumption | Location | Justified? | Potential Violations), Hidden Assumptions Found, Impact Assessment.

**Agent 9 — General Correctness Checker**
- Output: `check/general_correctness.md`
- Task: Read the full dissertation. Evaluate general technical and factual correctness: Are claims about the state of the field accurate? Are related works described correctly? Are technical definitions accurate? Are there factually incorrect statements? Are results accurately represented? Does the paper claim credit for previously known results? Write a structured report: Summary, Factual Issues Found (Claim | Location | Problem | Correction), Misrepresentations, Overall Correctness Assessment.

**Agent 10 — Structure & Flow Checker**
- Output: `check/structure_flow.md`
- Task: Read the full dissertation. Evaluate the overall structure and argumentative flow: Is the chapter order logical? Does each chapter build on the previous? Are there gaps in the argument? Is the introduction's promise fulfilled by the conclusion? Are there orphaned sections that don't connect to the main argument? Is the level of detail appropriate throughout? Are transitions between chapters/sections smooth? Write a structured report: Summary, Chapter-by-Chapter Flow Analysis, Structural Gaps, Disconnected Sections, Recommendations.

**Agent 11 — Abstract & Conclusion Consistency Checker**
- Output: `check/abstract_conclusion.md`
- Task: Read the full dissertation, focusing on the abstract, introduction, and conclusion. Check for consistency: Does the abstract accurately reflect what the dissertation actually delivers? Does the introduction's research question get answered in the conclusion? Are all contributions listed in the abstract substantiated in the body? Do the conclusions follow from the results? Are limitations acknowledged? Are future work claims reasonable? Write a structured report: Summary, Abstract vs. Body Comparison (Claim | Substantiated? | Notes), Conclusion Validity, Unmet Promises, Overstated Claims.

**Agent 12 — Figures & Tables Checker**
- Output: `check/figures_tables.md`
- Task: Read the full dissertation. Evaluate all figures, tables, plots, and diagrams: Are all figures/tables numbered sequentially and consistently? Does each have a descriptive caption? Is every figure/table referenced in the text? Do the captions match what is shown? Are axis labels, units, and legends present in plots? Are tables formatted correctly? Are there figures/tables that are never discussed? Write a structured report: Summary, Figure/Table Inventory (Number | Caption Present? | Referenced in Text? | Issues), Problems Found, Recommendations.

**Agent 13 — Terminology Consistency Checker**
- Output: `check/terminology_consistency.md`
- Task: Read the full dissertation. Track key technical terms throughout: Are terms defined and then used consistently? Does any term change meaning between chapters? Are synonyms used interchangeably without noting they are the same? Are technical terms from the field used with their standard meanings? Is jargon explained for a general academic audience? Write a structured report: Summary, Term Glossary (Term | First Defined | Variations Found | Consistency Issues), Definition Drift Instances, Recommendations.

**Agent 14 — Citations & References Checker**
- Output: `check/citations_references.md`
- Task: Read the full dissertation. Check citations and the reference list: Are all in-text citations present in the reference list? Are there references in the bibliography that are never cited? Are citation formats consistent (style, capitalization, journal abbreviations)? Are any important foundational works missing? Are citations used appropriately (primary vs. secondary)? Are self-citations excessive or appropriate? Write a structured report: Summary, Citation Issues Found, Bibliography Anomalies, Missing Key References, Format Problems, Recommendations.

**Agent 15 — Spelling Checker**
- Output: `check/spelling.md`
- Task: Read the full dissertation. Identify all spelling errors, typos, and misspellings: common English words misspelled, technical/mathematical terms misspelled, author names in citations misspelled, inconsistent British vs. American spelling, repeated words (e.g., "the the"), missing words, words run together. Write a structured report: Summary, Error List (Location | Wrong | Correct | Type), Patterns Observed, Total Error Count.

**Agent 16 — Grammar & Style Checker**
- Output: `check/grammar.md`
- Task: Read the full dissertation. Identify grammar, punctuation, and academic style issues: subject-verb agreement errors, incorrect tense (especially mixed past/present in results sections), misuse of articles (a/an/the), dangling modifiers, passive voice overuse, sentence fragments, run-on sentences, incorrect comma use, semicolon misuse, incorrect use of "which" vs. "that", academic register violations (too casual/colloquial), redundant phrases. Write a structured report: Summary, Error List (Location | Issue | Type | Corrected Form), Style Patterns, Severity Assessment.

---

## Step 3 — Assemble Final Report

After ALL agents have completed, spawn one final **Assembly Agent**:
- Output: `check/SUMMARY.md`
- Task: Read ALL files in the `check/` directory: math_errors.md, math_parameters.md, math_notation.md, numerical_computations.md, statistical_methods.md, logic_proofs.md, theorem_statements.md, assumptions.md, general_correctness.md, structure_flow.md, abstract_conclusion.md, figures_tables.md, terminology_consistency.md, citations_references.md, spelling.md, grammar.md. Synthesize them into a single comprehensive report `check/SUMMARY.md` with the following structure:
  1. **Executive Summary** — 2–3 paragraph overall assessment of the dissertation quality
  2. **Critical Issues** — Issues that must be addressed before the dissertation can be defended (from any agent)
  3. **Major Issues** — Significant issues that materially weaken the work
  4. **Minor Issues** — Small corrections and improvements
  5. **Strengths** — What the dissertation does well
  6. **Agent Reports Index** — Table linking to each agent's report file and its top finding
  7. **Recommended Action Items** — Prioritized list of changes the author should make

---

## Step 4 — Report to User

Once complete, print to the user:
- Confirmation that all 16 check files and the SUMMARY.md have been written
- The number of Critical / Major / Minor issues found in total
- The top 5 most important issues from `check/SUMMARY.md`
