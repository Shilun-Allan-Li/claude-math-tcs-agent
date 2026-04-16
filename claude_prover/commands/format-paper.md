# /format-paper

Convert a mathematical paper from PDF, LaTeX archive (.tar, .tar.gz, .zip), or .tex file into a clean, agent-readable markdown file saved to `papers/`.

## Usage
- `/format-paper path/to/paper.pdf`
- `/format-paper path/to/arxiv_source.tar.gz`
- `/format-paper path/to/paper.tex`
- `/format-paper path/to/paper.zip`

## Instructions

Read the file path from the user's argument after this command.

---

1. Check that the file exists using Bash: `ls -la "[path]"`
   - If not found: tell the user the file was not found and ask for the correct path.

2. Determine the output filename:
   - Strip the directory path and extension from the input filename
   - Sanitize to lowercase with hyphens: e.g., `MyPaper_2024.pdf` → `my-paper-2024`
   - Output will be saved to `papers/<sanitized_name>.md`
   - Create the `papers/` directory if needed: `mkdir -p papers`

3. Use the `proof-formatter` agent to convert the file. Pass it:
   "Convert the file at [path] to a clean, agent-readable markdown file. Save the output to papers/[sanitized_name].md. The input format is [pdf/tar.gz/tex/zip]."

---

After formatting completes, report:
- The output file location
- A brief summary (sections found, theorems found, any extraction issues)
- Suggested next step: "You can now reference this paper in `/prove` or `/explore` by reading `papers/[name].md`."

$ARGUMENTS
