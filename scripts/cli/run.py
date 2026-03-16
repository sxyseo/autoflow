"""
Autoflow CLI - Run Commands

Manage run lifecycle for AI-driven task execution.

Usage:
    from scripts.cli.run import add_subparser, create_run, complete_run

    # Register run commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    create_run(args)
    complete_run(args)
"""

from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    AGENT_RESULT_FILE,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    ROOT,
    RUNS_DIR,
    RUN_RESULTS,
    ensure_state,
    load_tasks,
    now_stamp,
    print_json,
    read_json,
    save_tasks,
    slugify,
    write_json,
)
from scripts.integrity import hash_file_content

# For now, import helper functions from the monolithic autoflow.py
# These will be moved to utils.py in subtask-2-2
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _get_run_helper_functions():
    """Import run helper functions from autoflow.py (temporary)."""
    # These functions will be moved to utils.py in subtask-2-2
    import scripts.autoflow as af

    return {
        'AgentSpec': af.AgentSpec,
        'build_prompt': af.build_prompt,
        'task_lookup': af.task_lookup,
        'task_run_history': af.task_run_history,
        'review_status_summary': af.review_status_summary,
        'next_task_data': af.next_task_data,
        'sync_review_state': af.sync_review_state,
        'record_event': af.record_event,
        'native_resume_preview': af.native_resume_preview,
        'write_handoff': af.write_handoff,
        'clear_fix_request': af.clear_fix_request,
        'record_reflection': af.record_reflection,
        'write_fix_request': af.write_fix_request,
        'load_system_config': af.load_system_config,
        'append_memory': af.append_memory,
        'parse_findings': af.parse_findings,
        'complete_run_record': af.complete_run_record,
        'finalize_run_record': af.finalize_run_record,
        'recover_run_record': af.recover_run_record,
        'run_metadata_iter': af.run_metadata_iter,
        'load_agents': af.load_agents,
        'load_run_metadata': af.load_run_metadata,
        'write_run_metadata': af.write_run_metadata,
        'worktree_path': af.worktree_path,
        'invalidate_run_cache': af.invalidate_run_cache,
        'active_runs_for_spec': af.active_runs_for_spec,
        'run_stale_reason': af.run_stale_reason,
    }


# Get helper functions
_helpers = _get_run_helper_functions()
AgentSpec = _helpers['AgentSpec']
build_prompt = _helpers['build_prompt']
task_lookup = _helpers['task_lookup']
task_run_history = _helpers['task_run_history']
review_status_summary = _helpers['review_status_summary']
next_task_data = _helpers['next_task_data']
sync_review_state = _helpers['sync_review_state']
record_event = _helpers['record_event']
native_resume_preview = _helpers['native_resume_preview']
write_handoff = _helpers['write_handoff']
clear_fix_request = _helpers['clear_fix_request']
record_reflection = _helpers['record_reflection']
write_fix_request = _helpers['write_fix_request']
load_system_config = _helpers['load_system_config']
append_memory = _helpers['append_memory']
parse_findings = _helpers['parse_findings']
complete_run_record = _helpers['complete_run_record']
finalize_run_record = _helpers['finalize_run_record']
recover_run_record = _helpers['recover_run_record']
run_metadata_iter = _helpers['run_metadata_iter']
load_agents = _helpers['load_agents']
load_run_metadata = _helpers['load_run_metadata']
write_run_metadata = _helpers['write_run_metadata']
worktree_path = _helpers['worktree_path']
invalidate_run_cache = _helpers['invalidate_run_cache']
active_runs_for_spec = _helpers['active_runs_for_spec']
run_stale_reason = _helpers['run_stale_reason']


