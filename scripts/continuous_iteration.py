#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
<<<<<<< HEAD
=======
import sys
from dataclasses import dataclass, field
>>>>>>> auto-claude/107-extract-shared-utilities-to-eliminate-code-duplica
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

<<<<<<< HEAD
=======
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
from autoflow.utils import load_config, load_json, run_cmd  # noqa: E402
>>>>>>> auto-claude/107-extract-shared-utilities-to-eliminate-code-duplica

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"
run = run_cmd


<<<<<<< HEAD
def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def load_config(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))
=======
class CommandExecutionError(Exception):
    """
    Exception raised for command execution errors.

    Attributes:
        message: Error message
        exit_code: Command exit code
        command: Command that failed
        spec: Spec slug being processed
    """

    def __init__(
        self,
        message: str,
        exit_code: int | None = None,
        command: str | None = None,
        spec: str | None = None,
    ):
        self.message = message
        self.exit_code = exit_code
        self.command = command
        self.spec = spec
        super().__init__(message)


class InvalidCommandError(Exception):
    """
    Exception raised for invalid command strings.

    Attributes:
        message: Error message
        command: Invalid command string
        reason: Specific reason for invalidity
    """

    def __init__(
        self,
        message: str,
        command: str | None = None,
        reason: str | None = None,
    ):
        self.message = message
        self.command = command
        self.reason = reason
        super().__init__(message)


@dataclass
class CommandResult:
    """
    Result of a command execution.

    Attributes:
        command: The command string that was executed
        success: Whether the command succeeded (exit code 0)
        exit_code: Process exit code
        stdout: Standard output (stripped)
        stderr: Standard error output (stripped)
        error: Error message if execution failed
    """

    command: str
    success: bool = False
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    def __repr__(self) -> str:
        """Return string representation."""
        status = "✓" if self.success else "✗"
        return f"{status} {self.command} (exit={self.exit_code})"


@dataclass
class VerifyCommandsResult:
    """
    Result of running verification commands.

    Attributes:
        commands_run: Number of commands executed
        all_success: Whether all commands succeeded
        results: List of individual command results
        stopped_at: Index of command where execution stopped (if failed early)
    """

    commands_run: int = 0
    all_success: bool = True
    results: list[CommandResult] = field(default_factory=list)
    stopped_at: int | None = None


def validate_slug_safe(slug: str) -> bool:
    """Validate that a slug does not contain path traversal patterns.

    Returns True if the slug is safe, False if it contains dangerous patterns
    that could lead to path traversal attacks.

    Checks for:
    - '..' sequences (parent directory)
    - './' sequences (current directory)
    - Absolute paths starting with '/'
    - Backslash separators (Windows paths)
    - Null bytes

    Args:
        slug: The slug string to validate

    Returns:
        bool: True if safe, False if dangerous
    """
    # Check for null bytes
    if "\0" in slug:
        return False

    # Check for parent directory patterns
    if ".." in slug:
        return False

    # Check for current directory patterns
    if "./" in slug:
        return False

    # Check for absolute paths
    if slug.startswith("/"):
        return False

    # Check for Windows path separators
    if "\\" in slug:
        return False

    # Check for drive letters (Windows absolute paths like C:)
    return not (len(slug) >= 2 and slug[1] == ":")
>>>>>>> auto-claude/107-extract-shared-utilities-to-eliminate-code-duplica


def git_dirty() -> bool:
    result = run(["git", "status", "--porcelain"], cwd=ROOT)
    return bool(result.stdout.strip())


def git_branch() -> str:
    result = run(["git", "branch", "--show-current"], cwd=ROOT)
    return result.stdout.strip()


def run_verify_commands(commands: list[str], spec: str) -> list[dict]:
    results = []
    for command in commands:
        rendered = command.replace("{spec}", spec)
        if any(token in rendered for token in ["&&", "||", "|", ";", ">", "<"]):
            results.append(
                {
                    "command": rendered,
                    "returncode": 2,
                    "stdout": "",
                    "stderr": "unsupported shell metacharacters in verify command",
                }
            )
            break
        proc = subprocess.run(
            shlex.split(rendered),
            cwd=ROOT,
            text=True,
            capture_output=True,
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
    run(["git", "add", "-A"], cwd=ROOT)
    run(["git", "commit", "-m", message], cwd=ROOT)
    pushed = False
    if push or commit_cfg.get("push", False):
        run(["git", "push", "origin", git_branch()], cwd=ROOT)
        pushed = True
    return {
        "committed": True,
        "pushed": pushed,
        "message": message,
        "verification": verify_results,
    }


<<<<<<< HEAD
def workflow_state(spec: str) -> dict:
    result = run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec])
    return json.loads(result.stdout)


def task_history(spec: str, task: str) -> list[dict]:
    result = run(["python3", "scripts/autoflow.py", "task-history", "--spec", spec, "--task", task])
    return json.loads(result.stdout)
=======
def workflow_state(spec: str) -> dict[str, Any]:
    result = run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec], cwd=ROOT)
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def task_history(spec: str, task: str) -> list[dict[str, Any]]:
    result = run(["python3", "scripts/autoflow.py", "task-history", "--spec", spec, "--task", task], cwd=ROOT)
    return json.loads(result.stdout)  # type: ignore[no-any-return]
>>>>>>> auto-claude/107-extract-shared-utilities-to-eliminate-code-duplica


def sync_agents(overwrite: bool = False) -> dict:
    cmd = ["python3", "scripts/autoflow.py", "sync-agents"]
    if overwrite:
        cmd.append("--overwrite")
<<<<<<< HEAD
    result = run(cmd)
    return json.loads(result.stdout)


def load_agent_catalog() -> dict[str, dict]:
    return load_json(AGENTS_FILE, default={"agents": {}}).get("agents", {})
=======
    result = run(cmd, cwd=ROOT)
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def sweep_stale_runs(config: dict[str, Any], spec: str, dispatch: bool) -> dict[str, Any]:
    recovery_cfg = config.get("recovery", {})
    cmd = [
        "python3",
        "scripts/autoflow.py",
        "sweep-runs",
        "--spec",
        spec,
        "--stale-after",
        str(recovery_cfg.get("stale_after_seconds", 120)),
    ]
    include_status = recovery_cfg.get("include_statuses", ["created", "running"])
    if include_status:
        cmd.extend(["--include-status", *include_status])
    if recovery_cfg.get("auto_recover", True):
        cmd.append("--auto-recover")
        if dispatch and recovery_cfg.get("dispatch_recovery", True):
            cmd.append("--dispatch-recovery")
    result = run(cmd, cwd=ROOT)
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def load_agent_catalog() -> dict[str, dict[str, Any]]:
    data = load_json(AGENTS_FILE, default={"agents": {}})
    agents = data.get("agents", {})
    return agents  # type: ignore[no-any-return]
>>>>>>> auto-claude/107-extract-shared-utilities-to-eliminate-code-duplica


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
        proc = run(
            ["bash", "scripts/workflow-dispatch.sh", spec, role, agent, next_action["id"]],
            cwd=ROOT,
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
