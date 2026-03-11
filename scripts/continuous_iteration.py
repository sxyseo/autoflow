#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"


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


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, capture_output=True)


def load_config(path: str) -> dict[str, Any]:
    content = (ROOT / path).read_text(encoding="utf-8")
    return json.loads(content)  # type: ignore[no-any-return]


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    content = path.read_text(encoding="utf-8")
    return json.loads(content)  # type: ignore[no-any-return]


def git_dirty() -> bool:
    result = run(["git", "status", "--porcelain"])
    return bool(result.stdout.strip())


def git_branch() -> str:
    result = run(["git", "branch", "--show-current"])
    return result.stdout.strip()


def run_verify_commands(commands: list[str], spec: str) -> VerifyCommandsResult:
    """
    Run verification commands with proper error handling and security safeguards.

    Executes a list of commands in sequence, stopping at the first failure.
    Commands support a {spec} placeholder that is replaced with the spec slug.

    Security Fix (CWE-77: Command Injection):
    -----------------------------------------
    This function implements multiple layers of protection against command injection
    vulnerabilities when processing user-controlled spec slugs:

    1. **Input Validation**: The spec parameter should be validated using
       validate_slug_safe() before calling this function. This prevents path
       traversal attacks (../../), null byte injection, and absolute path injection.

    2. **Safe Parsing**: Uses shlex.split() for shell-like parsing instead of
       direct string evaluation. This prevents shell metacharacter injection
       while preserving legitimate quoted arguments.

    3. **List-Based Execution**: Commands are executed as argument lists via
       subprocess.run() with no shell=True, ensuring no shell interpretation
       of the command string.

    4. **Template Validation**: Empty commands and parsing errors are detected
       and reported via InvalidCommandError exceptions.

    Example Attack Prevention:
    - Malicious spec: "../../../etc/passwd" → Blocked by validate_slug_safe()
    - Shell injection: "spec; rm -rf /" → Blocked by shlex.split() + list execution
    - Command chaining: "spec && evil" → Blocked by shlex.split() parsing
    - Path traversal: "../malicious" → Blocked by validate_slug_safe()

    Args:
        commands: List of command templates (may contain {spec} placeholder)
        spec: Spec slug to substitute into commands (MUST be validated first)

    Returns:
        VerifyCommandsResult containing execution results for all commands

    Raises:
        InvalidCommandError: If a command template is invalid or cannot be parsed
        CommandExecutionError: If a critical system error occurs during execution

    Example:
        >>> # Validate spec first to prevent command injection
        >>> if validate_slug_safe(spec_slug):
        ...     result = run_verify_commands(["pytest tests/", "flake8 src/"], spec_slug)
        ...     if result.all_success:
        ...         print("All checks passed")
        ...     else:
        ...         for cmd_result in result.results:
        ...             if not cmd_result.success:
        ...                 print(f"Failed: {cmd_result.command}")
        ...                 print(f"Error: {cmd_result.stderr}")
        >>> else:
        ...     print("Invalid spec slug - rejecting for security reasons")
    """
    if not commands:
        return VerifyCommandsResult(commands_run=0, all_success=True, results=[])

    results = []
    for idx, command in enumerate(commands):
        try:
            # Render the command template
            rendered = command.replace("{spec}", spec)

            # Validate command before parsing
            if not rendered or not rendered.strip():
                raise InvalidCommandError(
                    message="Empty command after rendering",
                    command=command,
                    reason="Command resulted in empty string after spec substitution",
                )

            # Parse command using shlex for proper shell-like splitting
            try:
                cmd_list = shlex.split(rendered)
            except ValueError as e:
                raise InvalidCommandError(
                    message=f"Failed to parse command: {e}",
                    command=rendered,
                    reason=str(e),
                ) from e

            # Validate command list is not empty
            if not cmd_list:
                raise InvalidCommandError(
                    message="Command parsed to empty list",
                    command=rendered,
                    reason="shlex.split produced no arguments",
                )

            # Execute the command
            try:
                proc = subprocess.run(
                    cmd_list,
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=300,  # 5 minute timeout per command
                )
            except subprocess.TimeoutExpired:
                # Command timed out - treat as failure but continue
                cmd_result = CommandResult(
                    command=rendered,
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr="Command timed out after 300 seconds",
                    error="timeout",
                )
                results.append(cmd_result)
                return VerifyCommandsResult(
                    commands_run=idx + 1,
                    all_success=False,
                    results=results,
                    stopped_at=idx,
                )
            except FileNotFoundError as e:
                # Command executable not found - critical error
                raise CommandExecutionError(
                    message=f"Command not found: {cmd_list[0]}",
                    exit_code=None,
                    command=rendered,
                    spec=spec,
                ) from e
            except Exception as e:
                # Unexpected subprocess error
                raise CommandExecutionError(
                    message=f"Unexpected error executing command: {e}",
                    exit_code=None,
                    command=rendered,
                    spec=spec,
                ) from e

            # Build result object
            cmd_result = CommandResult(
                command=rendered,
                success=(proc.returncode == 0),
                exit_code=proc.returncode,
                stdout=proc.stdout.strip(),
                stderr=proc.stderr.strip(),
                error=None if proc.returncode == 0 else proc.stderr.strip(),
            )
            results.append(cmd_result)

            # Stop on first failure
            if proc.returncode != 0:
                return VerifyCommandsResult(
                    commands_run=idx + 1,
                    all_success=False,
                    results=results,
                    stopped_at=idx,
                )

        except (InvalidCommandError, CommandExecutionError):
            # Re-raise custom exceptions as-is
            raise
        except Exception as e:
            # Catch any other unexpected errors and wrap them
            raise CommandExecutionError(
                message=f"Unexpected error during verification: {e}",
                command=command if 'command' in locals() else None,
                spec=spec,
            ) from e

    return VerifyCommandsResult(
        commands_run=len(results),
        all_success=True,
        results=results,
        stopped_at=None,
    )