def create_run_record(
    spec_slug: str,
    role: str,
    agent_name: str,
    task_id: str,
    branch: str | None = None,
    resume_from: str | None = None,
) -> Path:
    """
    Create a new run record directory with all necessary files.

    Creates a unique run directory with timestamp-based ID, generates the agent prompt,
    creates the execution script, and writes run metadata. The run ID is formatted as:
    {timestamp}-{role}-{spec_slug}-{task_id}[-{suffix}] if duplicates exist.

    Args:
        spec_slug: Slug identifier for the spec
        role: Role executing the run (e.g., "implementation-runner", "reviewer")
        agent_name: Name of the agent to use for execution
        task_id: ID of the task to execute
        branch: Git branch name (defaults to "codex/{spec_slug}-{task_id}")
        resume_from: Optional run ID to resume from

    Returns:
        Path to the created run directory

    Raises:
        SystemExit: If run directory creation fails (already exists after suffix attempts)
        KeyError: If agent_name is not found in agents configuration
    """
    agents = load_agents()
    agent = agents[agent_name]
    run_id_base = f"{now_stamp()}-{slugify(role)}-{slugify(spec_slug)}-{slugify(task_id)}"
    run_id = run_id_base
    run_dir = RUNS_DIR / run_id
    suffix = 1
    while run_dir.exists():
        run_id = f"{run_id_base}-{suffix}"
        run_dir = RUNS_DIR / run_id
        suffix += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    branch = branch or f"codex/{slugify(spec_slug)}-{slugify(task_id)}"
    target_workdir = worktree_path(spec_slug) if worktree_path(spec_slug).exists() else ROOT
    run_json_path = run_dir / "run.json"
    run_script = run_dir / "run.sh"
    prompt_path = run_dir / "prompt.md"
    agent_result_path = run_dir / AGENT_RESULT_FILE
    command = [agent.command, *agent.args, str(prompt_path)]
    prompt_path.write_text(
        build_prompt(
            spec_slug,
            role,
            task_id,
            agent,
            resume_from=resume_from,
            run_id=run_id,
        ),
        encoding="utf-8",
    )
    prompt_hash = hash_file_content(prompt_path)
    run_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(target_workdir))}",
                'session_name="${AUTOFLOW_TMUX_SESSION:-}"',
                f"export AUTOFLOW_RUN_ID={shlex.quote(run_id)}",
                f"export AUTOFLOW_RUN_DIR={shlex.quote(str(run_dir))}",
                f"export AUTOFLOW_AGENT_RESULT={shlex.quote(str(agent_result_path))}",
                "heartbeat_status() {",
                '  local status="$1"',
                "  shift || true",
                f"  local cmd=(python3 {shlex.quote(str(ROOT / 'scripts' / 'autoflow.py'))} heartbeat-run --run {shlex.quote(run_id)} --status \"$status\")",
                '  if [[ -n "${session_name}" ]]; then',
                '    cmd+=(--session "${session_name}")',
                "  fi",
                '  if [[ $# -gt 0 ]]; then',
                '    cmd+=("$@")',
                "  fi",
                '  "${cmd[@]}" >/dev/null 2>&1 || true',
                "}",
                "heartbeat_status running",
                "(",
                "  while true; do",
                f"    sleep {DEFAULT_HEARTBEAT_INTERVAL_SECONDS}",
                "    heartbeat_status running",
                "  done",
                ") &",
                "heartbeat_pid=$!",
                f"if {shlex.quote(str(ROOT / 'scripts' / 'run-agent.sh'))} {shlex.quote(agent_name)} {shlex.quote(str(prompt_path))} {shlex.quote(str(run_json_path))}; then",
                "  exit_code=0",
                "else",
                "  exit_code=$?",
                "fi",
                'kill "${heartbeat_pid}" >/dev/null 2>&1 || true',
                'wait "${heartbeat_pid}" 2>/dev/null || true',
                'heartbeat_status exited --exit-code "${exit_code}"',
                (
                    f"python3 {shlex.quote(str(ROOT / 'scripts' / 'autoflow.py'))} "
                    f"finalize-run --run {shlex.quote(run_id)} "
                    f"--exit-code \"${{exit_code}}\" "
                    f"--result-file {shlex.quote(str(agent_result_path))}"
                ),
                'exit "${exit_code}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    summary_path = run_dir / "summary.md"
    summary_path.write_text("# Run Summary\n\nFill after execution.\n", encoding="utf-8")
    os.chmod(run_script, 0o755)
    run_script_hash = hash_file_content(run_script)
    metadata = {
        "id": run_id,
        "spec": spec_slug,
        "task": task_id,
        "role": role,
        "agent": agent_name,
        "branch": branch,
        "workdir": str(target_workdir),
        "created_at": now_stamp(),
        "heartbeat_at": now_stamp(),
        "command_preview": command,
        "status": "created",
        "heartbeat_interval_seconds": DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        "stale_after_seconds": DEFAULT_STALE_AFTER_SECONDS,
        "tmux_session": "",
        "agent_result_path": str(agent_result_path),
        "attempt_count": len(task_run_history(spec_slug, task_id)) + 1,
        "resume_from": resume_from or "",
        "resume_command": f"python3 scripts/autoflow.py resume-run --run {run_id}",
        "native_resume_supported": bool(agent.resume),
        "native_resume_command_preview": native_resume_preview(agent),
        "agent_config": agent.to_dict(),
        "retry_policy": {
            "max_automatic_attempts": 3,
            "requires_fix_request_after_review_failure": True,
        },
        "integrity": {
            "prompt.md": prompt_hash,
            "run.sh": run_script_hash,
        },
    }
    write_json(run_json_path, metadata)
    record_event(spec_slug, "run.created", {"run": run_id, "task": task_id, "role": role})
    invalidate_run_cache()
    return run_dir


