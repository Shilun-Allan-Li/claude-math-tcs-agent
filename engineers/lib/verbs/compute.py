"""Verb: compute — escape hatch for languages/scripts not covered by named verbs.

If used 3+ times for the same shape, promote to a named verb.
"""

from __future__ import annotations

from audit import ARTIFACTS, run_subprocess

LANG_RUNNERS = {
    "python": ("script.py", ["python3", "script.py"]),
    "bash": ("script.sh", ["bash", "script.sh"]),
    "sh": ("script.sh", ["sh", "script.sh"]),
    "node": ("script.js", ["node", "script.js"]),
    "r": ("script.R", ["Rscript", "script.R"]),
    "ruby": ("script.rb", ["ruby", "script.rb"]),
}


def run(args: dict, request_id: str) -> dict:
    """args: {"lang": str, "script": str, "env_pkgs": [str]?, "timeout_s": int}"""
    lang = args.get("lang")
    script = args.get("script")
    if not lang or not script:
        raise ValueError("missing required field(s): lang, script")
    if lang not in LANG_RUNNERS:
        raise ValueError(f"unsupported lang: {lang} (supported: {sorted(LANG_RUNNERS)})")
    timeout_s = float(args.get("timeout_s", 30))
    env_pkgs = args.get("env_pkgs") or []

    artifact_dir = ARTIFACTS / request_id
    filename, cmd = LANG_RUNNERS[lang]
    (artifact_dir / filename).write_text(script)

    # Optional pip install for python; capture output to install.log so the
    # main stdout/stderr stay tied to the script run, not the install noise.
    if lang == "python" and env_pkgs:
        install_result = run_subprocess(
            request_id, timeout_s, ["pip3", "install", "--quiet", *env_pkgs]
        )
        # Move install output aside so the verb's main run gets clean files.
        for name in ("stdout.txt", "stderr.txt"):
            old = artifact_dir / name
            if old.exists():
                old.rename(artifact_dir / f"install_{name}")
        if install_result["exit_code"] != 0:
            install_result["phase"] = "install"
            return install_result

    result = run_subprocess(request_id, timeout_s, cmd)
    result["phase"] = "run"
    return result