def auto_commit(config: dict[str, Any], spec: str, push: bool, state: dict[str, Any]) -> dict[str, Any]:
    """
    Attempt to commit and push changes with verification.

    Args:
        config: Continuous iteration configuration
        spec: Spec slug being processed
        push: Whether to push commits to remote
        state: Current workflow state

    Returns:
        dict with commit status, push status, and verification results

    Raises:
        InvalidCommandError: If verification commands are invalid
        CommandExecutionError: If critical errors occur during verification
    """
    commit_cfg = config.get("commit", {})
    if state.get("active_runs") and not commit_cfg.get("allow_during_active_runs", False):
        return {"committed": False, "reason": "active_run_exists"}

    verify_commands = config.get("verify_commands", [])
    verify_results = run_verify_commands(verify_commands, spec) if verify_commands else VerifyCommandsResult(commands_run=0, all_success=True, results=[])

    if not verify_results.all_success:
        # Convert CommandResult objects to dicts for JSON serialization
        verification_dict = [
            {
                "command": r.command,
                "success": r.success,
                "exit_code": r.exit_code,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "error": r.error,
            }
            for r in verify_results.results
        ]
        return {
            "committed": False,
            "reason": "verification_failed",
            "verification": verification_dict,
        }

    if not git_dirty():
        # Convert to dicts even for clean worktree
        verification_dict = [
            {
                "command": r.command,
                "success": r.success,
                "exit_code": r.exit_code,
                "stdout": r.stdout,
                "stderr": r.stderr,
                "error": r.error,
            }
            for r in verify_results.results
        ]
        return {
            "committed": False,
            "reason": "clean_worktree",
            "verification": verification_dict,
        }

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    message_prefix = commit_cfg.get("message_prefix", "autoflow")
    message = f"{message_prefix}: {spec} iteration @ {timestamp}"
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", message])
    pushed = False
    if push or commit_cfg.get("push", False):
        run(["git", "push", "origin", git_branch()])
        pushed = True

    # Convert to dicts for successful commit
    verification_dict = [
        {
            "command": r.command,
            "success": r.success,
            "exit_code": r.exit_code,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "error": r.error,
        }
        for r in verify_results.results
    ]

    return {
        "committed": True,
        "pushed": pushed,
        "message": message,
        "verification": verification_dict,
    }


def workflow_state(spec: str) -> dict[str, Any]:
    result = run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", spec])
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def task_history(spec: str, task: str) -> list[dict[str, Any]]:
    result = run(["python3", "scripts/autoflow.py", "task-history", "--spec", spec, "--task", task])
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def sync_agents(overwrite: bool = False) -> dict[str, Any]:
    cmd = ["python3", "scripts/autoflow.py", "sync-agents"]
    if overwrite:
        cmd.append("--overwrite")
    result = run(cmd)
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
    result = run(cmd)
    return json.loads(result.stdout)  # type: ignore[no-any-return]


