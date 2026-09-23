import json
import os
import shutil
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN / "scripts"))

DEMO_SOURCE = PLUGIN / "examples" / "demo" / "source" / "01_unit-1-divisibility.md"
EXPECTED = PLUGIN / "examples" / "demo" / "expected"


def pytest_configure(config):
    config.addinivalue_line("markers", "lean: needs `lake` and a target project with Mathlib built (MATH_TCS_TEST_PROJECT)")


@pytest.fixture
def plugin_root() -> Path:
    return PLUGIN


@pytest.fixture
def demo_source() -> Path:
    return DEMO_SOURCE


@pytest.fixture
def expected() -> Path:
    return EXPECTED


@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """A minimal lakefile.toml project with a math-tcs config (no Lean run)."""
    from mathtcs import project
    root = tmp_path / "proj"
    root.mkdir()
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.25.0\n")
    (root / "lakefile.toml").write_text('name = "proj"\n[[lean_lib]]\nname = "Proj"\n')
    (root / "Proj").mkdir()
    (root / "Proj.lean").write_text("")
    project.init(root, lib="Proj", module_prefix="Proj.MathTcs", namespace="MathTcs", slug="dn")
    return root


def _lean_project() -> Path | None:
    env = os.environ.get("MATH_TCS_TEST_PROJECT")
    candidates = [env] if env else []
    for c in candidates:
        if not c:
            continue
        p = Path(c).expanduser().resolve()
        if (p / "lean-toolchain").exists() and (p / ".lake" / "packages" / "mathlib").exists() and shutil.which("lake"):
            return p
    return None


@pytest.fixture(scope="session")
def lean_project() -> Path:
    p = _lean_project()
    if p is None:
        pytest.skip("needs lake and a target project with Mathlib built (set MATH_TCS_TEST_PROJECT)")
    return p


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1))
