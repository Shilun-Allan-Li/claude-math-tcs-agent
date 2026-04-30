# /format-paper

Convert a mathematical paper (PDF / `.tar(.gz|.bz2)` / `.zip` / `.tex`) into `papers/<name>.md`.

## Usage
- `/format-paper path/to/paper.pdf`
- `/format-paper path/to/arxiv_source.tar.gz`
- `/format-paper path/to/paper.tex`

## Instructions

1. Run the extractor:
   ```
   python3 -m claude_prover.lib.cli paper-extract "<path>"
   ```
   It prints a JSON manifest with the workdir, main `.tex` file (or extracted PDF text path), and the final output path. If the command fails, surface the error and stop.

2. Dispatch the `proof-formatter` agent with the manifest:

   > "Convert the extracted material into a clean, agent-readable markdown file. If `main_tex` is set, read it and follow `\input{...}` / `\include{...}` across `tex_files`. If `raw_text_path` is set, clean that instead. Write the final markdown to `output_md`."

3. Print the output path and any extraction warnings.

$ARGUMENTS