def create_run(args: argparse.Namespace) -> None:
    """
    Create a new run for task execution.

    Validates the agent and spec review status, selects the appropriate task,
    updates task status to in_progress, and creates a run record. If no task
    is specified, automatically selects the next ready task for the role.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - role: Role executing the run
            - agent: Agent name to use
            - task: Optional task ID (auto-selects if not provided)
            - branch: Optional git branch name
            - resume_from: Optional run ID to resume from

    Raises:
        SystemExit: If agent is unknown, spec review is invalid, no ready task exists,
                    or task is not in a runnable state
    """
    ensure_state()
    agents = load_agents()
    if args.agent not in agents:
        raise SystemExit(f"unknown agent: {args.agent}")
    review_summary = review_status_summary(args.spec)
    if args.role in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        raise SystemExit(
            "spec review approval is not valid; approve the current planning contract before implementation"
        )
    chosen_task = args.task
    if not chosen_task:
        next_candidate = next_task_data(args.spec, args.role)
        if not next_candidate:
            raise SystemExit("no ready task for this role")
        chosen_task = next_candidate["id"]
    tasks = load_tasks(args.spec)
    task = task_lookup(tasks, chosen_task, spec_slug=args.spec)
    expected_role = "reviewer" if task["status"] == "in_review" and args.role == "reviewer" else task["owner_role"]
    if expected_role != args.role:
        raise SystemExit(f"task {chosen_task} belongs to role {task['owner_role']}, not {args.role}")
    if task["status"] not in {"todo", "needs_changes", "in_progress", "in_review"}:
        raise SystemExit(f"task {chosen_task} is not runnable from status {task['status']}")
    task["status"] = "in_progress"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": f"run pending for role {args.role}"}
    )
    save_tasks(args.spec, tasks, reason="task_status_updated", sync_review_state_callback=sync_review_state)
    run_dir = create_run_record(
        args.spec,
        args.role,
        args.agent,
        chosen_task,
        branch=args.branch,
        resume_from=getattr(args, "resume_from", None),
    )
    print(str(run_dir))


