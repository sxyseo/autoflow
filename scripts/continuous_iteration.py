#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# Ensure we import from the autoflow package, not scripts/autoflow.py
# Project root must be in path BEFORE scripts directory
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    # Insert at position 0 to ensure it's found before scripts/autoflow.py
    sys.path.insert(0, str(_root))
    # If scripts is already in path, remove and re-add after root
    scripts_path = str(_root / 'scripts')
    if scripts_path in sys.path:
        sys.path.remove(scripts_path)
    sys.path.insert(1, scripts_path)

# Import shared utilities from autoflow.utils
from autoflow.utils import load_config, load_json, run_cmd


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"


def git_dirty() -> bool:
    result = run_cmd(["git", "status", "--porcelain"], cwd=ROOT)
    return bool(result.stdout.strip())


def git_branch() -> str:
    result = run_cmd(["git", "branch", "--show-current"], cwd=ROOT)
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


def auto_commit(config: dict, spec: str, push: bool, state: dict) -> dict:
    commit_cfg = config.get("commit", {})
    if state.get("active_runs") and not commit_cfg.get("allow_during_active_runs", False):
        return {"committed": False, "reason": "active_run_exists"}
    verify_commands = config.get("verify_commands", [])
    verify_results = run_verify_commands(verify_commands, spec) if verify_commands else []
    if any(item["returncode"] != 0 for item in verify_results):
        return {"committed": False, "reason": "verification_failed", "verification": verify_results}
    if not git_dirty():
        return {"committed": False, "reason": "clean_worktree", "verification": verify_results}
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    message_prefix = commit_cfg.get("message_prefix", "autoflow")
    message = f"{message_prefix}: {spec} iteration @ {timestamp}"
    run_cmd(["git", "add", "-A"], cwd=ROOT)
    run_cmd(["git", "commit", "-m", message], cwd=ROOT)
    pushed = False
    if push or commit_cfg.get("push", False):
        run_cmd(["git", "push", "origin", git_branch()], cwd=ROOT)
        pushed = True
    return {
        "committed": True,
        "pushed": pushed,
        "message": message,
        "verification": verify_results,
    }


def workflow_state(spec: str) -> dict:
    result = run_cmd(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec], cwd=ROOT)
    return json.loads(result.stdout)


def task_history(spec: str, task: str) -> list[dict]:
    result = run_cmd(["python3", "scripts/autoflow.py", "task-history", "--spec", spec, "--task", task], cwd=ROOT)
    return json.loads(result.stdout)


def sync_agents(overwrite: bool = False) -> dict:
    cmd = ["python3", "scripts/autoflow.py", "sync-agents"]
    if overwrite:
        cmd.append("--overwrite")
    result = run_cmd(cmd, cwd=ROOT)
    return json.loads(result.stdout)


def load_agent_catalog() -> dict[str, dict]:
    return load_json(AGENTS_FILE, default={"agents": {}}).get("agents", {})


def default_role_preferences(role: str) -> list[str]:
    preferences = {
        "spec-writer": ["codex-spec", "codex"],
        "task-graph-manager": ["codex-spec", "codex"],
        "implementation-runner": ["codex-impl", "codex", "acp-example"],
        "reviewer": ["claude-review", "claude", "codex"],
        "maintainer": ["codex-impl", "codex", "acp-example"],
    }
    return preferences.get(role, [])


def select_agent_for_role(config: dict, role: str, catalog: dict[str, dict]) -> tuple[str | None, str]:
    selection_cfg = config.get("agent_selection", {})
    candidates = []
    explicit = config.get("role_agents", {}).get(role)
    if explicit:
        candidates.append(explicit)
    candidates.extend(selection_cfg.get("role_preferences", {}).get(role, []))
    candidates.extend(default_role_preferences(role))
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate in catalog:
            source = "configured" if candidate == explicit else "fallback"
            return candidate, source
    return None, "missing"


def dispatch_gate(config: dict, state: dict, next_action: dict | None) -> dict | None:
    if state.get("active_runs"):
        return {"blocked": True, "reason": "active_run_exists"}
    if state.get("blocking_reason"):
        return {"blocked": True, "reason": state["blocking_reason"]}
    if not next_action:
        return {"blocked": True, "reason": "no_ready_task"}

    retry_cfg = config.get("retry_policy", {})
    max_attempts = retry_cfg.get("max_automatic_attempts", 3)
    history = task_history(state["spec"], next_action["id"])
    unsuccessful = [
        item for item in history if item.get("result") in {"needs_changes", "blocked", "failed"}
    ]
    if len(unsuccessful) >= max_attempts:
        return {
            "blocked": True,
            "reason": "max_automatic_attempts_reached",
            "attempts": len(unsuccessful),
        }
    if (
        retry_cfg.get("require_fix_request_for_retry", True)
        and next_action.get("status") == "needs_changes"
        and not state.get("fix_request_present")
    ):
        return {"blocked": True, "reason": "missing_fix_request"}
    return None


def dispatch_next(config: dict, spec: str, dispatch: bool) -> dict:
    state = workflow_state(spec)
    next_action = state.get("recommended_next_action")
    gate = dispatch_gate(config, state, next_action)
    if gate:
        return {"dispatched": False, "reason": gate["reason"], "gate": gate, "state": state}
    role = next_action["owner_role"]
    selection_cfg = config.get("agent_selection", {})
    sync_result = None
    if selection_cfg.get("sync_before_dispatch", True):
        sync_result = sync_agents(overwrite=selection_cfg.get("overwrite_discovered", False))
    catalog = load_agent_catalog()
    agent, source = select_agent_for_role(config, role, catalog)
    if not agent:
        return {
            "dispatched": False,
            "reason": f"no_agent_for_role:{role}",
            "state": state,
            "agent_sync": sync_result,
        }
    payload = {
        "spec": spec,
        "task": next_action["id"],
        "role": role,
        "agent": agent,
        "agent_selection": source,
    }
    if dispatch:
        proc = run_cmd(
            ["bash", "scripts/workflow-dispatch.sh", spec, role, agent, next_action["id"]],
            cwd=ROOT,
            check=True,
        )
        payload["tmux_session"] = proc.stdout.strip()
    return {"dispatched": dispatch, "payload": payload, "state": state, "agent_sync": sync_result}


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
    initial_state = workflow_state(args.spec)
    if args.commit_if_dirty:
        result["commit"] = auto_commit(config, args.spec, args.push, initial_state)
    result["dispatch"] = dispatch_next(config, args.spec, args.dispatch)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
