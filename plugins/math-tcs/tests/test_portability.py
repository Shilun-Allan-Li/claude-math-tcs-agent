"""Exercise a relocated checkout without using installed hosts or personal directories."""
import json
import os
import shutil
import subprocess
import sys


def test_relocated_plugin_cli_hooks_and_skill_links(tmp_path, plugin_root):
    relocated = tmp_path / "Another researcher" / "插件 checkout" / "math-tcs"
    shutil.copytree(plugin_root, relocated, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    project = tmp_path / "My Lean project"
    child = project / "Nested folder"
    child.mkdir(parents=True)
    (project / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
    (project / "lakefile.toml").write_text('name = "portable"\n')
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(relocated)}
    env.pop("MATH_TCS_ENABLED", None)
    result = subprocess.run([sys.executable, str(relocated / "scripts/mathtcs.py"), "project", "detect"],
                            cwd=child, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["root"] == str(project.resolve())
    hooks = json.loads((relocated / "hooks/hooks.json").read_text())["hooks"]
    for event in ("SessionStart", "UserPromptSubmit"):
        command = hooks[event][0]["hooks"][0]["command"]
        result = subprocess.run(command, shell=True, cwd=child, env=env, text=True,
                                input=json.dumps({"hook_event_name": event, "cwd": str(child)}), capture_output=True)
        assert result.returncode == 0, result.stderr
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        assert context == (relocated / "guidance.md").read_text()
    for name in ("formalize", "review", "simplify"):
        skill = relocated / "skills" / name
        assert (skill / "../../guidance.md").resolve().is_file()
        assert (skill / "../../docs/agent-loop.md").resolve().is_file()


def test_make_paths_with_spaces_and_required_target(tmp_path, plugin_root):
    checkout = tmp_path / "Different checkout"
    checkout.mkdir()
    shutil.copyfile(plugin_root.parents[1] / "Makefile", checkout / "Makefile")
    project = tmp_path / "My Lean project"
    project.mkdir()
    (project / "lean-toolchain").write_text("leanprover/lean4:v4.25.0")
    # Do not launch a host: print a development invocation, run only the preflight.
    result = subprocess.run(["make", "-n", "dev", "TARGET=../My Lean project"], cwd=checkout,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert f'cd "{project}" && claude --plugin-dir "{checkout}/plugins/math-tcs"' in result.stdout
    result = subprocess.run(["make", "require-target", "TARGET=../My Lean project"], cwd=checkout,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run(["make", "require-target", "TARGET="], cwd=checkout, text=True, capture_output=True)
    assert result.returncode != 0 and "Set TARGET" in result.stderr