def resume_run(args: argparse.Namespace) -> None:
    """
    Resume a previous run by creating a new run record.

    Creates a new run that resumes from a previous run, preserving the original
    spec, role, agent, and task configuration. The new run is linked to the
    original run via the resume_from parameter.

    Args:
        args: Namespace with attributes:
            - run: Run ID to resume from

    Raises:
        SystemExit: If run ID is unknown or spec review is invalid
    """
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    review_summary = review_status_summary(metadata["spec"])
    if metadata["role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        raise SystemExit(
            "spec review approval is not valid; approve the current planning contract before resuming implementation"
        )
    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"], spec_slug=metadata["spec"])
    task["status"] = "in_progress"
    task.setdefault("notes", []).append({"at": now_stamp(), "note": f"retry created from {args.run}"})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated", sync_review_state_callback=sync_review_state)
    new_run = create_run_record(
        metadata["spec"],
        metadata["role"],
        metadata["agent"],
        metadata["task"],
        branch=metadata.get("branch"),
        resume_from=args.run,
    )
    record_event(metadata["spec"], "run.resumed", {"from": args.run, "task": metadata["task"]})
    print(str(new_run))


def heartbeat_run_cmd(args: argparse.Namespace) -> None:
    """
    Update run heartbeat metadata.

    Updates the run's heartbeat timestamp and optionally updates the run status
    and tmux session information.

    Args:
        args: Namespace with attributes:
            - run: Run ID to update
            - status: Optional new status to set
            - session: Optional tmux session name
            - exit_code: Optional exit code to record
    """
    metadata = load_run_metadata(args.run)
    if metadata.get("status") in {"completed", "cancelled", "cleaned"}:
        print_json({"run": args.run, "status": metadata.get("status", "")})
        return
    if args.status:
        metadata["status"] = args.status
    metadata["heartbeat_at"] = now_stamp()
    if args.session:
        metadata["tmux_session"] = args.session
    if args.exit_code is not None:
        metadata["last_exit_at"] = now_stamp()
        metadata["exit_code"] = args.exit_code
    write_run_metadata(args.run, metadata)
    print_json(
        {
            "run": args.run,
            "status": metadata.get("status", ""),
            "heartbeat_at": metadata.get("heartbeat_at", ""),
            "tmux_session": metadata.get("tmux_session", ""),
        }
    )


def recover_run_cmd(args: argparse.Namespace) -> None:
    """
    Recover a stale or interrupted run.

    Creates a new recovery run from a stale or interrupted run, updating the
    original run's status to "recovered" and creating a new run with updated
    task status.

    Args:
        args: Namespace with attributes:
            - run: Run ID to recover
            - reason: Recovery reason (default: "manual_recover")
            - dispatch: Whether to auto-dispatch the recovery run
    """
    print_json(recover_run_record(args.run, args.reason or "manual_recover", dispatch=args.dispatch))


def complete_run(args: argparse.Namespace) -> None:
    """
    Mark a run as completed and update task status.

    Processes the completion of a run by:
    - Updating run metadata with result and completion time
    - Updating task status based on run result
    - Recording findings and generating fix requests if needed
    - Capturing reflections in strategy memory
    - Writing handoff notes for the next role
    - Recording completion events

    Args:
        args: Namespace with attributes:
            - run: Run ID to complete
            - result: Run result ("success", "needs_changes", "blocked", "failed")
            - summary: Optional completion summary
            - findings: Optional findings data

    Raises:
        SystemExit: If result is invalid or run ID is unknown
    """
    findings = parse_findings(args)
    print_json(complete_run_record(args.run, args.result, args.summary, findings=findings))


def finalize_run_cmd(args: argparse.Namespace) -> None:
    """
    Finalize a run from an agent result artifact or exit code.

    Processes the completion of a run by reading the agent result file or
    falling back to exit code interpretation.

    Args:
        args: Namespace with attributes:
            - run: Run ID to finalize
            - exit_code: Process exit code
            - result_file: Optional path to agent result file
    """
    print_json(finalize_run_record(args.run, int(args.exit_code), result_file=args.result_file or ""))