def load_agent_catalog() -> dict[str, dict[str, Any]]:
    data = load_json(AGENTS_FILE, default={"agents": {}})
    agents = data.get("agents", {})
    return agents  # type: ignore[no-any-return]


def default_role_preferences(role: str) -> list[str]:
    preferences = {
        "spec-writer": ["codex-spec", "codex"],
        "task-graph-manager": ["codex-spec", "codex"],
        "implementation-runner": ["codex-impl", "codex", "acp-example"],
        "reviewer": ["claude-review", "claude", "codex"],
        "maintainer": ["codex-impl", "codex", "acp-example"],
    }
    return preferences.get(role, [])


def dispatch_settings(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("dispatch", {})


def select_dispatch_candidate(state: dict[str, Any]) -> dict[str, Any] | None:
    next_action = state.get("recommended_next_action")
    if next_action:
        return next_action

    ready_tasks = state.get("ready_tasks", [])
    if not ready_tasks:
        return None

    active_task_ids = {
        item.get("task")
        for item in state.get("active_runs", [])
        if isinstance(item, dict) and item.get("task")
    }
    for entry in ready_tasks:
        if entry.get("id") not in active_task_ids:
            return entry
    return None


def active_runs_for_agent(state: dict[str, Any], agent_name: str) -> int:
    return sum(
        1
        for item in state.get("active_runs", [])
        if isinstance(item, dict) and item.get("agent") == agent_name
    )


def select_agent_for_role(config: dict[str, Any], role: str, catalog: dict[str, dict[str, Any]]) -> tuple[str | None, str]:
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


def dispatch_gate(config: dict[str, Any], state: dict[str, Any], next_action: dict[str, Any] | None) -> dict[str, Any] | None:
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


def concurrency_gate(
    config: dict[str, Any],
    state: dict[str, Any],
    agent_name: str,
    catalog: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    active_runs = state.get("active_runs", [])
    dispatch_cfg = dispatch_settings(config)
    max_spec_runs = dispatch_cfg.get("max_concurrent_runs", 1)
    if len(active_runs) >= max_spec_runs:
        return {
            "blocked": True,
            "reason": "spec_concurrency_limit_reached",
            "active_runs": len(active_runs),
            "max_concurrent_runs": max_spec_runs,
        }

    agent_spec = catalog.get(agent_name, {})
    max_agent_runs = agent_spec.get("max_concurrent")
    if isinstance(max_agent_runs, int) and max_agent_runs > 0:
        current_agent_runs = active_runs_for_agent(state, agent_name)
        if current_agent_runs >= max_agent_runs:
            return {
                "blocked": True,
                "reason": "agent_concurrency_limit_reached",
                "agent": agent_name,
                "active_runs": current_agent_runs,
                "max_concurrent": max_agent_runs,
            }
    return None


def dispatch_next(config: dict[str, Any], spec: str, dispatch: bool) -> dict[str, Any]:
    state = workflow_state(spec)
    next_action = select_dispatch_candidate(state)
    gate = dispatch_gate(config, state, next_action)
    if gate:
        return {"dispatched": False, "reason": gate["reason"], "gate": gate, "state": state}
    if not next_action:
        return {"dispatched": False, "reason": "no_next_action", "state": state}
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
    limit_gate = concurrency_gate(config, state, agent, catalog)
    if limit_gate:
        return {
            "dispatched": False,
            "reason": limit_gate["reason"],
            "gate": limit_gate,
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
    parser = argparse.ArgumentParser(description="Autoflow phase 3 iteration loop")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--config", default="config/continuous-iteration.example.json")
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--commit-if-dirty", action="store_true")
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()

    # Validate spec slug to prevent command injection
    if not validate_slug_safe(args.spec):
        print(
            json.dumps(
                {
                    "error": "invalid_spec_slug",
                    "message": f"Spec slug '{args.spec}' contains dangerous patterns (path traversal, absolute paths, etc.)",
                },
                indent=2,
                ensure_ascii=True,
            )
        )
        raise SystemExit(1)

    config = load_config(args.config)
    result = {"spec": args.spec}
    result["recovery"] = sweep_stale_runs(config, args.spec, args.dispatch)
    initial_state = workflow_state(args.spec)
    if args.commit_if_dirty:
        result["commit"] = auto_commit(config, args.spec, args.push, initial_state)
    result["dispatch"] = dispatch_next(config, args.spec, args.dispatch)
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
