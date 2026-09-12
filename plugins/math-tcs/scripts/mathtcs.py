#!/usr/bin/env python3
"""math-tcs deterministic helper CLI (stdlib only). See `mathtcs.py help`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mathtcs.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