def cancel_run(args: argparse.Namespace) -> None:
    """
    Cancel a run and revert task status.

    Marks a run as cancelled, updates the associated task status back to "todo",
    and records the cancellation event.

    Args:
        args: Namespace with attributes:
            - run: Run ID to cancel
            - reason: Optional cancellation reason

    Raises:
        SystemExit: If run ID is unknown or run is already completed
    """
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    if metadata["status"] == "completed":
        raise SystemExit(f"cannot cancel run with status {metadata['status']}")
    reason = args.reason or f"Run {args.run} cancelled."
    metadata["status"] = "cancelled"
    metadata["cancelled_at"] = now_stamp()
    write_json(metadata_path, metadata)
    (run_dir / "summary.md").write_text(f"# Run Summary\n\n{reason}\n", encoding="utf-8")

    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"])
    task["status"] = "todo"
    task.setdefault("notes", []).append({"at": now_stamp(), "note": reason})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated", sync_review_state_callback=sync_review_state)
    record_event(
        metadata["spec"],
        "run.cancelled",
        {
            "run": metadata["id"],
            "task": metadata["task"],
            "role": metadata["role"],
            "reason": reason,
        },
    )
    print_json(
        {
            "run": metadata["id"],
            "task_status": task["status"],
            "cancelled_at": metadata["cancelled_at"],
            "reason": reason,
        }
    )


def show_task_history(args: argparse.Namespace) -> None:
    """
    Display execution history for a specific task.

    Retrieves and prints all runs associated with the given spec and task,
    sorted by creation timestamp. Output is formatted as indented JSON.

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec
            - task: ID of the task to get history for
    """
    print_json(task_run_history(args.spec, args.task))


