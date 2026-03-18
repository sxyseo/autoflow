#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


def command_ready(command: str) -> dict[str, str | bool]:
    path = shutil.which(command)
    return {"available": bool(path), "path": path or ""}


def imports_ready() -> dict[str, bool]:
    modules = ["click", "pydantic", "json5", "apscheduler", "aiohttp"]
    results: dict[str, bool] = {}
    for module in modules:
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        results[module] = proc.returncode == 0
    return results


def main() -> None:
    git_status = run(["git", "status", "--short"])
    autoflow_help = run([sys.executable, "scripts/autoflow.py", "--help"])
    scheduler_help = run([sys.executable, "scripts/scheduler.py", "--help"])
    imports = imports_ready()
    commands = {
        "tmux": command_ready("tmux"),
        "codex": command_ready("codex"),
        "claude": command_ready("claude"),
        "git": command_ready("git"),
    }

    dirty = bool(git_status.stdout.strip())
    missing_imports = [name for name, ready in imports.items() if not ready]
    recommended = [
        "python3 scripts/autoflow.py init",
        "python3 scripts/autoflow.py init-system-config",
        "python3 scripts/autoflow.py sync-agents",
        "python3 scripts/validate_readme_flow.py --agent codex",
    ]
    if commands["tmux"]["available"]:
        recommended.append("python3 scripts/validate_runtime_loop.py")
    if imports.get("apscheduler", False):
        recommended.append("python3 scripts/validate_scheduler_start.py")

    payload = {
        "root": str(ROOT),
        "python": sys.executable,
        "virtualenv_active": bool(os.environ.get("VIRTUAL_ENV")),
        "git_dirty": dirty,
        "imports": imports,
        "commands": commands,
        "autoflow_cli_ready": autoflow_help.returncode == 0,
        "scheduler_cli_ready": scheduler_help.returncode == 0,
        "ready_for_smoke": not dirty and not missing_imports and autoflow_help.returncode == 0,
        "recommended_commands": recommended,
        "warnings": [
            message
            for message in [
                "working tree is dirty; validate from a clean worktree or clone first" if dirty else "",
                "missing Python dependencies; run `pip install -e '.[dev]'` in a virtualenv first"
                if missing_imports
                else "",
                "tmux is unavailable; skip runtime loop validation until tmux is installed"
                if not commands["tmux"]["available"]
                else "",
            ]
            if message
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
