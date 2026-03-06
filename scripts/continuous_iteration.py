#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def load_config(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def git_dirty() -> bool:
    result = run(["git", "status", "--porcelain"])
    return bool(result.stdout.strip())


def git_branch() -> str:
    result = run(["git", "branch", "--show-current"])
    return result.stdout.strip()


def run_verify_commands(commands: list[str], spec: str) -> list[dict]:
    results = []
    for command in commands:
        rendered = command.replace("{spec}", spec)
        proc = subprocess.run(
            rendered,
            cwd=ROOT,
            text=True,
            capture_output=True,
            shell=True,
        )
        results.append(
            {
                "command": rendered,
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip(),
                "stderr": proc.stderr.strip(),
            }
        )
        if proc.returncode != 0:
            break
    return results


def auto_commit(config: dict, spec: str, push: bool) -> dict:
    commit_cfg = config.get("commit", {})
    verify_commands = config.get("verify_commands", [])
    verify_results = run_verify_commands(verify_commands, spec) if verify_commands else []
    if any(item["returncode"] != 0 for item in verify_results):
        return {"committed": False, "reason": "verification_failed", "verification": verify_results}
    if not git_dirty():
        return {"committed": False, "reason": "clean_worktree", "verification": verify_results}
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    message_prefix = commit_cfg.get("message_prefix", "autoflow")
    message = f"{message_prefix}: {spec} iteration @ {timestamp}"
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", message])
    pushed = False
    if push or commit_cfg.get("push", False):
        run(["git", "push", "origin", git_branch()])
        pushed = True
    return {
        "committed": True,
        "pushed": pushed,
        "message": message,
        "verification": verify_results,
    }


def workflow_state(spec: str) -> dict:
    result = run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec])
    return json.loads(result.stdout)


def dispatch_next(config: dict, spec: str, dispatch: bool) -> dict:
    state = workflow_state(spec)
    next_action = state.get("recommended_next_action")
    if state.get("active_runs"):
        return {"dispatched": False, "reason": "active_run_exists", "state": state}
    if not next_action:
        return {"dispatched": False, "reason": "no_ready_task", "state": state}
    role = next_action["owner_role"]
    agent = config.get("role_agents", {}).get(role)
    if not agent:
        return {"dispatched": False, "reason": f"no_agent_for_role:{role}", "state": state}
    payload = {
        "spec": spec,
        "task": next_action["id"],
        "role": role,
        "agent": agent,
    }
    if dispatch:
        proc = run(
            ["bash", "scripts/workflow-dispatch.sh", spec, role, agent, next_action["id"]],
            check=True,
        )
        payload["tmux_session"] = proc.stdout.strip()
    return {"dispatched": dispatch, "payload": payload, "state": state}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autoflow phase 3 iteration loop")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--config", default="config/continuous-iteration.example.json")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--commit-if-dirty", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    result = {"spec": args.spec}
    if args.commit_if_dirty:
        result["commit"] = auto_commit(config, args.spec, args.push)
    result["dispatch"] = dispatch_next(config, args.spec, args.dispatch)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
