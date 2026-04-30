"""distill_mathematicians CLI — dispatcher for the regulated-search collectors.

Invoked as: `python -m distill_mathematicians.lib.cli <verb> [args...]`

Verbs:
  arxiv     Build an arXiv manifest for a batch-pack run.
  github    Build a GitHub-curator manifest for a batch-pack run.
  corpus    Build a corpus-collector manifest for an individual-pack run.

Each verb writes a YAML manifest matching the schema in the corresponding
agent spec under distill_mathematicians/agents/.
"""

from __future__ import annotations

import argparse
import sys

from . import arxiv as _arxiv
from . import corpus as _corpus
from . import github as _github


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="distill-mathematicians",
        description="Regulated-search collectors for the distillation pipeline.",
    )
    sub = parser.add_subparsers(dest="verb")
    sub.required = True

    _arxiv.add_argparser(sub)
    _github.add_argparser(sub)
    _corpus.add_argparser(sub)

    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
