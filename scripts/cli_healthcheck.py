#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def probe_binary(name: str) -> dict[str, Any]:
    path = shutil.which(name)
    if not path:
        return {
            "name": name,
            "available": False,
            "path": "",
            "status": "missing",
            "version": "",
            "capabilities": {},
        }

    version_cmd = [name, "--version"]
    if name == "tmux":
        version_cmd = [name, "-V"]
    version_result = run(version_cmd, cwd=ROOT, check=False)
    help_result = run([name, "--help"], cwd=ROOT, check=False)
    version_text = (version_result.stdout or version_result.stderr).strip()
    help_text = (help_result.stdout or "") + (help_result.stderr or "")
    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }
    return {
        "name": name,
        "available": True,
        "path": path,
        "status": "ok",
        "version": version_text.splitlines()[0] if version_text else "",
        "capabilities": capabilities,
    }


def tmux_sessions() -> list[dict[str, Any]]:
    if not shutil.which("tmux"):
        return []
    result = run(["tmux", "list-sessions", "-F", "#{session_name}:#{session_windows}:#{session_attached}"], cwd=ROOT, check=False)
    if result.returncode != 0:
        return []
    sessions = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        name, windows, attached = (line.split(":") + ["0", "0"])[:3]
        sessions.append(
            {
                "name": name,
                "windows": int(windows),
                "attached": bool(int(attached)),
            }
        )
    return sessions


def build_report() -> dict[str, Any]:
    binaries = [probe_binary("codex"), probe_binary("claude"), probe_binary("tmux")]
    return {
        "checked_at": now_stamp(),
        "binaries": binaries,
        "tmux_sessions": tmux_sessions(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report local Codex/Claude/tmux health")
    parser.add_argument("--require", action="append", default=[])
    args = parser.parse_args()

    report = build_report()
    required = set(args.require)
    missing = [
        item["name"]
        for item in report["binaries"]
        if item["name"] in required and not item["available"]
    ]
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if missing:
        raise SystemExit(f"required binaries missing: {', '.join(sorted(missing))}")


if __name__ == "__main__":
    main()
