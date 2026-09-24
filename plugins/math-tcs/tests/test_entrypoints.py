"""Public command discovery and routing must not activate the retired stages."""
import json
import subprocess
import sys

import pytest

from mathtcs import cli, task_cli


def test_only_current_skills_and_workers_are_exposed(plugin_root):
    assert {p.parent.name for p in (plugin_root / "skills").glob("*/SKILL.md")} == {
        "formalize", "review", "simplify"}
    assert {p.stem for p in (plugin_root / "agents").glob("*.md")} == {
        "lean-formalizer", "lean-semantic-reviewer", "lean-proof-worker"}
    manifest = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text())
    assert (plugin_root / manifest["skills"]).resolve() == (plugin_root / "skills").resolve()
    assert not list((plugin_root / "commands").glob("*.md"))


@pytest.mark.parametrize("argv", [["task", "begin"], ["task", "apply"],
                                  ["check-file", "Main.lean", "--decl", "t"]])
def test_public_cli_dispatches_to_current_parser(monkeypatch, argv):
    calls = []
    def current(args):
        calls.append(args)
        return 1
    monkeypatch.setattr(task_cli, "main", current)
    assert cli.main(argv) == 1
    assert calls == [argv]


@pytest.mark.parametrize("argv", [
    ["run"], ["translate"], ["scaffold", "apply"], ["verify"], ["prove"],
    ["args", "run"], ["workflow", "stage"], ["promote", "t"],
    ["manifest", "set-status"], ["project", "init"],
])
def test_old_commands_fail_without_creating_artifacts(plugin_root, tmp_path, argv):
    result = subprocess.run([sys.executable, str(plugin_root / "scripts/mathtcs.py"), *argv],
                            cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 2
    assert "retired" in json.loads(result.stdout)["error"]
    assert list(tmp_path.iterdir()) == []
