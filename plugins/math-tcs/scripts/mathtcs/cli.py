"""Public CLI: ordinary-file tasks only; never dispatch to the retired stage pipeline."""
import json

from . import project, task_cli
from .util import MathTcsError

USAGE = """mathtcs.py <command> [args]
  check-file FILE --decl Qualified.name [--root DIR] [--timeout SECONDS]
  task begin|propose|review|attempt|apply|status|abort --help
  project detect [--root DIR]

Use the formalize, review, or simplify skill in your Lean project.
The retired batch-stage commands are not supported by this entry point."""


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(USAGE)
        return 0
    try:
        if argv[0] in {"task", "check-file"}:
            return task_cli.main(argv)
        if argv[:2] == ["project", "detect"]:
            parser = task_cli.Parser(prog="mathtcs.py project detect")
            parser.add_argument("--root")
            args = parser.parse_args(argv[2:])
            print(json.dumps(project.detect(args.root)))
            return 0
        raise MathTcsError(
            f"unknown command {' '.join(argv[:2])!r}; use task or check-file. "
            "The old stage pipeline has been retired from this entry point.", code=2)
    except MathTcsError as exc:
        print(json.dumps({"error": str(exc), "code": exc.code,
                          **({"detail": exc.detail} if exc.detail else {})}))
        return exc.code
    except Exception as exc:
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "code": 2}))
        return 2
