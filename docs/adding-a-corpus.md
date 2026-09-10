# Adding a corpus

Nothing in `src/` should need to change.
`tests/integration/test_corpus_agnostic.py` is the acceptance test for that claim: it
builds a corpus in a temporary directory, mounts it from outside the repository, and
asserts that identity, extraction and the graph all work on it — and that no module under
`src/pipeline/` names a corpus or uses one domain's vocabulary.

There are two places a corpus config can live:

| | where | for |
|---|---|---|
| **in the tree** | `corpora/<name>.json` | the committed demo; a corpus you do not mind having in the repo (git-ignored except the demo) |
| **outside the tree** | any directory on `PIPELINE_CORPORA_PATH` | private, copyrighted or third-party corpora — nothing about them enters the repository |

## 1. Get the source as Markdown

The pipeline ingests **Markdown**. How you get there is your choice — PDF extraction is a
separate, optional stage that exists only to produce it.

Page provenance travels in `<!-- p.NNN -->` markers. Keep them if you have them; the
`printed_page_offset` field converts them to the numbers the source prints.

If you are starting from a PDF:

```bash
pipeline ingest-pdf book.pdf --out data/raw --first 9 --last 270 --plan   # costs nothing
```

That needs poppler (`pdfinfo`, `pdfseparate`, `pdftoppm`). The renderer is injectable, so
a pure-Python alternative works too — `PageRenderer` is a two-method protocol.

## 2. Write a corpus config

`corpora/<name>.json`, or `<any-mounted-dir>/<name>.json`:

```json
{
  "corpus": "your-book",
  "slug": "yb",
  "title": "…",
  "authors": ["…"],
  "source_type": "book",
  "divisions": [
    {"number": "1", "type": "chapter", "title": "…",
     "markdown": "sources/your-book/01.md",
     "pdf_page_start": 9, "pdf_page_end": 32, "printed_page_offset": 8}
  ]
}
```

Relative paths inside a config resolve against **the config's own directory** first, then
against the repository root. An externally mounted corpus is therefore self-contained: keep
`sources/` next to the JSON and it travels as one directory.

| field | default | purpose |
|---|---|---|
| `slug` | — | prefix of every declaration id, used verbatim; keep it short |
| `source_type` | `"book"` | `"notes"`, `"paper"`, … display only |
| `divisions[].type` | `"chapter"` | the source's own word — `"unit"`, `"lecture"`, `"part"`. Display only; no pipeline logic branches on it |
| `printed_page_offset` | — | converts PDF page markers to printed page numbers |

`chapters` is accepted as a synonym for `divisions`.

## 3. Run it

With more than one corpus configured there is no default — guessing which source you meant
is worse than asking:

```bash
pipeline --corpus your-book ingest --all
export PIPELINE_CORPUS=your-book        # or set it once
```

Artifacts go to `--data-dir` (default `data/`, git-ignored). Point it outside the repo if
you prefer:

```bash
pipeline --corpus your-book --data-dir ~/research/pipeline-data ingest --all
```

## 4. Keep it out of the repository

Real corpora are usually copyrighted. The safest arrangement keeps the corpus, its sources
and its artifacts all outside the tree, so there is nothing to accidentally commit:

```bash
~/research/my-corpus/
  my-corpus.json          # "markdown": "sources/01.md"
  sources/01.md

export PIPELINE_CORPORA_PATH=~/research/my-corpus
pipeline --corpus my-corpus --data-dir ~/research/my-data ingest --all
```

`PIPELINE_CORPORA_PATH` takes several directories separated by `:`. `corpora/` is always
searched first, so a mounted config can never shadow one in the repository.

If you would rather keep the config in the tree, `.gitignore` excludes `sources/`,
`corpora/*` (except the demo) and `data/`.

## Identity, and why it constrains the source

Declaration ids are derived only from what the source fixes:

```
<slug>-ch<division>-<kind>-<label>              yb-ch3-thm-3.2
<slug>-ch<division>-<kind>-<section>-<ordinal>  yb-ch3-def-3.1-1   (unlabelled)
```

Never from model wording, generated Lean names, timestamps, or content hashes. This is why
the extractor cares about label shapes: `Theorem 3.2`, `3.1.2`, `1.2.8(b)`, `8.5.2 (a)*`
must all normalise stably, because the label is the join key a human uses.

If your source numbers things in a shape the extractor does not recognise, that is a real
gap — extend `pipeline/stages/source_items.py` and add a case to
`tests/unit/test_ids.py`. It is the one place a new corpus legitimately touches engine code.

## Checking your corpus is wired correctly

```bash
pipeline corpus list                             # is it discovered at all?
pipeline corpus show your-book
pipeline --corpus your-book ingest 1
pipeline --corpus your-book corpus declarations
pipeline --corpus your-book graph unresolved     # citations resolving to nothing
```

A high unresolved count usually means the source cites divisions you have not ingested
yet, which is expected and reported rather than hidden.
