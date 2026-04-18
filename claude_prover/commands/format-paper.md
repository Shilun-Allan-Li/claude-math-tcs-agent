# /format-paper

Convert a mathematical paper (PDF / `.tar(.gz|.bz2)` / `.zip` / `.tex`) into `papers/<name>.md`.

## Usage
- `/format-paper path/to/paper.pdf`
- `/format-paper path/to/arxiv_source.tar.gz`
- `/format-paper path/to/paper.tex`

## Instructions

1. Read the file path from the argument.

2. Run the extractor. It prints a JSON manifest with the temp workdir, main `.tex` file (or extracted PDF text path), and the final output path:

   ```
   python3 -m claude_prover.lib.cli paper-extract "<path>"
   ```

   If this fails (unsupported format, missing `pdftotext`/`pandoc`, etc.), surface the error and stop.

3. Delegate to the `proof-formatter` agent. Pass it the manifest and instruct:

   > "Convert the extracted material into a clean, agent-readable markdown file. If `main_tex` is set, read it and follow `\input{...}` / `\include{...}` across `tex_files`. If `raw_text_path` is set, clean that instead. Write the final markdown to `output_md`. Follow the cleaning rules in your agent spec."

4. After the agent returns, report:
   - output path,
   - how many sections / theorems / proofs it found,
   - any extraction warnings.

$ARGUMENTS
