import importlib.util
import json
import subprocess
import sys

import pytest


@pytest.fixture
def hook(plugin_root):
    spec = importlib.util.spec_from_file_location("lean_guidance", plugin_root / "scripts/lean_guidance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_detection_and_opt_out(tmp_path, hook, monkeypatch):
    event = {"hook_event_name": "SessionStart", "cwd": str(tmp_path)}
    assert hook.response(event) == {}
    (tmp_path / "lean-toolchain").write_text("leanprover/lean4:v4.25.0")
    assert hook.response(event) == {}
    (tmp_path / "lakefile.toml").write_text('name = "test"')
    child = tmp_path / "Sub"
    child.mkdir()
    event["cwd"] = str(child)
    for name in ("SessionStart", "UserPromptSubmit"):
        event["hook_event_name"] = name
        output = hook.response(event)
        assert output["hookSpecificOutput"]["hookEventName"] == name
        assert len(output["hookSpecificOutput"]["additionalContext"]) < 1800
    monkeypatch.setenv("MATH_TCS_ENABLED", "0")
    assert hook.response(event) == {}


def test_malformed_hook_input(plugin_root):
    r = subprocess.run([sys.executable, str(plugin_root / "scripts/lean_guidance.py")], input="{bad", text=True, capture_output=True)
    assert r.returncode == 0 and json.loads(r.stdout) == {}


def test_hook_does_not_create_project_files(tmp_path, hook):
    (tmp_path / "lean-toolchain").write_text("test")
    (tmp_path / "lakefile.lean").write_text("test")
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    hook.response({"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path)})
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
