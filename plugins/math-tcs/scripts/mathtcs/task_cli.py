"""Argument parsing for the ordinary-file workflow, separate from legacy stages."""
import argparse
import json
from pathlib import Path

from . import harness, plain, project
from .util import MathTcsError, read_json


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise MathTcsError(message, code=2)


def main(argv):
    parser = Parser(prog="mathtcs.py " + argv[0])
    if argv[0] == "check-file":
        parser.add_argument("file", type=Path)
        parser.add_argument("--decl", action="append", required=True)
        parser.add_argument("--root", type=Path, default=Path.cwd())
        parser.add_argument("--timeout", type=float, default=120)
        args = parser.parse_args(argv[1:])
        root = project.find_root(args.root)
        if root is None:
            raise MathTcsError("no Lean project found", code=2)
        result = plain.check_file(root, args.file.resolve(), args.decl, args.timeout)
        print(json.dumps(result))
        return 0 if result["ok"] else 1
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for name in ("begin", "propose", "review", "attempt", "apply", "status", "abort"):
        p = sub.add_parser(name)
        p.add_argument("--root", type=Path, default=Path.cwd())
        if name != "begin":
            p.add_argument("id")
        if name == "begin":
            p.add_argument("--file", type=Path, required=True)
            p.add_argument("--source", type=Path, required=True)
            p.add_argument("--decl", required=True)
            p.add_argument("--start", type=int, required=True)
            p.add_argument("--end", type=int, required=True)
            p.add_argument("--mode", choices=("formalize", "simplify"), default="formalize")
            p.add_argument("--budget", type=int, default=4)
        if name in {"propose", "review", "attempt"}:
            p.add_argument("--input", type=Path, required=True)
        if name in {"attempt", "apply"}:
            p.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv[1:])
    root = project.find_root(args.root)
    if root is None:
        raise MathTcsError("no Lean project found", code=2)
    if args.command == "begin":
        result = harness.begin(root, args.file, args.source, args.decl, start=args.start,
                               end=args.end, mode=args.mode, budget=args.budget)
    elif args.command in {"propose", "review", "attempt"}:
        content = read_json(args.input) if args.command == "review" else args.input.read_text(encoding="utf-8")
        extra = {"timeout": args.timeout} if args.command == "attempt" else {}
        result = getattr(harness, args.command)(root, args.id, content, **extra)
    else:
        extra = {"timeout": args.timeout} if args.command == "apply" else {}
        result = getattr(harness, args.command)(root, args.id, **extra)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] in {"unfinished", "needs_statement_review"} else 0
