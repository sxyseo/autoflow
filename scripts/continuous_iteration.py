#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"


class InvalidCommandError(ValueError):
    """Raised when a verify command cannot be parsed into safe argv tokens."""


@dataclass(slots=True)
class CommandResult:
    """Structured result for a single verification command."""

    command: str
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "success": self.success,
            "returncode": self.exit_code,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
        }


@dataclass(slots=True)
class VerifyCommandsResult:
    """Aggregate verification command results."""

    commands_run: int
    all_success: bool
    results: list[CommandResult]
    stopped_at: int | None = None

    def as_dicts(self) -> list[dict[str, Any]]:
        return [result.as_dict() for result in self.results]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def load_config(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def git_dirty() -> bool:
    result = run(["git", "status", "--porcelain"])
    return bool(result.stdout.strip())


def git_branch() -> str:
    result = run(["git", "branch", "--show-current"])
    return result.stdout.strip()


def run_verify_commands(commands: list[str], spec: str) -> VerifyCommandsResult:
    results: list[CommandResult] = []
    stopped_at: int | None = None
    for command in commands:
        rendered = command.replace("{spec}", spec)
        try:
            argv = shlex.split(rendered)
        except ValueError as exc:
            raise InvalidCommandError(f"Failed to parse command: {rendered}") from exc
        proc = subprocess.run(
            argv,
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        success = proc.returncode == 0
        results.append(
            CommandResult(
                command=rendered,
                success=success,
                exit_code=proc.returncode,
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                error=None if success else f"Command failed with exit code {proc.returncode}",
            )
        )
        if not success:
            stopped_at = len(results) - 1
            break
    return VerifyCommandsResult(
        commands_run=len(results),
        all_success=all(result.success for result in results),
        results=results,
        stopped_at=stopped_at,
    )


def _verification_records(results: VerifyCommandsResult | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(results, VerifyCommandsResult):
        return results.as_dicts()
    return results


def auto_commit(config: dict, spec: str, push: bool, state: dict) -> dict:
    commit_cfg = config.get("commit", {})
    if state.get("active_runs") and not commit_cfg.get("allow_during_active_runs", False):
        return {"committed": False, "reason": "active_run_exists"}
    verify_commands = config.get("verify_commands", [])
    verify_results = run_verify_commands(verify_commands, spec) if verify_commands else VerifyCommandsResult(
        commands_run=0,
        all_success=True,
        results=[],
    )
    verification_records = _verification_records(verify_results)
    if any(not item.get("success", item.get("returncode", 1) == 0) for item in verification_records):
        return {
            "committed": False,
            "reason": "verification_failed",
            "verification": verification_records,
        }
    if not git_dirty():
        return {"committed": False, "reason": "clean_worktree", "verification": verification_records}
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
        "verification": verification_records,
    }


def workflow_state(spec: str) -> dict:
    result = run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec])
    return json.loads(result.stdout)


def task_history(spec: str, task: str) -> list[dict]:
    result = run(["python3", "scripts/autoflow.py", "task-history", "--spec", spec, "--task", task])
    return json.loads(result.stdout)


def sync_agents(overwrite: bool = False) -> dict:
    cmd = ["python3", "scripts/autoflow.py", "sync-agents"]
    if overwrite:
        cmd.append("--overwrite")
    result = run(cmd)
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


def _active_task_ids(state: dict[str, Any]) -> set[str]:
    active = set()
    for run_info in state.get("active_runs", []):
        if isinstance(run_info, dict):
            task_id = run_info.get("task")
            if task_id:
                active.add(task_id)
    return active


def _select_next_action(state: dict[str, Any]) -> dict[str, Any] | None:
    active_task_ids = _active_task_ids(state)
    recommended = state.get("recommended_next_action")
    if recommended and recommended.get("id") not in active_task_ids:
        return recommended
    for task in state.get("ready_tasks", []):
        if task.get("id") not in active_task_ids:
            return task
    return recommended


def _active_run_count_for_agent(state: dict[str, Any], agent: str) -> int:
    count = 0
    for run_info in state.get("active_runs", []):
        if isinstance(run_info, dict) and run_info.get("agent") == agent:
            count += 1
    return count


def dispatch_next(config: dict, spec: str, dispatch: bool) -> dict:
    state = workflow_state(spec)
    next_action = _select_next_action(state)
    gate = dispatch_gate(config, state, next_action)
    if gate:
        return {"dispatched": False, "reason": gate["reason"], "gate": gate, "state": state}
    dispatch_cfg = config.get("dispatch", {})
    max_concurrent_runs = dispatch_cfg.get("max_concurrent_runs", 1)
    if len(state.get("active_runs", [])) >= max_concurrent_runs:
        return {
            "dispatched": False,
            "reason": "spec_concurrency_limit_reached",
            "state": state,
        }
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
    agent_max_concurrent = catalog.get(agent, {}).get("max_concurrent")
    if agent_max_concurrent is not None and _active_run_count_for_agent(state, agent) >= agent_max_concurrent:
        return {
            "dispatched": False,
            "reason": "agent_concurrency_limit_reached",
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
        proc = run(
            ["bash", "scripts/workflow-dispatch.sh", spec, role, agent, next_action["id"]],
            check=True,
        )
        payload["tmux_session"] = proc.stdout.strip()
    return {"dispatched": dispatch, "payload": payload, "state": state, "agent_sync": sync_result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autoflow single-pass iteration loop")
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