def cleanup_runs_cmd(args: argparse.Namespace) -> None:
    """
    Clean up stale or manually-selected runs.

    Marks runs as inactive based on specified criteria and updates associated tasks.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug
            - reason: Cleanup reason (default: "manual_cleanup")
            - target_status: Target status for cleaned runs (default: "abandoned")
            - task_status: Optional task status filter
            - include_status: List of statuses to include (default: ["created", "running"])
    """
    import json
    cleaned = []
    tasks = load_tasks(args.spec)
    task_updates = []
    for metadata in active_runs_for_spec(args.spec):
        if metadata.get("status") not in args.include_status:
            continue
        run_dir = RUNS_DIR / metadata["id"]
        run_json = run_dir / "run.json"
        if not run_json.exists():
            continue
        payload = read_json(run_json)
        payload["status"] = args.target_status
        payload["cleanup_at"] = now_stamp()
        payload["cleanup_reason"] = args.reason
        write_json(run_json, payload)
        cleaned.append(metadata["id"])
        task = task_lookup(tasks, payload["task"])
        if task.get("status") == "in_progress":
            fallback_status = args.task_status or ("in_review" if payload.get("role") == "reviewer" else "todo")
            task["status"] = fallback_status
            task.setdefault("notes", []).append(
                {
                    "at": now_stamp(),
                    "note": f"run {metadata['id']} cleaned up; task returned to {fallback_status}",
                }
            )
            task_updates.append({"task": payload["task"], "status": fallback_status})
        record_event(
            args.spec,
            "run.cleaned",
            {"run": metadata["id"], "status": args.target_status, "task": payload["task"]},
        )
    if task_updates:
        save_tasks(args.spec, tasks, reason="run_cleanup", sync_review_state_callback=sync_review_state)
    invalidate_run_cache()
    print(
        json.dumps(
            {
                "spec": args.spec,
                "cleaned_runs": cleaned,
                "target_status": args.target_status,
                "task_updates": task_updates,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def sweep_runs_cmd(args: argparse.Namespace) -> None:
    """
    Detect stale runs and mark or recover them.

    Identifies runs that have not sent a heartbeat within the specified
    time period and marks them as stale or optionally recovers them.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug
            - stale_after: Seconds after which a run is considered stale
            - target_status: Target status for stale runs (default: "stale")
            - task_status: Optional task status filter
            - include_status: List of statuses to check (default: ["created", "running"])
            - auto_recover: Whether to automatically recover stale runs
            - dispatch_recovery: Whether to dispatch recovered runs
    """
    import json
    ensure_state()
    stale_after = max(1, int(args.stale_after))
    tasks = load_tasks(args.spec)
    task_updates = []
    marked_stale = []
    recovered = []

    for metadata in list(run_metadata_iter()):
        if metadata.get("spec") != args.spec:
            continue
        if metadata.get("status") not in args.include_status:
            continue
        reason = run_stale_reason(metadata, stale_after_seconds=stale_after)
        if not reason:
            continue

        if args.auto_recover:
            recovered.append(
                recover_run_record(
                    metadata["id"],
                    reason=f"stale:{reason}",
                    dispatch=args.dispatch_recovery,
                )
            )
            continue

        payload = load_run_metadata(metadata["id"])
        payload["status"] = args.target_status
        payload["stale_at"] = now_stamp()
        payload["stale_reason"] = reason
        write_run_metadata(metadata["id"], payload)
        marked_stale.append(
            {
                "run": metadata["id"],
                "reason": reason,
                "status": args.target_status,
            }
        )
        task = task_lookup(tasks, payload["task"], spec_slug=args.spec)
        if task.get("status") == "in_progress":
            fallback_status = args.task_status or ("in_review" if payload.get("role") == "reviewer" else "todo")
            task["status"] = fallback_status
            task.setdefault("notes", []).append(
                {
                    "at": now_stamp(),
                    "note": f"run {metadata['id']} marked {args.target_status}; task returned to {fallback_status}",
                }
            )
            task_updates.append({"task": payload["task"], "status": fallback_status})
            record_event(
                args.spec,
                "run.stale",
                {"run": metadata["id"], "reason": reason, "task": payload["task"], "status": args.target_status},
            )
    if task_updates:
        save_tasks(args.spec, tasks, reason="run_stale", sync_review_state_callback=sync_review_state)
    invalidate_run_cache()
    print(
        json.dumps(
            {
                "spec": args.spec,
                "marked_stale": marked_stale,
                "recovered": recovered,
                "stale_count": len(marked_stale),
                "recovered_count": len(recovered),
                "task_updates": task_updates,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def list_runs(args: argparse.Namespace) -> None:
    """
    List runs with optional filtering.

    Displays run metadata with optional filters for spec, status, role, and agent.

    Args:
        args: Namespace with attributes:
            - spec: Optional spec slug filter
            - status: Optional status filter
            - role: Optional role filter
            - agent: Optional agent name filter
    """
    ensure_state()
    runs = run_metadata_iter()
    if args.spec:
        runs = [r for r in runs if r.get("spec") == args.spec]
    if args.status:
        runs = [r for r in runs if r.get("status") == args.status]
    if args.role:
        runs = [r for r in runs if r.get("role") == args.role]
    if args.agent:
        runs = [r for r in runs if r.get("agent") == args.agent]
    print_json(
        [
            {
                "id": r.get("id", ""),
                "spec": r.get("spec", ""),
                "task": r.get("task", ""),
                "role": r.get("role", ""),
                "agent": r.get("agent", ""),
                "status": r.get("status", ""),
                "created_at": r.get("created_at", ""),
                "result": r.get("result", ""),
            }
            for r in runs
        ]
    )


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register run command subparsers with the argument parser.

    This function is called during CLI initialization to add all run-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    run_cmd_parser = sub.add_parser("new-run", help="create a runnable agent job")
    run_cmd_parser.add_argument("--spec", required=True)
    run_cmd_parser.add_argument("--role", required=True)
    run_cmd_parser.add_argument("--agent", required=True)
    run_cmd_parser.add_argument("--task")
    run_cmd_parser.add_argument("--branch")
    run_cmd_parser.add_argument("--resume-from")
    run_cmd_parser.set_defaults(func=create_run)

    resume_cmd = sub.add_parser("resume-run", help="create a retry run from an earlier run record")
    resume_cmd.add_argument("--run", required=True)
    resume_cmd.set_defaults(func=resume_run)

    heartbeat_cmd = sub.add_parser("heartbeat-run", help="update run heartbeat metadata")
    heartbeat_cmd.add_argument("--run", required=True)
    heartbeat_cmd.add_argument("--status", default="")
    heartbeat_cmd.add_argument("--session", default="")
    heartbeat_cmd.add_argument("--exit-code", type=int)
    heartbeat_cmd.set_defaults(func=heartbeat_run_cmd)

    recover_cmd = sub.add_parser("recover-run", help="recover a stale or interrupted run")
    recover_cmd.add_argument("--run", required=True)
    recover_cmd.add_argument("--reason", default="manual_recover")
    recover_cmd.add_argument("--dispatch", action="store_true")
    recover_cmd.set_defaults(func=recover_run_cmd)

    complete_cmd = sub.add_parser("complete-run", help="close a run and update task state")
    complete_cmd.add_argument("--run", required=True)
    complete_cmd.add_argument("--result", required=True)
    complete_cmd.add_argument("--summary", default="")
    complete_cmd.add_argument("--findings-json", default="")
    complete_cmd.add_argument("--findings-file", default="")
    complete_cmd.set_defaults(func=complete_run)

    finalize_cmd = sub.add_parser("finalize-run", help="complete a run from an agent result artifact or exit code")
    finalize_cmd.add_argument("--run", required=True)
    finalize_cmd.add_argument("--exit-code", required=True, type=int)
    finalize_cmd.add_argument("--result-file", default="")
    finalize_cmd.set_defaults(func=finalize_run_cmd)

    cancel_cmd = sub.add_parser("cancel-run", help="cancel a run and revert task status")
    cancel_cmd.add_argument("--run", required=True)
    cancel_cmd.add_argument("--reason", default="")
    cancel_cmd.set_defaults(func=cancel_run)

    history_cmd = sub.add_parser("task-history", help="show run history for a task")
    history_cmd.add_argument("--spec", required=True)
    history_cmd.add_argument("--task", required=True)
    history_cmd.set_defaults(func=show_task_history)

    cleanup_runs = sub.add_parser("cleanup-runs", help="mark stale or manual-selected runs as inactive")
    cleanup_runs.add_argument("--spec", required=True)
    cleanup_runs.add_argument("--reason", default="manual_cleanup")
    cleanup_runs.add_argument("--target-status", default="abandoned")
    cleanup_runs.add_argument("--task-status", default="")
    cleanup_runs.add_argument("--include-status", nargs="+", default=["created", "running"])
    cleanup_runs.set_defaults(func=cleanup_runs_cmd)

    sweep_runs = sub.add_parser("sweep-runs", help="detect stale runs and mark or recover them")
    sweep_runs.add_argument("--spec", required=True)
    sweep_runs.add_argument("--stale-after", type=int, default=DEFAULT_STALE_AFTER_SECONDS)
    sweep_runs.add_argument("--target-status", default="stale")
    sweep_runs.add_argument("--task-status", default="")
    sweep_runs.add_argument("--include-status", nargs="+", default=["created", "running"])
    sweep_runs.add_argument("--auto-recover", action="store_true")
    sweep_runs.add_argument("--dispatch-recovery", action="store_true")
    sweep_runs.set_defaults(func=sweep_runs_cmd)

    list_runs_cmd = sub.add_parser("list-runs", help="list runs with optional filtering")
    list_runs_cmd.add_argument("--spec", default="", help="filter by spec slug")
    list_runs_cmd.add_argument("--status", default="", help="filter by run status")
    list_runs_cmd.add_argument("--role", default="", help="filter by role")
    list_runs_cmd.add_argument("--agent", default="", help="filter by agent name")
    list_runs_cmd.set_defaults(func=list_runs)
