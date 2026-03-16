#!/usr/bin/env python3
"""
Autoflow CLI - Control Plane Interface

Provides the command-line interface for managing Autoflow specs, tasks, agents,
and git worktrees. This is the main entry point for interacting with the Autoflow
workflow system.

Features:
    - Spec and task lifecycle management
    - Git worktree isolation for parallel development
    - Agent discovery and configuration
    - Memory and strategy tracking
    - Review and approval workflows
    - Run execution and history tracking

Usage:
    # Initialize Autoflow state
    python scripts/autoflow.py init

    # Create a new spec
    python scripts/autoflow.py new-spec --title "Add Feature" --summary "Description"

    # Show available tasks
    python scripts/autoflow.py list-tasks --spec my-spec

    # Create a worktree for isolated development
    python scripts/autoflow.py create-worktree --spec my-spec

    # Show overall status
    python scripts/autoflow.py status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cli.utils import (
    AGENT_RESULT_FILE,
    AGENTS_FILE,
    BMAD_DIR,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    DEPENDENCIES_DIR,
    DISCOVERY_FILE,
    EVENTS_FILE,
    INACTIVE_RUN_STATUSES,
    LOGS_DIR,
    MEMORY_DIR,
    QA_FIX_REQUEST_FILE,
    QA_FIX_REQUEST_JSON_FILE,
    REPOSITORIES_DIR,
    REVIEW_STATE_FILE,
    ROOT as UTILS_ROOT,
    RUN_LEASE_ACTIVE_STATUSES,
    RUN_RESULTS,
    RUNS_DIR,
    SPECS_DIR,
    STATE_DIR,
    STRATEGY_MEMORY_DIR,
    SYSTEM_CONFIG_FILE,
    SYSTEM_CONFIG_TEMPLATE,
    TASKS_DIR,
    VALID_TASK_STATUSES,
    WORKTREES_DIR,
    _agents_config_cache,
    _cache_loaded_specs,
    _populate_agents_cache,
    _populate_run_cache,
    _populate_run_cache_for_spec,
    _run_metadata_cache,
    append_memory,
    compute_file_hash,
    compute_spec_hash,
    deep_merge,
    ensure_state,
    ensure_state as ensure_state_dirs,
    increment_counter,
    invalidate_agents_cache,
    invalidate_run_cache,
    invalidate_system_config_cache,
    invalidate_tasks_cache,
    load_agent_result_payload,
    load_agents,
    load_memory_context,
    load_review_state,
    load_run_metadata,
    load_spec_metadata,
    load_strategy_memory,
    load_system_config,
    load_tasks,
    memory_file,
    now_stamp,
    now_utc,
    parse_stamp,
    planning_contract,
    print_json,
    read_json,
    read_json_or_default,
    record_event,
    resolve_agent_profiles,
    resolve_root_path,
    review_state_default,
    review_status_summary,
    run_cmd,
    run_is_stale,
    run_last_activity,
    run_metadata_path,
    run_stale_reason,
    save_review_state,
    save_spec_metadata,
    save_strategy_memory,
    save_tasks,
    slugify,
    spec_dir,
    spec_files,
    stale_runs_for_spec,
    strategy_memory_default,
    strategy_memory_file,
    sync_review_state,
    system_config_default,
    task_file,
    tmux_session_exists,
    validate_slug_safe,
    worktree_branch,
    worktree_path,
    write_json,
    write_run_metadata,
)
# Import agent-related utilities
from scripts.cli.utils import (
    AgentSpec,
    invalidate_agents_cache,
    load_agent_result_payload,
    load_agents,
    normalize_findings,
    resolve_agent_profiles,
    _agents_config_cache,
    _populate_agents_cache,
)
# Import modular CLI modules
from scripts.cli import worktree
from scripts.cli import memory
from scripts.cli import review
from scripts.cli import agent
from scripts.cli import system
from scripts.cli import integration
from scripts.cli import spec
from scripts.cli import task
from scripts.cli import run
from scripts.cli import repository
from scripts.integrity import hash_file_content, verify_file_integrity
from autoflow.core.sanitization import sanitize_dict, sanitize_value


def repository_manager():
    """Load RepositoryManager only when repository features are used."""
    from autoflow.core.repository import RepositoryManager

    return RepositoryManager(STATE_DIR)


def derive_strategy_actions(
    role: str,
    result: str,
    findings: list[dict[str, Any]],
    stats: dict[str, Any],
) -> list[str]:
    """
    Derive strategic actions from review findings and statistics.

    Analyzes review findings, result status, and historical statistics to generate
    actionable recommendations for improving future work. Considers severity levels,
    categories, file paths, and recurring patterns.

    Args:
        role: Agent role (e.g., "implementation-runner", "maintainer")
        result: Review result status (e.g., "success", "needs_changes", "blocked", "failed")
        findings: List of review findings with category, severity, and file metadata
        stats: Historical statistics including finding_categories and file counts

    Returns:
        List of strategic action recommendations based on the analysis
    """
    actions: list[str] = []
    categories = {finding.get("category", "") for finding in findings if finding.get("category")}
    severities = {finding.get("severity", "") for finding in findings if finding.get("severity")}
    files = [finding.get("file", "") for finding in findings if finding.get("file")]

    if any(level in severities for level in {"critical", "high"}):
        actions.append("Address the highest-severity findings before broad refactors or new features.")
    if "tests" in categories or any("test" in path.lower() for path in files):
        actions.append("Add or update a regression test before sending the task back to review.")
    if "workflow" in categories or "infra" in categories:
        actions.append("Re-run the relevant control-plane command locally before retrying the task.")
    if result in {"needs_changes", "blocked", "failed"}:
        actions.append("Start the retry from the structured fix request instead of reusing the prior edit plan.")
    if role in {"implementation-runner", "maintainer"} and result == "success":
        actions.append("Keep the validated edit path small and capture the exact verification steps in the handoff.")

    recurring_categories = [
        category
        for category, count in stats.get("finding_categories", {}).items()
        if count >= 2
    ]
    if recurring_categories:
        actions.append(
            "Review recurring blocker categories first: " + ", ".join(sorted(recurring_categories))
        )
    return actions


def rebuild_playbook(memory: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Rebuild a playbook from memory statistics.

    Generates actionable rules based on historical finding categories and file hotspots.
    Prioritizes rules by evidence count and includes special handling for tests
    and workflow categories. Returns the top 8 rules.

    Args:
        memory: Strategy memory dictionary containing stats with finding_categories
                and files counts

    Returns:
        List of playbook entries sorted by evidence count (highest first).
        Each entry contains category/file, evidence_count, and a rule string.
        Maximum 8 entries.
    """
    playbook: list[dict[str, Any]] = []
    for category, count in sorted(
        memory.get("stats", {}).get("finding_categories", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        rule = f"Before retrying work that touches {category}, review prior findings and front-load verification."
        if category == "tests":
            rule = "If tests-related findings recur, write the regression test before or alongside the fix."
        elif category == "workflow":
            rule = "If workflow findings recur, validate control-plane commands and state transitions before code edits."
        playbook.append(
            {
                "category": category,
                "evidence_count": count,
                "rule": rule,
            }
        )
    for file_path, count in sorted(
        memory.get("stats", {}).get("files", {}).items(),
        key=lambda item: (-item[1], item[0]),
    ):
        if count < 2:
            continue
        playbook.append(
            {
                "file": file_path,
                "evidence_count": count,
                "rule": f"Treat {file_path} as a hotspot and review existing findings before editing it again.",
            }
        )
    return playbook[:8]


def record_reflection(
    spec_slug: str,
    run_metadata: dict[str, Any],
    result: str,
    summary: str,
    findings: list[dict[str, Any]] | None = None,
) -> list[Path]:
    """
    Record a task run reflection into strategy memory.

    Captures reflection data including run metadata, results, summary, and findings.
    Updates both global and spec-scoped strategy memory with statistics and
    maintains a rolling history of the last 25 reflections. Automatically rebuilds
    the strategy playbook based on accumulated reflections.

    Args:
        spec_slug: Spec identifier for scoping the reflection
        run_metadata: Dictionary containing run metadata (id, task, role, etc.)
        result: Run result status (e.g., "success", "needs_changes", "blocked", "failed")
        summary: Text summary of the reflection
        findings: Optional list of finding dictionaries with category, severity, file

    Returns:
        List of paths to updated strategy memory files (global and spec)

    Example:
        >>> metadata = {"id": "run-123", "task": "task-1", "role": "developer"}
        >>> findings = [{"category": "bug", "severity": "high", "file": "src/main.py"}]
        >>> paths = record_reflection("my-spec", metadata, "success", "All tests passed", findings)
        >>> print(f"Updated {len(paths)} memory files")
        Updated 2 memory files
    """
    normalized = (
        normalize_findings(summary, findings)
        if findings or result in {"needs_changes", "blocked", "failed"}
        else []
    )
    updated_paths: list[Path] = []
    for scope in ["global", "spec"]:
        memory = load_strategy_memory(scope, spec_slug if scope == "spec" else None)
        stats = memory.setdefault(
            "stats",
            {
                "by_role": {},
                "by_result": {},
                "finding_categories": {},
                "severity": {},
                "files": {},
            },
        )
        increment_counter(stats.setdefault("by_role", {}), run_metadata.get("role", "unknown"))
        increment_counter(stats.setdefault("by_result", {}), result)
        for finding in normalized:
            increment_counter(stats.setdefault("finding_categories", {}), finding.get("category", "general"))
            increment_counter(stats.setdefault("severity", {}), finding.get("severity", "medium"))
            increment_counter(stats.setdefault("files", {}), finding.get("file", ""))
        reflection = {
            "at": now_stamp(),
            "run": run_metadata.get("id", ""),
            "task": run_metadata.get("task", ""),
            "role": run_metadata.get("role", ""),
            "result": result,
            "summary": summary,
            "findings": normalized,
            "recommended_actions": derive_strategy_actions(
                run_metadata.get("role", ""),
                result,
                normalized,
                stats,
            ),
        }
        reflections = memory.setdefault("reflections", [])
        reflections.append(reflection)
        memory["reflections"] = reflections[-25:]
        memory["playbook"] = rebuild_playbook(memory)
        updated_paths.append(save_strategy_memory(scope, memory, spec_slug if scope == "spec" else None))
    return updated_paths


def add_planner_note(
    spec_slug: str,
    title: str,
    content: str,
    category: str = "strategy",
    scope: str = "spec",
) -> Path:
    """
    Add a planner note to strategy memory.

    Planner notes are free-form annotations for tracking strategic decisions,
    observations, or guidance. Notes are timestamped and categorized, with the
    last 25 notes retained in memory. Notes can be scoped globally or to a
    specific spec.

    Args:
        spec_slug: Spec identifier for scoping the note
        title: Short title describing the note
        content: Detailed content of the note
        category: Category for organizing notes (default: "strategy")
        scope: Memory scope - "global" or "spec" (default: "spec")

    Returns:
        Path to the updated strategy memory file

    Example:
        >>> path = add_planner_note(
        ...     "my-spec",
        ...     "Architecture Decision",
        ...     "Use PostgreSQL for the primary database",
        ...     category="architecture"
        ... )
        >>> print(f"Note saved to {path}")
    """
    memory = load_strategy_memory(scope, spec_slug if scope == "spec" else None)
    notes = memory.setdefault("planner_notes", [])
    notes.append(
        {
            "at": now_stamp(),
            "title": title,
            "category": category,
            "content": content.strip(),
        }
    )
    memory["planner_notes"] = notes[-25:]
    return save_strategy_memory(scope, memory, spec_slug if scope == "spec" else None)


def strategy_summary(spec_slug: str) -> dict[str, Any]:
    """
    Generate a summary of strategy memory for a spec.

    Loads the strategy memory for the given spec and extracts the most relevant
    information including playbook entries, planner notes, recent reflections,
    and statistics.

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Dictionary containing:
            - updated_at: Last update timestamp
            - playbook: List of playbook rules with evidence
            - planner_notes: Last 5 planner notes with metadata
            - recent_reflections: Last 5 reflection entries
            - stats: Strategy statistics and metrics
    """
    spec_memory = load_strategy_memory("spec", spec_slug)
    recent = spec_memory.get("reflections", [])[-5:]
    return {
        "updated_at": spec_memory.get("updated_at", ""),
        "playbook": spec_memory.get("playbook", []),
        "planner_notes": spec_memory.get("planner_notes", [])[-5:],
        "recent_reflections": recent,
        "stats": spec_memory.get("stats", {}),
    }


def render_strategy_context(spec_slug: str) -> str:
    """
    Render strategy memory as formatted markdown for context injection.

    Generates a markdown representation of strategy memory for use in prompts
    and context windows. Includes playbook entries, planner notes, and recent
    reflections with their recommended actions.

    The output includes:
    - Playbook: Top 5 rules with evidence counts
    - Planner notes: Last 3 notes with titles and categories
    - Recent reflections: Last 3 reflections with outcomes and actions

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Formatted markdown string containing strategy context, or a message
        indicating no strategy memory has been recorded yet
    """
    summary = strategy_summary(spec_slug)
    lines = ["## Strategy memory", ""]
    playbook = summary.get("playbook", [])
    if playbook:
        lines.append("### Playbook")
        lines.append("")
        for item in playbook[:5]:
            target = item.get("category") or item.get("file") or "general"
            lines.append(f"- {target}: {item['rule']} (evidence={item['evidence_count']})")
        lines.append("")
    notes = summary.get("planner_notes", [])
    if notes:
        lines.append("### Planner notes")
        lines.append("")
        for note in notes[-3:]:
            lines.append(f"- {note['title']} [{note['category']}]")
            lines.append(f"  {note['content']}")
        lines.append("")
    reflections = summary.get("recent_reflections", [])
    if reflections:
        lines.append("### Recent reflections")
        lines.append("")
        for item in reflections[-3:]:
            lines.append(
                f"- {item['task']} / {item['role']} -> {item['result']}: {item['summary']}"
            )
            for action in item.get("recommended_actions", [])[:2]:
                lines.append(f"  action: {action}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("No strategy memory recorded yet.")
    return "\n".join(lines).strip()


def parse_dependency_ref(dep_ref: str) -> tuple[str | None, str]:
    """
    Parse a dependency reference into (repository_id, task_id).

    Args:
        dep_ref: Dependency reference, either "task-id" or "repo-id/task-id"

    Returns:
        Tuple of (repository_id, task_id). repository_id is None for same-repo deps.

    Examples:
        >>> parse_dependency_ref("T1")
        (None, 'T1')
        >>> parse_dependency_ref("backend/T1")
        ('backend', 'T1')
    """
    if "/" in dep_ref:
        parts = dep_ref.split("/", 1)
        return parts[0], parts[1]
    return None, dep_ref


def load_tasks_from_repository(repository_id: str, spec_slug: str) -> dict[str, Any]:
    """
    Load tasks from a spec in another repository.

    Args:
        repository_id: Repository ID containing the spec
        spec_slug: Spec slug to load tasks from

    Returns:
        Tasks data dictionary

    Raises:
        SystemExit: If repository or task file doesn't exist
    """
    # Validate repository exists
    repo_manager = repository_manager()
    if not repo_manager.repository_exists(repository_id):
        raise SystemExit(
            f"cannot load dependency: repository '{repository_id}' not found"
        )

    # Load repository configuration
    repo_data = repo_manager.load_repository(repository_id)
    if not repo_data:
        raise SystemExit(f"cannot load dependency: repository '{repository_id}' not found")

    # Resolve repository path
    from autoflow.core.repository import Repository
    repo = Repository(**repo_data)
    repo_path = repo.get_resolved_path()

    # Construct path to task file in other repository
    other_tasks_file = repo_path / ".autoflow" / "tasks" / f"{spec_slug}.json"

    if not other_tasks_file.exists():
        raise SystemExit(
            f"cannot load dependency: task file not found for spec '{spec_slug}' "
            f"in repository '{repository_id}' at {other_tasks_file}"
        )

    return read_json(other_tasks_file)


def task_lookup(data: dict[str, Any], task_id: str, spec_slug: str | None = None) -> dict[str, Any]:
    """
    Look up a task by ID, supporting cross-repository references.

    Args:
        data: Current spec's tasks data
        task_id: Task ID, either "T1" or "repo-id/spec-slug/T1"
        spec_slug: Current spec slug (required for cross-repo lookups)

    Returns:
        Task dictionary

    Raises:
        SystemExit: If task is not found
    """
    # Check if this is a cross-repo reference (format: repo-id/spec-slug/task-id)
    if task_id.count("/") >= 2:
        parts = task_id.split("/")
        repo_id = parts[0]
        other_spec_slug = parts[1]
        other_task_id = "/".join(parts[2:])  # Handle case where task ID contains /

        # Load tasks from other repository
        other_tasks = load_tasks_from_repository(repo_id, other_spec_slug)
        for task in other_tasks.get("tasks", []):
            if task["id"] == other_task_id:
                return task
        raise SystemExit(
            f"unknown task: {task_id} (in spec '{other_spec_slug}' "
            f"in repository '{repo_id}')"
        )

    # Same-repo lookup
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            return task
    raise SystemExit(f"unknown task: {task_id}")


def replace_markdown_section(markdown: str, heading: str, content: str) -> str:
    lines = markdown.splitlines()
    target = f"## {heading}".strip()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == target:
            start = index
            break
    if start is None:
        return markdown.rstrip() + f"\n\n## {heading}\n\n{content.strip()}\n"
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    replacement = [target, "", content.strip()]
    new_lines = lines[:start] + replacement + lines[end:]
    return "\n".join(new_lines).rstrip() + "\n"


def normalize_worktree_metadata(spec_slug: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(metadata or load_spec_metadata(spec_slug))
    worktree = dict(payload.get("worktree", {}))
    expected = worktree_path(spec_slug)
    current_path = worktree.get("path", "")
    branch = worktree.get("branch", worktree_branch(spec_slug))
    base_branch = worktree.get("base_branch", detect_base_branch())
    resolved_path = ""
    if expected.exists():
        resolved_path = str(expected)
    elif current_path:
        current = Path(current_path)
        if current.exists():
            resolved_path = str(current)
    payload["worktree"] = {
        "path": resolved_path,
        "branch": branch,
        "base_branch": base_branch,
    }
    return payload


def load_events(spec_slug: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Load events from the spec's event log.

    Reads the events.jsonl file and returns the most recent events.
    Events are stored in reverse chronological order (newest last),
    so the last N lines are retrieved.

    Args:
        spec_slug: Slug identifier for the spec
        limit: Maximum number of events to return (default: 20)

    Returns:
        List of event dictionaries, each containing:
        - "at": UTC timestamp string
        - "type": Event type identifier
        - "payload": Event-specific data dictionary

        Returns empty list if the event log doesn't exist.
    """
    events_path = spec_files(spec_slug)["events"]
    if not events_path.exists():
        return []
    with open(events_path, encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def load_fix_request(spec_slug: str) -> str:
    """
    Load the QA fix request markdown file for a spec.

    Reads the fix request markdown file that contains structured feedback
    for implementation revisions. Returns an empty string if the file doesn't exist.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Contents of the fix request markdown file, or empty string if not found

    Examples:
        >>> content = load_fix_request("my-feature")
        >>> print(content[:50])
        # QA Fix Request: task-001
    """
    path = spec_files(spec_slug)["qa_fix_request"]
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_fix_request_data(spec_slug: str) -> dict[str, Any]:
    """
    Load the QA fix request JSON data for a spec.

    Reads the structured JSON data that contains the fix request payload including
    task ID, result status, summary, and normalized findings. Returns a default
    empty structure if the file doesn't exist.

    Args:
        spec_slug: Slug identifier for the spec

    Returns:
        Dictionary containing fix request data with keys:
        - task: Task ID string
        - result: Review result status
        - summary: Reviewer summary text
        - finding_count: Number of findings
        - findings: List of normalized finding dictionaries
        Returns default empty structure if file not found.

    Examples:
        >>> data = load_fix_request_data("my-feature")
        >>> data["finding_count"]
        3
        >>> len(data["findings"])
        3
    """
    return read_json_or_default(
        spec_files(spec_slug)["qa_fix_request_json"],
        {"task": "", "result": "", "summary": "", "finding_count": 0, "findings": []},
    )


def format_fix_request_markdown(task_id: str, summary: str, result: str, findings: list[dict[str, Any]]) -> str:
    """
    Format a QA fix request as structured markdown.

    Generates a comprehensive markdown document containing review findings in a
    structured format suitable for developer review and implementation revisions.
    Includes a summary table, detailed findings with metadata, and retry policy.

    Args:
        task_id: Identifier for the task requiring fixes
        summary: High-level summary of the review feedback
        result: Review result status (e.g., "needs_changes", "blocked")
        findings: List of normalized finding dictionaries

    Returns:
        Formatted markdown string with sections:
        - Header with task ID and metadata
        - Summary section with overall feedback
        - Findings table with ID, severity, category, file, line, and title
        - Details section with full information for each finding
        - Retry policy section with guidance for implementation

    Examples:
        >>> findings = [
        ...     {
        ...         "id": "F1",
        ...         "title": "Add tests",
        ...         "severity": "high",
        ...         "category": "tests",
        ...         "file": "src/test.py",
        ...         "line": 42,
        ...         "end_line": 50,
        ...         "body": "Add unit tests for edge cases",
        ...         "suggested_fix": "Add tests in test suite",
        ...         "source_run": "run-123"
        ...     }
        ... ]
        >>> markdown = format_fix_request_markdown("task-001", "Tests needed", "needs_changes", findings)
        >>> print(markdown[:100])
        # QA Fix Request: task-001
        <BLANKLINE>
        - created_at: 20260309T120000Z
        - result: needs_changes
    """
    lines = [
        f"# QA Fix Request: {task_id}",
        "",
        f"- created_at: {now_stamp()}",
        f"- result: {result}",
        f"- finding_count: {len(findings)}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Findings",
        "",
        "| ID | Severity | Category | File | Line | Title |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for finding in findings:
        line_display = ""
        if finding.get("line") is not None:
            line_display = str(finding["line"])
            if finding.get("end_line") is not None and finding["end_line"] != finding["line"]:
                line_display = f"{line_display}-{finding['end_line']}"
        lines.append(
            f"| {finding['id']} | {finding['severity']} | {finding['category']} | "
            f"{finding.get('file', '')} | {line_display} | {finding['title']} |"
        )
    lines.extend(["", "## Details", ""])
    for finding in findings:
        lines.extend(
            [
                f"### {finding['id']}: {finding['title']}",
                "",
                f"- severity: {finding['severity']}",
                f"- category: {finding['category']}",
                f"- file: {finding.get('file', '')}",
                f"- line: {finding.get('line', '')}",
                f"- end_line: {finding.get('end_line', '')}",
                f"- suggested_fix: {finding.get('suggested_fix', '')}",
                f"- source_run: {finding.get('source_run', '')}",
                "",
                finding["body"],
                "",
            ]
        )
    lines.extend(
        [
            "## Retry policy",
            "",
            "- Read this file before retrying the implementation task.",
            "- Address findings in severity order where possible.",
            "- Change approach instead of repeating the same edits.",
            "- Leave a handoff note explaining what changed in the retry.",
            "",
        ]
    )
    return "\n".join(lines)


def write_fix_request(
    spec_slug: str,
    task_id: str,
    reviewer_summary: str,
    result: str,
    findings: list[dict[str, Any]] | None = None,
) -> Path:
    """
    Write a QA fix request to both markdown and JSON files.

    Creates structured fix request documentation by normalizing findings, formatting
    them as markdown, and saving both human-readable (markdown) and machine-readable
    (JSON) versions. Records an event in the spec's event log.

    Args:
        spec_slug: Slug identifier for the spec
        task_id: Identifier for the task requiring fixes
        reviewer_summary: High-level summary of the review feedback
        result: Review result status (e.g., "needs_changes", "blocked")
        findings: List of finding dictionaries from review, or None for a default finding

    Returns:
        Path to the written markdown fix request file

    Side Effects:
        - Creates/overwrites QA_FIX_REQUEST.md file in spec directory
        - Creates/overwrites QA_FIX_REQUEST.json file in spec directory
        - Records "qa.fix_request_created" event in spec's event log

    Examples:
        >>> findings = [
        ...     {"title": "Fix typo", "severity": "low", "category": "style"}
        ... ]
        >>> path = write_fix_request("my-feature", "task-001", "Minor fixes needed", "needs_changes", findings)
        >>> path.name
        'QA_FIX_REQUEST.md'
        >>> path.exists()
        True
    """
    path = spec_files(spec_slug)["qa_fix_request"]
    json_path = spec_files(spec_slug)["qa_fix_request_json"]
    normalized = normalize_findings(reviewer_summary, findings)
    payload = {
        "task": task_id,
        "result": result,
        "summary": reviewer_summary,
        "created_at": now_stamp(),
        "finding_count": len(normalized),
        "findings": normalized,
    }
    content = format_fix_request_markdown(task_id, reviewer_summary, result, normalized)
    content = "\n".join(
        [content]
    )
    path.write_text(content, encoding="utf-8")
    write_json(json_path, payload)
    record_event(
        spec_slug,
        "qa.fix_request_created",
        {"task": task_id, "result": result, "finding_count": len(normalized)},
    )
    return path


def clear_fix_request(spec_slug: str) -> None:
    """
    Remove QA fix request files for a spec.

    Deletes both the markdown and JSON fix request files if they exist.
    Records an event in the spec's event log if any files were removed.

    Args:
        spec_slug: Slug identifier for the spec

    Side Effects:
        - Deletes QA_FIX_REQUEST.md file if it exists
        - Deletes QA_FIX_REQUEST.json file if it exists
        - Records "qa.fix_request_cleared" event in spec's event log if any files were removed

    Examples:
        >>> clear_fix_request("my-feature")
        >>> # Files are removed if they existed
    """
    paths = [
        spec_files(spec_slug)["qa_fix_request"],
        spec_files(spec_slug)["qa_fix_request_json"],
    ]
    removed = False
    for path in paths:
        if path.exists():
            path.unlink()
            removed = True
    if removed:
        record_event(spec_slug, "qa.fix_request_cleared", {})


def detect_base_branch() -> str:
    """
    Detect the git repository's base branch.

    Attempts to identify the primary branch by checking for common branch names
    (main, master) in order. Falls back to the current branch if neither is found,
    or defaults to "main" as a last resort.

    Returns:
        Name of the detected base branch ("main", "master", or current branch)
    """
    for branch in ["main", "master"]:
        result = run_cmd(["git", "rev-parse", "--verify", branch], check=False)
        if result.returncode == 0:
            return branch
    current = run_cmd(["git", "branch", "--show-current"]).stdout.strip()
    return current or "main"


def load_bmad_template(role: str) -> str:
    """
    Load a BMAD (Behavioral Model for Agent Development) template for a specific role.

    BMAD templates provide role-specific guidance and instructions for agents.
    Templates are stored as markdown files in the templates/bmad directory,
    with filenames matching the role name.

    Args:
        role: The role name to load the template for (e.g., "developer", "reviewer")

    Returns:
        The template content as a string, or a message indicating no template
        is configured for the requested role
    """
    path = BMAD_DIR / f"{role}.md"
    if not path.exists():
        return "No BMAD template configured for this role."
    return path.read_text(encoding="utf-8")


def native_resume_preview(agent: AgentSpec) -> list[str]:
    """
    Build command preview for native resume mode.

    Constructs the command line arguments needed to resume a previous session
    using the agent's native resume capability. Supports different resume modes:
    - "subcommand": Uses a dedicated resume subcommand (e.g., "claude resume")
    - "args": Passes resume arguments directly to the main command
    - Other modes: Returns empty list (no native resume)

    Args:
        agent: Agent specification containing resume configuration

    Returns:
        List of command arguments for native resume, or empty list if resume
        is not configured or mode is not supported. Includes "<prompt>" as
        a placeholder for the actual prompt content.

    Example:
        >>> agent = AgentSpec(
        ...     name="claude",
        ...     command="claude",
        ...     resume={"mode": "subcommand", "subcommand": "continue", "args": []}
        ... )
        >>> native_resume_preview(agent)
        ['claude', '--print', 'continue', '<prompt>']
    """
    if not agent.resume:
        return []
    mode = agent.resume.get("mode", "none")
    resume_args = list(agent.resume.get("args", []))
    if mode == "subcommand":
        return [agent.command, *agent.args, agent.resume.get("subcommand", "resume"), *resume_args, "<prompt>"]
    if mode == "args":
        return [agent.command, *agent.args, *resume_args, "<prompt>"]
    return []


def discover_cli_agent(name: str, command: str) -> dict[str, Any] | None:
    """
    Discover a CLI agent by checking command availability and capabilities.

    Attempts to locate the specified command on the system PATH and analyzes
    its help output to determine supported capabilities. This enables automatic
    detection of agent features like resume support and model selection flags.

    Detection capabilities:
    - resume: Checks for "resume" or "--continue" in help text
    - model_flag: Checks for "--model" or " -m," in help text

    Args:
        name: Identifier name for the agent (e.g., "claude", "codex")
        command: Executable command to search for (e.g., "claude", "codex")

    Returns:
        Dictionary containing discovered agent information with keys:
        - name: Agent identifier
        - protocol: Always "cli" for this function
        - command: The command string
        - path: Full path to the executable
        - capabilities: Dict of boolean flags (resume, model_flag)

        Returns None if the command is not found on PATH.

    Example:
        >>> agent = discover_cli_agent("claude", "claude")
        >>> if agent:
        ...     print(agent["path"])
        ...     print(agent["capabilities"]["resume"])
    """
    executable = shutil.which(command)
    if not executable:
        return None
    help_result = run_cmd([command, "--help"], check=False)
    help_text = (help_result.stdout or "") + (help_result.stderr or "")
    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }
    protocol = "cli"
    return {
        "name": name,
        "protocol": protocol,
        "command": command,
        "path": executable,
        "capabilities": capabilities,
    }


def discover_agents_registry() -> dict[str, Any]:
    """
    Discover all available agents from CLI and system configuration registry.

    Performs comprehensive agent discovery by:
    1. Checking for CLI-based agents (codex, claude) on the system PATH
    2. Loading additional agents from the system config registry (ACP protocol)

    CLI agents are discovered by probing for executable commands and their
    capabilities. Registry agents are loaded from the system configuration's
    registry.acp_agents section, which typically contains ACP (Agent Control
    Protocol) agents with custom transport configurations.

    The discovery results are cached to DISCOVERY_FILE for persistence and
    returned with metadata about when the discovery was performed.

    Returns:
        Dictionary containing:
        - discovered_at: ISO 8601 timestamp of when discovery was performed
        - agents: List of discovered agent dictionaries, each containing:
            - name: Agent identifier
            - protocol: "cli" or "acp"
            - command/path (for CLI agents)
            - transport (for ACP agents)
            - capabilities: Dict of supported features
        - system_config: Relevant sections from system config including:
            - memory: Memory configuration
            - models: Model profiles
            - tools: Tool configurations

    Side Effects:
        Writes discovery results to DISCOVERY_FILE (discovered_agents.json)

    Example:
        >>> registry = discover_agents_registry()
        >>> print(f"Found {len(registry['agents'])} agents")
        >>> for agent in registry['agents']:
        ...     print(f"  - {agent['name']} ({agent['protocol']})")
    """
    config = load_system_config()
    discovered = []
    for name, command in [("codex", "codex"), ("claude", "claude")]:
        item = discover_cli_agent(name, command)
        if item:
            discovered.append(item)
    for agent in config.get("registry", {}).get("acp_agents", []):
        discovered.append(
            {
                "name": agent.get("name", "acp-agent"),
                "protocol": "acp",
                "transport": agent.get("transport", {}),
                "capabilities": agent.get("capabilities", {}),
            }
        )
    payload = {
        "discovered_at": now_stamp(),
        "agents": discovered,
        "system_config": {
            "memory": config.get("memory", {}),
            "models": config.get("models", {}),
            "tools": config.get("tools", {}),
        },
    }
    write_json(DISCOVERY_FILE, payload)
    return payload


def discovered_agent_to_config(agent: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a discovered agent registry entry into an Autoflow agent configuration.

    Converts agent discovery data into the standard Autoflow agent configuration format,
    handling both ACP (Agent Communication Protocol) agents and CLI agents. For CLI
    agents, configures resume behavior based on agent capabilities.

    Args:
        agent: Discovered agent metadata from the agent registry. Contains protocol,
            command, name, capabilities, and optional transport configuration.

    Returns:
        A dictionary with agent configuration including:
        - protocol: "acp" or "cli"
        - command: Command to run the agent
        - args: List of command arguments (typically empty)
        - transport: Transport config for ACP agents
        - resume: Resume configuration for CLI agents with resume capability
        - memory_scopes: List of memory scopes (defaults to ["spec"])
    """
    if agent.get("protocol") == "acp":
        return {
            "protocol": "acp",
            "command": agent.get("transport", {}).get("command", agent.get("name", "acp-agent")),
            "args": [],
            "transport": agent.get("transport", {}),
            "memory_scopes": ["spec"],
        }
    resume = None
    if agent.get("name") == "codex" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "subcommand", "subcommand": "resume", "args": ["--last"]}
    elif agent.get("name") == "claude" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "args", "args": ["--continue"]}
    return {
        "protocol": "cli",
        "command": agent.get("command", agent.get("name", "")),
        "args": [],
        "resume": resume,
        "memory_scopes": ["spec"],
    }


# ============================================================================
# CONFIG FILE WRITE LOCATIONS - For Cache Invalidation
# ============================================================================
#
# This section documents all locations where config files are written.
# Cache invalidation (invalidate_config_cache) must be called after each write.
#
# SYSTEM_CONFIG_FILE (system.json) write locations:
#   - Line 4025: init_system_config() function
#     Command: python3 scripts/autoflow.py init-system-config
#     Purpose: Initialize system configuration with defaults
#
# AGENTS_FILE (agents.json) write locations:
#   - Line 2372: sync_discovered_agents() function
#     Command: python3 scripts/autoflow.py sync-agents [--overwrite]
#     Purpose: Sync agents from discovery registry into agents.json
#
# No other write operations to SYSTEM_CONFIG_FILE or AGENTS_FILE found.
#
# ============================================================================


def sync_discovered_agents(overwrite: bool = False) -> dict[str, Any]:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into agents.json, preserving existing
    agent configurations by default. Can optionally overwrite existing entries.
    Creates the agents file with default structure if it doesn't exist.

    Args:
        overwrite: If True, replace existing agent configurations with discovered
            ones. If False, preserve existing configurations and only add new agents.

    Returns:
        A dictionary containing sync results:
        - agents_file: Path to the agents.json file
        - added: List of agent names that were added or updated
        - total_agents: Total number of agents after sync
    """
    ensure_state()
    discovered = discover_agents_registry()
    existing = {"defaults": {"workspace": ".", "shell": "bash"}, "agents": {}}
    if AGENTS_FILE.exists():
        existing = read_json_or_default(AGENTS_FILE, existing)
        existing.setdefault("defaults", {"workspace": ".", "shell": "bash"})
        existing.setdefault("agents", {})
    merged = dict(existing["agents"])
    added = []
    for agent in discovered.get("agents", []):
        name = agent["name"]
        if name in merged and not overwrite:
            continue
        merged[name] = discovered_agent_to_config(agent)
        added.append(name)
    payload = {"defaults": existing["defaults"], "agents": merged}
    # NOTE: This writes to AGENTS_FILE (agents.json)
    # Cache invalidation required: call invalidate_config_cache() after this write
    write_json(AGENTS_FILE, payload)
    invalidate_config_cache()
    return {
        "agents_file": str(AGENTS_FILE),
        "added": added,
        "total_agents": len(merged),
    }

# ============================================================================
# RUN METADATA CACHING STRATEGY
# ============================================================================
#
# Problem: The original implementation scanned ALL run directories in O(n) time
# for every call to run_metadata_iter(), active_runs_for_spec(), and
# task_run_history(). With many runs, this caused significant performance
# degradation, especially when these functions were called repeatedly.
#
# Solution: Implemented a lazy-loading cache indexed by spec_slug:
#
#   1. Cache Structure:
#      - _run_metadata_cache: dict[spec_slug, list[run_metadata]]
#      - _cache_loaded_specs: set[spec_slug] tracks which specs are cached
#
#   2. Lazy Loading:
#      - Runs are only loaded from disk when first requested
#      - Subsequent calls return cached data from memory (O(1) lookup)
#      - When loading runs for one spec, we opportunistically cache all
#        specs encountered during the filesystem scan (amortized O(1))
#
#   3. Cache Invalidation:
#      - Cache is invalidated by calling invalidate_run_cache()
#      - Called after creating new runs (create_run_record)
#      - This ensures cache consistency when runs are modified
#      - Invalidation is simple: clear all cached data (safe and correct)
#
#   4. Performance Impact:
#      - First call: O(n) filesystem scan (same as before)
#      - Subsequent calls: O(1) memory lookup (vs O(n) scan)
#      - Typical speedup: 2x+ for repeated calls
#
# ============================================================================


def invalidate_config_cache() -> None:
    """Invalidate all configuration caches.

    Call this function whenever any configuration is modified to ensure
    all caches remain consistent with the filesystem state. This is a
    comprehensive invalidation that clears both system and agents caches.

    Cache Invalidation Strategy:
        - Comprehensive: clears all config-related caches
        - Safe: ensures cache consistency after any config modification
        - Lazy: data is reloaded on next access (not immediately)
        - Called by: commands that modify system or agents configuration

    Note: Configuration modifications are rare (e.g., init-system-config,
    sync-agents), so aggressive invalidation is acceptable. The caches will
    be repopulated on the next access.
    """
    invalidate_system_config_cache()
    invalidate_agents_cache()


def run_metadata_iter() -> list[dict[str, Any]]:
    """Return all run metadata using a lazy-loaded cache.

    Performance Characteristics:
        - First call: O(n) filesystem scan to load all run metadata
        - Subsequent calls: O(m) where m = number of cached specs (typically O(1))
        - Previous uncached implementation: O(n) filesystem scan on EVERY call

    Cache Behavior:
        This function uses an in-memory cache indexed by spec_slug to avoid
        repeated O(n) filesystem scans. On first call, it loads all runs via
        _populate_run_cache(). Subsequent calls return the cached data directly
        from memory, which is much faster than scanning the filesystem.

        The cache is automatically invalidated when runs are created or modified
        (see invalidate_run_cache() in create_run_record()).

    Returns:
        A list of run metadata dictionaries, sorted by run directory name.
    """
    # Ensure all specs are loaded into cache (lazy-load on first call)
    _populate_run_cache()

    # Flatten the cache into a single list
    items = []
    for spec_runs in _run_metadata_cache.values():
        items.extend(spec_runs)

    # Sort by run id (the run id corresponds to the directory name)
    return sorted(items, key=lambda item: item.get("id", ""))


def active_runs_for_spec(spec_slug: str) -> list[dict[str, Any]]:
    """Return active runs for a spec using cached lookup.

    This function uses the lazy-loaded cache to avoid O(n) filesystem scans.
    It only loads runs for the requested spec, and subsequent calls return
    the cached data from memory.

    Args:
        spec_slug: The spec identifier to get active runs for.

    Returns:
        A list of run metadata dictionaries for the spec that are not completed.
    """
    # Lazy-load runs for this specific spec
    _populate_run_cache_for_spec(spec_slug)

    # Return cached runs for this spec, filtered by status
    return [
        item
        for item in _run_metadata_cache.get(spec_slug, [])
        if item.get("status") not in INACTIVE_RUN_STATUSES
        and not run_is_stale(item)
    ]


def task_run_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return run history for a task using cached lookup.

    This function uses the lazy-loaded cache to avoid O(n) filesystem scans.
    It only loads runs for the requested spec, and subsequent calls return
    the cached data from memory.

    Args:
        spec_slug: The spec identifier to get task run history for.
        task_id: The task identifier to get run history for.
        limit: Maximum number of history items to return (default: 5).

    Returns:
        A list of run metadata dictionaries for the task, sorted by created_at
        and limited to the last `limit` items.
    """
    # Lazy-load runs for this specific spec
    _populate_run_cache_for_spec(spec_slug)

    # Filter by task_id from cached data
    history = [
        item
        for item in _run_metadata_cache.get(spec_slug, [])
        if item.get("task") == task_id
    ]

    # Sort by created_at and return last `limit` items
    return sorted(history, key=lambda item: item.get("created_at", ""))[-limit:]


def latest_handoffs(spec_slug: str, limit: int = 3) -> list[Path]:
    """
    Get the most recent handoff markdown files for a spec.

    Handoffs contain context passed between agents when working on tasks.
    This function retrieves the latest handoff files, sorted chronologically,
    to provide recent context for continuation or review.

    Args:
        spec_slug: URL-friendly slug identifying the spec
        limit: Maximum number of handoff files to return (default: 3)

    Returns:
        List of paths to the most recent handoff markdown files,
        sorted oldest to newest. Returns empty list if no handoffs exist
        or the handoffs directory doesn't exist.
    """
    handoffs_dir = spec_files(spec_slug)["handoffs_dir"]
    if not handoffs_dir.exists():
        return []
    return sorted(handoffs_dir.glob("*.md"))[-limit:]


def worktree_context(spec_slug: str) -> str:
    """
    Generate environment context documentation for a spec's workspace mode.

    Creates a formatted markdown section explaining whether the spec uses an
    isolated git worktree or shares the main repository root. Provides critical
    rules and path information to guide agent behavior based on the workspace mode.

    Args:
        spec_slug: URL-friendly slug identifying the spec

    Returns:
        Formatted markdown string containing environment context, including:
        - Current working directory path
        - Workspace mode (isolated worktree or shared root)
        - Critical rules for path usage and file operations
        - Parent repository path (if using worktree)
    """
    path = worktree_path(spec_slug)
    if not path.exists():
        return f"""## Environment Context

**Working Directory:** `{ROOT}`
**Spec Workspace Mode:** Shared repository root

No isolated git worktree is configured for this spec yet.
Use relative paths only.
"""
    return f"""## Environment Context

**Working Directory:** `{path}`
**Spec Workspace Mode:** Isolated git worktree
**Parent Repository:** `{ROOT}`

### Critical rules

1. Stay inside the worktree path above.
2. Do not edit files through absolute paths pointing at the parent repository.
3. Use relative paths from the worktree for all changes and git operations.
"""


def recovery_context(spec_slug: str, task_id: str) -> str:
    """
    Generate context about previous failed or blocked attempts for a task.

    Aggregates information from recent unsuccessful task runs to help agents
    understand what went wrong before and avoid repeating mistakes. Includes
    run IDs, roles, results, and summary text from up to 3 recent failures.

    Args:
        spec_slug: URL-friendly slug identifying the spec
        task_id: Unique identifier for the task

    Returns:
        Formatted text string containing:
        - Count of previous unsuccessful attempts
        - List of recent failed/blocked runs with:
            - Run ID
            - Role that executed the run
            - Result status (needs_changes, blocked, or failed)
            - Summary text (if available)
        Returns "No previous failed or blocked attempts..." if no failures exist.
    """
    history = task_run_history(spec_slug, task_id, limit=5)
    unsuccessful = [item for item in history if item.get("result") in {"needs_changes", "blocked", "failed"}]
    if not unsuccessful:
        return "No previous failed or blocked attempts recorded for this task."
    lines = [
        f"Previous unsuccessful attempts: {len(unsuccessful)}",
        "",
        "Recent outcomes:",
    ]
    for item in unsuccessful[-3:]:
        run_dir = RUNS_DIR / item["id"]
        summary_path = run_dir / "summary.md"
        summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
        lines.append(
            f"- {item['id']} ({item.get('role', 'unknown')} -> {item.get('result', 'unknown')})"
        )
        if summary_text:
            lines.append(f"  {summary_text.replace(chr(10), ' ')}")
    return "\n".join(lines)


def resume_context(run_id: str | None) -> str:
    """
    Generate context when resuming execution from a previous run.

    Retrieves metadata and summary information from a prior run to enable
    continuation of work. Provides agents with information about what role
    previously worked on the task, what result was achieved, how many attempts
    have been made, and what summary was recorded.

    Args:
        run_id: Unique identifier of the run to resume from, or None if no resume context

    Returns:
        Formatted text string containing:
        - Run ID being resumed
        - Previous role that executed the run
        - Previous result status
        - Attempt count so far
        - Summary text from the previous run (if available)
        Returns "No resume context." if run_id is None
        Returns "Requested resume source `{run_id}` was not found." if run doesn't exist
    """
    if not run_id:
        return "No resume context."
    run_dir = RUNS_DIR / run_id
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        return f"Requested resume source `{run_id}` was not found."
    metadata = read_json(metadata_path)
    summary_path = run_dir / "summary.md"
    summary_text = summary_path.read_text(encoding="utf-8").strip() if summary_path.exists() else ""
    return "\n".join(
        [
            f"Resuming from run: {run_id}",
            f"Previous role: {metadata.get('role', '')}",
            f"Previous result: {metadata.get('result', 'unfinished')}",
            f"Attempt count so far: {metadata.get('attempt_count', 1)}",
            "",
            summary_text or "No previous summary recorded.",
        ]
    )


def parse_findings(args: argparse.Namespace) -> list[dict[str, Any]] | None:
    """
    Parse findings from command-line arguments.

    Findings can be provided either as a JSON string via --findings-json
    or as a file path via --findings-file. The JSON can be either a list
    of finding objects or a dict with a 'findings' key.

    Args:
        args: Parsed command-line arguments with optional findings_json
            and findings_file attributes

    Returns:
        List of finding dictionaries, or None if no findings provided

    Raises:
        json.JSONDecodeError: If the provided JSON is invalid
    """
    findings_json = getattr(args, "findings_json", "")
    findings_file = getattr(args, "findings_file", "")
    if findings_json:
        loaded = json.loads(findings_json)
        return loaded if isinstance(loaded, list) else loaded.get("findings", [])
    if findings_file:
        loaded = read_json(Path(findings_file))
        return loaded if isinstance(loaded, list) else loaded.get("findings", [])
    return None


def default_tasks() -> list[dict[str, Any]]:
    """
    Get the default task template for new specs.

    Returns a predefined list of tasks that form the core workflow for
    building an autonomous development harness, including workflow contract
    definition, task graph management, execution harness implementation,
    review gates, and maintenance hooks.

    Returns:
        List of task dictionaries with default workflow tasks. Each task
        contains id, title, status, depends_on, owner_role,
        acceptance_criteria, and notes fields
    """
    return [
        {
            "id": "T1",
            "title": "Define workflow contract and repository structure",
            "status": "todo",
            "depends_on": [],
            "owner_role": "spec-writer",
            "acceptance_criteria": [
                "Spec and control-plane directories exist.",
                "Workflow roles and artifacts are defined.",
            ],
            "notes": [],
        },
        {
            "id": "T2",
            "title": "Build task graph and lifecycle management",
            "status": "todo",
            "depends_on": ["T1"],
            "owner_role": "task-graph-manager",
            "acceptance_criteria": [
                "Tasks have explicit lifecycle states.",
                "The system can identify the next ready task.",
            ],
            "notes": [],
        },
        {
            "id": "T3",
            "title": "Implement bounded coding execution harness",
            "status": "todo",
            "depends_on": ["T2"],
            "owner_role": "implementation-runner",
            "acceptance_criteria": [
                "A run can target one task and one backend agent.",
                "Runs store prompts, metadata, and summaries.",
            ],
            "notes": [],
        },
        {
            "id": "T4",
            "title": "Add review gate and handoff artifacts",
            "status": "todo",
            "depends_on": ["T3"],
            "owner_role": "reviewer",
            "acceptance_criteria": [
                "Review is distinct from implementation.",
                "Review outcome can move tasks to done or needs_changes.",
            ],
            "notes": [],
        },
        {
            "id": "T5",
            "title": "Add maintenance and git workflow hooks",
            "status": "todo",
            "depends_on": ["T4"],
            "owner_role": "maintainer",
            "acceptance_criteria": [
                "The system can prepare isolated worktrees.",
                "Low-risk maintenance can be scheduled and audited.",
            ],
            "notes": [],
        },
    ]


def validate_spec_repository(repository_id: str) -> None:
    """
    Validate that a repository reference exists.

    Args:
        repository_id: The repository ID to validate

    Raises:
        SystemExit: If the repository doesn't exist
    """
    if not repository_id:
        return

    repo_manager = repository_manager()
    if not repo_manager.repository_exists(repository_id):
        raise SystemExit(
            f"repository '{repository_id}' not found. "
            f"Use 'repo-add' to register it first, or omit --repository to use the default repository."
        )


def create_spec(args: argparse.Namespace) -> None:
    """
    Create a new spec directory with markdown, metadata, and initial task files.

    Creates a spec directory structure containing:
    - spec.md: Main specification document with title, summary, problem, goals, etc.
    - metadata.json: Spec metadata including slug, title, dates, and worktree info
    - handoff.md: Handoff notes for role transitions
    - tasks.json: Initial task list with default tasks
    - review_state.json: Initial review state
    - handoffs/: Directory for role handoff notes

    Args:
        args: Namespace containing spec creation parameters:
            - title: Spec title
            - summary: Brief description of the spec
            - slug: Optional URL-friendly slug (auto-generated from title if not provided)

    Raises:
        SystemExit: If a spec with the same slug already exists

    Side Effects:
        Creates spec directory and all initial files
        Records a spec.created event
    """
    ensure_state()
    slug = slugify(args.slug or args.title)
    files = spec_files(slug)
    if files["spec"].exists():
        raise SystemExit(f"spec already exists: {slug}")
    files["dir"].mkdir(parents=True, exist_ok=True)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    spec_markdown = f"""# {args.title}

## Summary

{args.summary}

## Problem

Describe the problem this system is solving.

## Goals

- Build a reliable autonomous development harness.
- Keep orchestration separate from model-specific execution.
- Make every run resumable and auditable.

## Non-goals

- Fully unsupervised production deploys in v1.
- Vendor lock-in to a single coding model.

## Constraints

- Use explicit specs and task artifacts.
- Support `codex` and `claude` style CLIs.
- Support background execution with `tmux`.
- Require review before marking coding work complete.
- Prefer isolated git worktrees for implementation runs.

## Acceptance Criteria

- A spec-driven task graph exists.
- Runs can be created from roles and agent mappings.
- Review is a separate step from implementation.
- Git workflow hooks can prepare isolated task branches.
"""
    metadata = {
        "slug": slug,
        "title": args.title,
        "summary": args.summary,
        "created_at": now_stamp(),
        "updated_at": now_stamp(),
        "status": "draft",
        "worktree": {
            "path": "",
            "branch": worktree_branch(slug),
            "base_branch": detect_base_branch(),
        },
    }
    if getattr(args, "repository", None):
        validate_spec_repository(args.repository)
        metadata["repository"] = args.repository
    handoff = "# Handoff\n\nInitial spec created. Next role should refine scope and derive tasks.\n"
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    files["handoff"].write_text(handoff, encoding="utf-8")
    write_json(files["metadata"], metadata)
    save_review_state(slug, review_state_default())
    if not task_file(slug).exists():
        write_json(
            task_file(slug),
            {
                "spec_slug": slug,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
    record_event(slug, "spec.created", {"title": args.title})
    print(str(files["dir"]))


def init_tasks_cmd(args: argparse.Namespace) -> None:
    ensure_state()
    load_spec_metadata(args.spec)
    path = task_file(args.spec)
    created = False
    if not path.exists() or args.force:
        write_json(
            path,
            {
                "spec_slug": args.spec,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
        sync_review_state(args.spec, reason="tasks_initialized")
        record_event(args.spec, "tasks.initialized", {"force": args.force})
        created = True
    payload = load_tasks(args.spec)
    print(
        json.dumps(
            {
                "spec": args.spec,
                "tasks_file": str(path),
                "created": created,
                "task_count": len(payload.get("tasks", [])),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def show_spec(args: argparse.Namespace) -> None:
    metadata = normalize_worktree_metadata(args.slug)
    files = spec_files(args.slug)
    payload = {
        "metadata": metadata,
        "review_status": review_status_summary(args.slug),
        "tasks": load_tasks(args.slug),
        "spec_markdown": files["spec"].read_text(encoding="utf-8"),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def update_spec(args: argparse.Namespace) -> None:
    metadata = load_spec_metadata(args.slug)
    files = spec_files(args.slug)
    spec_markdown = files["spec"].read_text(encoding="utf-8")
    changes = []
    if args.title:
        metadata["title"] = args.title
        lines = spec_markdown.splitlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {args.title}"
            spec_markdown = "\n".join(lines).rstrip() + "\n"
        changes.append("title")
    if args.summary:
        metadata["summary"] = args.summary
        spec_markdown = replace_markdown_section(spec_markdown, "Summary", args.summary)
        changes.append("summary")
    if args.status:
        metadata["status"] = args.status
        changes.append("status")
    if args.append:
        spec_markdown = spec_markdown.rstrip() + (
            f"\n\n## Updates\n\n### {now_stamp()}\n\n{args.append.strip()}\n"
        )
        changes.append("append")
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    save_spec_metadata(args.slug, normalize_worktree_metadata(args.slug, metadata))
    sync_review_state(args.slug, reason="spec_updated")
    record_event(args.slug, "spec.updated", {"changes": changes or ["touch"]})
    print(
        json.dumps(
            {
                "slug": args.slug,
                "changed_fields": changes,
                "metadata": normalize_worktree_metadata(args.slug),
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def list_tasks(args: argparse.Namespace) -> None:
    """
    List all tasks for a spec in JSON format.

    Retrieves the task list for a given spec and prints it as formatted JSON.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier

    Side Effects:
        Prints JSON task list to stdout
    """
    tasks = load_tasks(args.spec)
    print_json(tasks)


def next_task_data(spec_slug: str, role: str | None = None) -> dict[str, Any] | None:
    """
    Find the next available task for a given role.

    Searches for a task that is:
    - For non-reviewer roles: status is "todo" or "needs_changes", matches the role if specified,
      and has all dependencies completed
    - For reviewer role: status is "in_review"

    Args:
        spec_slug: Spec slug identifier
        role: Optional role filter (e.g., "frontend", "backend"). If None, returns any
            available task. If "reviewer", returns tasks in review status.

    Returns:
        Task dictionary if an available task is found, None otherwise

    Side Effects:
        None
    """
    tasks = load_tasks(spec_slug)
    for task in tasks.get("tasks", []):
        if role == "reviewer":
            if task["status"] != "in_review":
                continue
        else:
            if task["status"] not in {"todo", "needs_changes"}:
                continue
            if role and task["owner_role"] != role:
                continue
        blocked = False
        for dep in task.get("depends_on", []):
            # task_lookup now handles both same-repo and cross-repo dependencies
            dep_task = task_lookup(tasks, dep, spec_slug=spec_slug)
            if dep_task["status"] != "done":
                blocked = True
                break
        if not blocked:
            return task
    return None


def next_task(args: argparse.Namespace) -> None:
    """
    Print the next available task for a spec in JSON format.

    Retrieves and displays the next available task for a given spec and role.
    If no task is available, prints an empty JSON object.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - role: Optional role filter (e.g., "frontend", "backend", "reviewer")

    Side Effects:
        Prints task data as JSON to stdout, or {} if no task is available
    """
    task = next_task_data(args.spec, args.role)
    if not task:
        print("{}")
        return
    print_json(task)


def set_task_status(args: argparse.Namespace) -> None:
    """
    Set the status of a task within a spec.

    Updates the task's status field, adds a note with timestamp, saves the
    updated tasks data, records an event, and prints the updated task as JSON.

    Valid statuses: todo, in_progress, in_review, needs_changes, blocked, done

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier to update
            - status: New status value (must be in VALID_TASK_STATUSES)
            - note: Optional note to add (defaults to status change message)

    Raises:
        SystemExit: If the provided status is not valid
    """
    if args.status not in VALID_TASK_STATUSES:
        raise SystemExit(f"invalid status: {args.status}")
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = args.status
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or f"status set to {args.status}"}
    )
    save_tasks(args.spec, data, reason="task_status_updated", sync_review_state_callback=sync_review_state)
    record_event(args.spec, "task.status_updated", {"task": args.task, "status": args.status})
    print_json(task)


def update_task_cmd(args: argparse.Namespace) -> None:
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    changed_fields = []
    if args.status:
        if args.status not in VALID_TASK_STATUSES:
            raise SystemExit(f"invalid status: {args.status}")
        task["status"] = args.status
        changed_fields.append("status")
    if args.title:
        task["title"] = args.title
        changed_fields.append("title")
    if args.owner_role:
        task["owner_role"] = args.owner_role
        changed_fields.append("owner_role")
    if args.append_criterion:
        task.setdefault("acceptance_criteria", []).append(args.append_criterion)
        changed_fields.append("acceptance_criteria")
    if args.note:
        task.setdefault("notes", []).append({"at": now_stamp(), "note": args.note})
        changed_fields.append("notes")
    elif args.status:
        task.setdefault("notes", []).append({"at": now_stamp(), "note": f"status set to {args.status}"})
    if not changed_fields:
        raise SystemExit("no task update provided")
    save_tasks(args.spec, data, reason="task_updated", sync_review_state_callback=sync_review_state)
    record_event(args.spec, "task.updated", {"task": args.task, "fields": changed_fields})
    print(json.dumps(task, indent=2, ensure_ascii=True))


def reset_task_cmd(args: argparse.Namespace) -> None:
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = "todo"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or "task reset to todo"}
    )
    save_tasks(args.spec, data, reason="task_reset", sync_review_state_callback=sync_review_state)
    record_event(args.spec, "task.reset", {"task": args.task})
    print(json.dumps(task, indent=2, ensure_ascii=True))


def write_handoff(
    spec_slug: str,
    task_id: str,
    role: str,
    summary: str,
    next_role: str,
    result: str,
) -> Path:
    """
    Write a handoff document for a task.

    Creates a timestamped handoff markdown file in the spec's handoffs directory
    and updates the current handoff file. The handoff includes metadata (role,
    next_role, result, timestamp) and a summary section.

    Args:
        spec_slug: Spec identifier (slug or ID)
        task_id: Task identifier for the handoff
        role: Current role (who is handing off)
        summary: Summary of work completed or context for next role
        next_role: Next role to take over the task
        result: Result status or outcome of the current role's work

    Returns:
        Path to the created handoff markdown file
    """
    files = spec_files(spec_slug)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    handoff_path = files["handoffs_dir"] / f"{now_stamp()}-{task_id}-{slugify(role)}.md"
    handoff_text = "\n".join(
        [
            f"# Handoff: {task_id}",
            "",
            f"- role: {role}",
            f"- next_role: {next_role}",
            f"- result: {result}",
            f"- created_at: {now_stamp()}",
            "",
            "## Summary",
            "",
            summary,
            "",
        ]
    )
    handoff_path.write_text(handoff_text, encoding="utf-8")
    files["handoff"].write_text(handoff_text, encoding="utf-8")
    record_event(spec_slug, "handoff.created", {"task": task_id, "role": role, "result": result})
    return handoff_path


def create_handoff(args: argparse.Namespace) -> None:
    """
    Create a handoff document from CLI arguments.

    Command-line interface wrapper for write_handoff(). Extracts handoff
    parameters from args namespace, creates the handoff document, and
    prints the resulting file path.

    Args:
        args: Command-line arguments containing:
            - spec: Spec identifier (slug or ID)
            - task: Task identifier for the handoff
            - role: Current role handing off
            - summary: Summary of work completed
            - next_role: Next role to receive the handoff
            - result: Result status of current work
    """
    path = write_handoff(args.spec, args.task, args.role, args.summary, args.next_role, args.result)
    print(str(path))


def build_prompt(
    spec_slug: str,
    role: str,
    task_id: str | None,
    agent: AgentSpec,
    resume_from: str | None = None,
    run_id: str | None = None,
) -> str:
    """
    Build a comprehensive execution prompt for an AI agent.

    Assembles all context needed for an AI agent to execute a task, including
    the spec definition, task details, agent configuration, memory context,
    strategy context, review state, recovery information, resume context,
    QA fix requests, and recent handoffs.

    The prompt is structured to provide the agent with complete situational
    awareness and all necessary metadata to perform its role effectively.

    Args:
        spec_slug: Slug identifier for the spec to execute
        role: Role name the agent should assume (e.g., "developer", "reviewer")
        task_id: Specific task ID to execute, or None to auto-select next task
        agent: Agent specification with configuration, tools, and memory scopes
        resume_from: Optional run ID to resume from for recovery
        run_id: Optional run ID so the prompt can include the completion artifact path

    Returns:
        Complete prompt string with all context sections for agent execution

    Raises:
        SystemExit: If the specified spec does not exist
    """
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id, spec_slug=spec_slug) if task_id else next_task_data(spec_slug, role)
    review_summary = review_status_summary(spec_slug)
    fix_request = load_fix_request(spec_slug)
    fix_request_data = load_fix_request_data(spec_slug)
    memory_context = load_memory_context(spec_slug, agent.memory_scopes)
    strategy_context = render_strategy_context(spec_slug)
    agent_result_path = str(RUNS_DIR / run_id / AGENT_RESULT_FILE) if run_id else ""
    handoff_sections = []
    for handoff_path in latest_handoffs(spec_slug):
        handoff_sections.append(f"### {handoff_path.name}\n")
        handoff_sections.append(handoff_path.read_text(encoding="utf-8"))
    recovery = recovery_context(spec_slug, selected_task["id"]) if selected_task else "No task selected."
    return "\n".join(
        [
            f"Role: {role}",
            f"Spec slug: {spec_slug}",
            f"Task id: {selected_task['id'] if selected_task else 'none'}",
            "",
            "Read the repository state and execute the role carefully.",
            "Follow the selected task acceptance criteria.",
            "Keep changes scoped and leave a concise handoff summary.",
            "",
            "## Backend configuration",
            json.dumps(
                sanitize_dict(
                    {
                        "agent": agent.name,
                        "protocol": agent.protocol,
                        "command": agent.command,
                        "model": agent.model,
                        "model_profile": agent.model_profile,
                        "tools": agent.tools or [],
                        "tool_profile": agent.tool_profile,
                        "memory_scopes": agent.memory_scopes or [],
                        "native_resume_supported": bool(agent.resume),
                        "transport": agent.transport or {},
                    }
                ),
                indent=2,
                ensure_ascii=True,
            ),
            "",
            "## BMAD operating frame",
            load_bmad_template(role),
            "",
            worktree_context(spec_slug),
            "",
            "## Memory context",
            memory_context,
            "",
            strategy_context,
            "",
            "## Review state",
            json.dumps(review_summary, indent=2, ensure_ascii=True),
            "",
            "## Recovery context",
            recovery,
            "",
            "## Resume context",
            resume_context(resume_from),
            "",
            "## Completion contract",
            (
                "When you finish, write a JSON file to "
                f"{agent_result_path} with this shape:\n"
                "{\n"
                '  "result": "success|needs_changes|blocked|failed",\n'
                '  "summary": "concise execution summary",\n'
                '  "findings": [\n'
                "    {\n"
                '      "file": "path/to/file",\n'
                '      "line": 10,\n'
                '      "severity": "low|medium|high|critical",\n'
                '      "category": "tests|bug|security|workflow|docs",\n'
                '      "title": "short finding title",\n'
                '      "body": "what is wrong and why",\n'
                '      "suggested_fix": "optional next action"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "Always write the file before exiting. Use an empty findings array when there are no findings."
            )
            if agent_result_path
            else "No completion artifact path was assigned for this run.",
            "",
            "## QA fix request (structured)",
            json.dumps(fix_request_data, indent=2, ensure_ascii=True),
            "",
            "## QA fix request (markdown)",
            fix_request or "No QA fix request present.",
            "",
            "## Spec",
            files["spec"].read_text(encoding="utf-8"),
            "",
            "## Selected task",
            json.dumps(selected_task, indent=2, ensure_ascii=True) if selected_task else "{}",
            "",
            "## Full task graph",
            json.dumps(tasks, indent=2, ensure_ascii=True),
            "",
            "## Recent handoffs",
            "\n".join(handoff_sections) if handoff_sections else "No handoffs yet.",
        ]
    )


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


def recover_run_record(run_id: str, reason: str, dispatch: bool = False) -> dict[str, Any]:
    metadata = load_run_metadata(run_id)
    if metadata.get("status") in {"completed", "cancelled", "cleaned", "recovered"}:
        raise SystemExit(f"run {run_id} cannot be recovered from status {metadata.get('status', '')}")
    review_summary = review_status_summary(metadata["spec"])
    if metadata["role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        raise SystemExit(
            "spec review approval is not valid; approve the current planning contract before recovering implementation"
        )
    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"], spec_slug=metadata["spec"])
    task["status"] = "in_progress"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": f"recovery created from {run_id}: {reason}"}
    )
    save_tasks(metadata["spec"], tasks, reason="task_status_updated", sync_review_state_callback=sync_review_state)

    metadata["status"] = "recovered"
    metadata["recovered_at"] = now_stamp()
    metadata["recovery_reason"] = reason
    write_run_metadata(run_id, metadata)

    new_run_dir = create_run_record(
        metadata["spec"],
        metadata["role"],
        metadata["agent"],
        metadata["task"],
        branch=metadata.get("branch"),
        resume_from=run_id,
    )
    new_run_id = new_run_dir.name
    new_metadata = load_run_metadata(new_run_id)
    new_metadata["recovery_reason"] = reason
    write_run_metadata(new_run_id, new_metadata)

    session_name = ""
    if dispatch:
        session_name = run_cmd(
            ["bash", str(ROOT / "scripts" / "tmux-start.sh"), str(new_run_dir / "run.sh")]
        ).stdout.strip()
        if session_name:
            new_metadata = load_run_metadata(new_run_id)
            new_metadata["tmux_session"] = session_name
            write_run_metadata(new_run_id, new_metadata)

    record_event(
        metadata["spec"],
        "run.recovered",
        {
            "from": run_id,
            "to": new_run_id,
            "task": metadata["task"],
            "role": metadata["role"],
            "dispatch": dispatch,
            "reason": reason,
        },
    )
    return {
        "run": run_id,
        "new_run": new_run_id,
        "reason": reason,
        "dispatched": dispatch,
        "tmux_session": session_name,
    }


def recover_run_cmd(args: argparse.Namespace) -> None:
    print_json(recover_run_record(args.run, args.reason or "manual_recover", dispatch=args.dispatch))


def sweep_runs_cmd(args: argparse.Namespace) -> None:
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
            {"run": metadata["id"], "reason": reason, "status": args.target_status},
        )

    if task_updates:
        save_tasks(args.spec, tasks, reason="run_sweep", sync_review_state_callback=sync_review_state)

    print_json(
        {
            "spec": args.spec,
            "stale_after": stale_after,
            "marked_stale": marked_stale,
            "recovered": recovered,
            "task_updates": task_updates,
        }
    )


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


def complete_run_record(
    run_id: str,
    result: str,
    summary: str | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if result not in RUN_RESULTS:
        raise SystemExit(f"invalid result: {result}")
    run_dir = RUNS_DIR / run_id
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {run_id}")
    metadata = read_json(metadata_path)
    findings = findings or []
    metadata["status"] = "completed"
    metadata["result"] = result
    metadata["completed_at"] = now_stamp()
    metadata["findings_count"] = len(findings)
    write_json(metadata_path, metadata)
    summary = summary or f"Run {run_id} completed with result {result}."
    (run_dir / "summary.md").write_text(f"# Run Summary\n\n{summary}\n", encoding="utf-8")

    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"], spec_slug=metadata["spec"])
    if metadata["role"] == "reviewer":
        next_status = "done" if result == "success" else result
    elif result == "success":
        next_status = "in_review"
    else:
        next_status = result
    status_map = {
        "success": next_status,
        "needs_changes": "needs_changes",
        "blocked": "blocked",
        "failed": "blocked",
    }
    task["status"] = status_map[result]
    task.setdefault("notes", []).append({"at": now_stamp(), "note": summary})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated", sync_review_state_callback=sync_review_state)
    next_role = "reviewer" if metadata["role"] != "reviewer" else task["owner_role"]
    fix_request_path = ""
    if metadata["role"] == "reviewer" and result in {"needs_changes", "blocked", "failed"}:
        fix_request_path = str(
            write_fix_request(
                metadata["spec"],
                metadata["task"],
                summary,
                result,
                findings=findings,
            )
        )
    if metadata["role"] == "implementation-runner" and result == "success":
        clear_fix_request(metadata["spec"])
    strategy_paths = record_reflection(metadata["spec"], metadata, result, summary, findings=findings)
    memory_cfg = load_system_config().get("memory", {})
    if memory_cfg.get("enabled", True) and memory_cfg.get("auto_capture_run_results", True):
        for scope in metadata.get("agent_config", {}).get("memory_scopes") or ["spec"]:
            append_memory(
                scope,
                f"role={metadata['role']}\nresult={result}\nsummary={summary}",
                spec_slug=metadata["spec"],
                title=f"{metadata['task']} {metadata['role']} {result}",
            )
    handoff_path = write_handoff(
        metadata["spec"], metadata["task"], metadata["role"], summary, next_role, result
    )
    record_event(
        metadata["spec"],
        "run.completed",
        {
            "run": metadata["id"],
            "task": metadata["task"],
            "role": metadata["role"],
            "result": result,
            "fix_request": fix_request_path,
        },
    )
    return {
        "run": metadata["id"],
        "task_status": task["status"],
        "handoff": str(handoff_path),
        "fix_request": fix_request_path,
        "strategy_memory": [str(path) for path in strategy_paths],
    }


def finalize_run_record(
    run_id: str,
    exit_code: int,
    result_file: str = "",
) -> dict[str, Any]:
    result_path = Path(result_file) if result_file else (RUNS_DIR / run_id / AGENT_RESULT_FILE)
    source = "fallback"
    details = ""
    findings: list[dict[str, Any]] = []
    try:
        result, summary, findings, details = load_agent_result_payload(result_path)
        source = "agent_result"
    except FileNotFoundError:
        if exit_code == 0:
            result = "failed"
            summary = (
                f"Agent exited successfully but did not write {AGENT_RESULT_FILE}; "
                "treating the run as failed."
            )
        else:
            result = "failed"
            summary = f"Agent exited with code {exit_code} before producing {AGENT_RESULT_FILE}."
    except Exception as exc:
        result = "failed"
        summary = f"Invalid agent result payload in {result_path}: {exc}"
    payload = complete_run_record(run_id, result, summary, findings=findings)
    payload["exit_code"] = exit_code
    payload["result_source"] = source
    if details:
        payload["result_file"] = details
    return payload


def finalize_run_cmd(args: argparse.Namespace) -> None:
    print_json(finalize_run_record(args.run, int(args.exit_code), result_file=args.result_file or ""))


def cancel_run(args: argparse.Namespace) -> None:
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
    print(
        json.dumps(
            {
                "run": metadata["id"],
                "task_status": task["status"],
                "cancelled_at": metadata["cancelled_at"],
                "reason": reason,
            },
            indent=2,
            ensure_ascii=True,
        )
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


def show_events(args: argparse.Namespace) -> None:
    """
    Display event log for a spec.

    Retrieves and prints the most recent events from the spec's event log,
    formatted as indented JSON. Events are stored in reverse chronological
    order (newest last).

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec
            - limit: Maximum number of events to return (default: 20)
    """
    print_json(load_events(args.spec, args.limit))


def show_fix_request(args: argparse.Namespace) -> None:
    """
    Display QA fix request data for a spec.

    Retrieves and prints the structured JSON data containing the fix request
    payload including task ID, result status, summary, and normalized findings.
    Output is formatted as indented JSON.

    Args:
        args: Command-line arguments namespace with attributes:
            - spec: Slug identifier of the spec

    Notes:
        Returns a default empty structure if the fix request file doesn't exist.
    """
    print_json(load_fix_request_data(args.spec))


def create_fix_request_cmd(args: argparse.Namespace) -> None:
    """
    Create a QA fix request artifact for a spec and task.

    Parses QA findings from command-line arguments and writes a structured
    fix request file to the spec's review directory. The file captures
    issues that must be addressed before the spec can be approved.

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier
            - task: Task ID requiring fixes
            - summary: Brief summary of issues
            - result: QA result status (e.g., "needs_changes")
            - findings_json: JSON string with findings (optional)
            - findings_file: Path to JSON file with findings (optional)

    Side Effects:
        - Creates .autoflow/specs/{spec}/QA_FIX_REQUEST.md
        - Records event in spec's event log
    """
    findings = parse_findings(args)
    path = write_fix_request(args.spec, args.task, args.summary, args.result, findings=findings)
    print(str(path))


def discover_agents_cmd(_: argparse.Namespace) -> None:
    """
    Discover and display all available agents.

    Performs comprehensive agent discovery by checking for CLI-based agents
    (codex, claude) on the system PATH and loading additional agents from the
    system configuration registry (ACP protocol).

    The discovery results are printed as JSON containing:
    - discovered_at: ISO 8601 timestamp of when discovery was performed
    - agents: List of discovered agent dictionaries with name, protocol,
      command/path, transport, and capabilities
    - system_config: Relevant sections from system config including memory,
      models, and tools configurations

    The discovery results are also cached to .autoflow/discovered_agents.json
    for persistence and use by other commands.
    """
    print_json(discover_agents_registry())


def sync_agents_cmd(args: argparse.Namespace) -> None:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into .autoflow/agents.json,
    preserving existing agent configurations by default. Can optionally
    overwrite existing entries when the --overwrite flag is provided.

    Creates the agents file with default structure if it doesn't exist.

    The sync results are printed as JSON containing:
    - agents_file: Path to the agents.json file
    - added: List of agent names that were added or updated
    - total_agents: Total number of agents after sync

    Args:
        args: Namespace with optional overwrite attribute (bool). If True,
            replaces existing agent configurations with discovered ones.
            If False, preserves existing configurations and only adds new agents.
    """
    print_json(sync_discovered_agents(overwrite=args.overwrite))


def show_strategy_cmd(args: argparse.Namespace) -> None:
    """
    Display accumulated strategy memory for a spec.

    Shows the complete strategy summary including playbook entries,
    planner notes, recent reflections, and statistics. This provides
    a comprehensive view of all strategic decisions and learnings
    accumulated for a spec.

    Args:
        args: Namespace containing:
            - spec: Spec slug to show strategy for

    Output:
        Prints JSON-formatted strategy summary with keys:
            - updated_at: Last update timestamp
            - playbook: List of playbook rules with evidence
            - planner_notes: Last 5 planner notes with metadata
            - recent_reflections: Last 5 reflection entries
            - stats: Strategy statistics and metrics
    """
    print_json(strategy_summary(args.spec))


def add_planner_note_cmd(args: argparse.Namespace) -> None:
    content = args.content or args.note or ""
    if not content:
        raise SystemExit("planner note content is required")
    title = args.title or "Planner note"
    path = add_planner_note(args.spec, title, content, category=args.category, scope=args.scope)
    print(str(path))


def create_worktree(args: argparse.Namespace) -> None:
    """
    Create a git worktree for isolated spec development.

    Creates a new git worktree linked to a spec-specific branch, allowing
    parallel development without affecting the main branch. The worktree
    is created at `.autoflow/worktrees/tasks/{spec_slug}`.

    If the worktree already exists, updates the spec metadata with the
    worktree information without recreating it.

    The branch name follows the pattern `codex/{slugified_spec}` and is
    created from the base branch if it doesn't already exist.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - base_branch: Base branch to create worktree from (optional,
              defaults to detected base branch)

    Side Effects:
        - Creates git worktree directory
        - Creates or checks out spec-specific branch
        - Updates spec metadata with worktree path and branch info
        - Records worktree.created event

    Example:
        >>> args = argparse.Namespace(spec="feature-auth", base_branch="main")
        >>> create_worktree(args)
        {"path": ".autoflow/worktrees/tasks/feature-auth",
         "branch": "codex/feature-auth",
         "base_branch": "main"}
    """
    ensure_state()
    repository = getattr(args, "repository", None)
    if repository:
        validate_spec_repository(repository)
    path = worktree_path(args.spec, repository=repository)
    branch = worktree_branch(args.spec)
    base_branch = args.base_branch or detect_base_branch()
    metadata = load_spec_metadata(args.spec)

    if args.force and path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)], check=False)
        shutil.rmtree(path, ignore_errors=True)

    if path.exists():
        worktree_metadata = {
            "path": str(path),
            "branch": branch,
            "base_branch": base_branch,
        }
        if repository:
            worktree_metadata["repository"] = repository
        metadata["worktree"] = worktree_metadata
        save_spec_metadata(args.spec, metadata)
        print_json(metadata["worktree"])
        return

    branch_exists = run_cmd(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    if branch_exists:
        run_cmd(["git", "worktree", "add", str(path), branch])
    else:
        run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch])

    worktree_metadata = {
        "path": str(path),
        "branch": branch,
        "base_branch": base_branch,
    }
    if repository:
        worktree_metadata["repository"] = repository
    metadata["worktree"] = worktree_metadata
    save_spec_metadata(args.spec, metadata)
    record_event(args.spec, "worktree.created", metadata["worktree"])
    print_json(metadata["worktree"])


def remove_worktree(args: argparse.Namespace) -> None:
    """
    Remove a git worktree for a spec.

    Removes the worktree directory and optionally deletes the associated branch.
    Updates the spec metadata to clear the worktree path.

    Args:
        args: Namespace with attributes:
            - spec: Spec slug identifier
            - repository: Optional repository ID for multi-repo worktrees
            - delete_branch: If True, delete the associated git branch

    Side Effects:
        - Removes git worktree directory if it exists
        - Deletes the associated branch if delete_branch is True
        - Updates spec metadata to clear worktree path
        - Records worktree.removed event
    """
    repository = getattr(args, "repository", None)
    if repository:
        validate_spec_repository(repository)
    path = worktree_path(args.spec, repository=repository)
    branch = worktree_branch(args.spec)
    if path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)])
    if args.delete_branch:
        run_cmd(["git", "branch", "-D", branch], check=False)
    worktree_metadata = {"path": "", "branch": branch, "base_branch": detect_base_branch()}
    if repository:
        worktree_metadata["repository"] = repository
    metadata["worktree"] = worktree_metadata
    metadata = load_spec_metadata(args.spec)
    metadata["worktree"] = worktree_metadata
    save_spec_metadata(args.spec, metadata)
    record_event(args.spec, "worktree.removed", {"path": str(path), "branch_deleted": args.delete_branch})
    print_json(metadata["worktree"])


def list_specs(_: argparse.Namespace) -> None:
    items = []
    for metadata_path in SPECS_DIR.glob("*/metadata.json"):
        metadata = normalize_worktree_metadata(metadata_path.parent.name, read_json(metadata_path))
        slug = metadata.get("slug", metadata_path.parent.name)
        review_state = load_review_state(slug)
        items.append(
            {
                "slug": slug,
                "title": metadata.get("title", ""),
                "summary": metadata.get("summary", ""),
                "status": metadata.get("status", ""),
                "created_at": metadata.get("created_at", ""),
                "updated_at": metadata.get("updated_at", ""),
                "worktree": metadata.get("worktree", {}),
                "review": {
                    "approved": review_state.get("approved", False),
                    "approved_by": review_state.get("approved_by", ""),
                    "review_count": review_state.get("review_count", 0),
                },
            }
        )
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    print(json.dumps(items, indent=2, ensure_ascii=True))


def list_worktrees(_: argparse.Namespace) -> None:
    """
    List all worktrees across all specs.

    Scans all spec metadata files to collect worktree information, including
    the spec slug, worktree path, associated branch, and base branch.

    Args:
        _: Unused namespace argument (required for CLI command interface)

    Output:
        Prints JSON array of worktree information, one entry per spec:
        - spec: Spec slug identifier
        - worktree: Dictionary containing:
            - path: Path to worktree directory (empty if not created)
            - branch: Branch name for the worktree
            - base_branch: Base branch the worktree was created from

    Example:
        >>> list_worktrees(None)
        [
          {
            "spec": "feature-auth",
            "worktree": {
              "path": ".autoflow/worktrees/tasks/feature-auth",
              "branch": "codex/feature-auth",
              "base_branch": "main"
            }
          },
          {
            "spec": "bugfix-login",
            "worktree": {"path": "", "branch": "codex/bugfix-login", "base_branch": "main"}
          }
        ]
    """
    items = []
    for metadata_path in sorted(SPECS_DIR.glob("*/metadata.json")):
        metadata = normalize_worktree_metadata(metadata_path.parent.name, read_json(metadata_path))
        items.append(
            {
                "spec": metadata.get("slug", metadata_path.parent.name),
                "worktree": metadata.get("worktree", {}),
            }
        )
    print_json(items)


def workflow_state(args: argparse.Namespace) -> None:
    """
    Aggregate and display comprehensive workflow state for a spec.

    Computes the complete workflow state by analyzing task dependencies,
    review status, active runs, strategy memory, and QA fix requests.
    Identifies ready tasks (those whose dependencies are satisfied) and
    blocked tasks, then determines the recommended next action while
    respecting approval gates.

    The output payload includes:
        - spec: Spec slug identifier
        - review_status: Review approval and validity information
        - worktree: Git worktree metadata if present
        - fix_request_present: Whether a QA fix request exists
        - fix_request: Structured QA fix request data
        - strategy_summary: Strategy memory with playbook and reflections
        - active_runs: List of currently executing runs for this spec
        - ready_tasks: Tasks ready to be started (dependencies met)
        - blocked_or_active_tasks: Tasks that are blocked or in progress
        - blocking_reason: Reason if next action is blocked (e.g., "review_approval_required")
        - recommended_next_action: Next task to work on, or None if active runs exist

    Args:
        args: Namespace containing:
            - spec: Spec slug identifier

    Returns:
        None (prints JSON payload to stdout)
    """
    data = load_tasks(args.spec)
    review_summary = review_status_summary(args.spec)
    active_runs = active_runs_for_spec(args.spec)
    stale_runs = stale_runs_for_spec(args.spec)
    ready = []
    blocked = []
    for task in data.get("tasks", []):
        deps_done = all(task_lookup(data, dep, spec_slug=args.spec)["status"] == "done" for dep in task.get("depends_on", []))
        entry = {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "owner_role": task["owner_role"],
        }
        is_ready = False
        if task["status"] in {"todo", "needs_changes"} and deps_done:
            is_ready = True
        if task["status"] == "in_review":
            entry["owner_role"] = "reviewer"
            is_ready = True
        if is_ready:
            ready.append(entry)
        elif task["status"] != "done":
            blocked.append(entry)
    next_entry = ready[0] if ready else None
    blocking_reason = ""
    if next_entry and next_entry["owner_role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        blocking_reason = "review_approval_required"
        next_entry = None
    payload = {
        "spec": args.spec,
        "review_status": review_summary,
        "worktree": normalize_worktree_metadata(args.spec).get("worktree", {}),
        "fix_request_present": bool(load_fix_request(args.spec)),
        "fix_request": load_fix_request_data(args.spec),
        "strategy_summary": strategy_summary(args.spec),
        "active_runs": active_runs,
        "stale_runs": stale_runs,
        "ready_tasks": ready,
        "blocked_or_active_tasks": blocked,
        "blocking_reason": blocking_reason,
        "recommended_next_action": None if active_runs else next_entry,
    }
    print_json(payload)


def show_status(_: argparse.Namespace) -> None:
    """
    Display overall Autoflow system status.

    Shows a high-level overview of the Autoflow system by listing all
    available specs and runs. This provides a quick way to see what
    specs exist and what runs have been executed across the entire system.

    The output payload includes:
        - specs: Alphabetically sorted list of spec slugs
        - runs: Alphabetically sorted list of run IDs

    Args:
        _: Namespace (unused, present for command interface consistency)

    Returns:
        None (prints JSON payload to stdout)
    """
    ensure_state()
    specs = sorted(p.name for p in SPECS_DIR.iterdir() if p.is_dir())
    runs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
    status = {"specs": specs, "runs": runs}
    print_json(status)


def list_runs(args: argparse.Namespace) -> None:
    ensure_state()
    runs = run_metadata_iter()

    # Apply filters if provided
    if hasattr(args, 'spec') and args.spec:
        runs = [r for r in runs if r.get("spec") == args.spec]
    if hasattr(args, 'status') and args.status:
        runs = [r for r in runs if r.get("status") == args.status]
    if hasattr(args, 'role') and args.role:
        runs = [r for r in runs if r.get("role") == args.role]
    if hasattr(args, 'agent') and args.agent:
        runs = [r for r in runs if r.get("agent") == args.agent]

    print(json.dumps(runs, indent=2, ensure_ascii=True))


def repo_add_cmd(args: argparse.Namespace) -> None:
    """Add a repository to the registry."""
    ensure_state()
    repo_id = args.id
    repo_file = REPOSITORIES_DIR / f"{repo_id}.json"

    if repo_file.exists():
        raise SystemExit(f"repository already exists: {repo_id}")

    # Build repository data
    repo_data = {
        "id": repo_id,
        "name": args.name,
        "path": args.path,
        "url": args.url if args.url else None,
        "description": args.description if args.description else None,
        "enabled": True,
        "branch": {
            "default": args.branch if args.branch else "main",
            "current": None,
            "protected": ["main", "master"]
        }
    }

    write_json(repo_file, repo_data)
    print(f"Repository '{repo_id}' added successfully")


def repo_list_cmd(_: argparse.Namespace) -> None:
    """List all registered repositories."""
    items = []
    for repo_path in sorted(REPOSITORIES_DIR.glob("*.json")):
        repo_data = read_json(repo_path)
        items.append(repo_data)
    print(json.dumps(items, indent=2, ensure_ascii=True))


def repo_validate_cmd(args: argparse.Namespace) -> None:
    """Validate repositories and dependencies."""
    ensure_state()

    # Create repository manager
    manager = repository_manager()

    # Check if validating specific repository or all
    if args.repo:
        # Validate single repository
        errors = manager.validate(args.repo)
        if errors:
            print(f"❌ Repository '{args.repo}' validation failed:")
            for error in errors:
                print(f"  - {error}")
            raise SystemExit(1)
        else:
            print(f"✅ Repository '{args.repo}' is valid")
    else:
        # Validate all repositories and dependencies
        print("Validating repositories...")
        repo_results = manager.validate_all()

        # Count errors
        total_repos = len(repo_results)
        invalid_repos = {repo_id: errs for repo_id, errs in repo_results.items() if errs}
        valid_repos = total_repos - len(invalid_repos)

        # Print repository results
        if invalid_repos:
            print(f"\n❌ Found {len(invalid_repos)} invalid repositories:")
            for repo_id, errors in invalid_repos.items():
                print(f"\n  {repo_id}:")
                for error in errors:
                    print(f"    - {error}")
        else:
            if total_repos > 0:
                print(f"✅ All {total_repos} repositories are valid")
            else:
                print("⚠️  No repositories registered")

        # Validate dependencies
        print("\nValidating dependencies...")
        dep_errors = manager.validate_dependencies()

        if dep_errors:
            print(f"❌ Found {len(dep_errors)} dependency errors:")
            for error in dep_errors:
                print(f"  - {error}")
            raise SystemExit(1)
        else:
            print("✅ All dependencies are valid")

        # Exit with error if any repositories are invalid
        if invalid_repos:
            raise SystemExit(1)


def test_agent_cmd(args: argparse.Namespace) -> None:
    configured = read_json_or_default(AGENTS_FILE, {"agents": {}}).get("agents", {}).get(args.agent)
    payload = {
        "agent": args.agent,
        "configured": bool(configured),
        "ready": False,
        "issues": [],
    }
    if configured:
        resolved = resolve_agent_profiles(configured, load_system_config())
        payload["protocol"] = resolved.get("protocol", "cli")
        payload["command"] = resolved.get("command", "")
        payload["model"] = resolved.get("model", "")
        if payload["protocol"] == "acp":
            transport = resolved.get("transport", {})
            payload["transport"] = transport
            command = transport.get("command", resolved.get("command", ""))
            payload["path"] = shutil.which(command) or ""
            payload["ready"] = bool(command) and bool(payload["path"])
            if not payload["ready"]:
                payload["issues"].append("ACP transport command is not executable")
        else:
            discovered = discover_cli_agent(args.agent, resolved.get("command", ""))
            if not discovered:
                payload["issues"].append("CLI agent binary not found")
            else:
                payload["path"] = discovered.get("path", "")
                payload["capabilities"] = discovered.get("capabilities", {})
                payload["ready"] = True
    else:
        discovered = discover_cli_agent(args.agent, args.agent)
        if not discovered:
            payload["issues"].append("agent is neither configured nor discoverable by binary name")
        else:
            payload.update(
                {
                    "protocol": discovered.get("protocol", "cli"),
                    "command": discovered.get("command", args.agent),
                    "path": discovered.get("path", ""),
                    "capabilities": discovered.get("capabilities", {}),
                    "ready": True,
                }
            )
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def cleanup_runs_cmd(args: argparse.Namespace) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    """
    Build and configure the Autoflow CLI argument parser.

    Creates the main ArgumentParser and all subcommands for interacting with
    the Autoflow workflow system. Each subcommand is configured with its
    respective arguments and bound to a handler function.

    Returns:
        Configured ArgumentParser with all Autoflow subcommands registered.

    Subcommands:
        init: Create .autoflow state directories
        new-spec: Create a spec scaffold with slug, title, and summary
        list-tasks: Print the task graph for a spec
        next-task: Print the next ready task for a role
        set-task-status: Update a task lifecycle state
        create-handoff: Write a handoff artifact between roles
        create-fix-request: Write a structured QA fix request artifact
        show-fix-request: Show the structured QA fix request data
        review-status: Show hash-based review approval status
        approve-spec: Approve the current spec/task contract hash
        invalidate-review: Manually invalidate approval state
        create-worktree: Create or reuse an isolated git worktree for a spec
        remove-worktree: Remove a spec worktree
        list-worktrees: Show known spec worktrees
        init-system-config: Write the local system config scaffold
        show-system-config: Show system memory/model/tool config
        discover-agents: Probe local agents and merge ACP registry entries
        sync-agents: Merge discovered CLI/ACP agents into .autoflow/agents.json
        write-memory: Append to global or spec memory
        show-memory: Show stored memory context
        show-strategy: Show accumulated planner/reflection strategy memory
        add-planner-note: Append a planner strategy note to strategy memory
        export-taskmaster: Export Autoflow tasks in Taskmaster-friendly JSON
        import-taskmaster: Import task data from Taskmaster-style JSON
        new-run: Create a runnable agent job
        resume-run: Create a retry run from an earlier run record
        complete-run: Close a run and update task state
        task-history: Show run history for a task
        show-events: Show recent event records for a spec
        workflow-state: Show ready tasks and next suggested action
        status: Print current specs and runs

    Examples:
        >>> parser = build_parser()
        >>> args = parser.parse_args(["status"])
        >>> args.func(args)
    """
    parser = argparse.ArgumentParser(description="Autoflow control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # Core system command
    init_cmd = sub.add_parser("init", help="create .autoflow state directories")
    init_cmd.set_defaults(func=lambda _: ensure_state())

    # Register spec commands from spec module
    spec.add_subparser(sub)

    # Register task commands from task module
    task.add_subparser(sub)

    # Handoff and fix request commands (kept in main CLI)
    handoff_cmd = sub.add_parser("create-handoff", help="write a handoff artifact")
    handoff_cmd.add_argument("--spec", required=True)
    handoff_cmd.add_argument("--task", required=True)
    handoff_cmd.add_argument("--role", required=True)
    handoff_cmd.add_argument("--summary", required=True)
    handoff_cmd.add_argument("--next-role", required=True)
    handoff_cmd.add_argument("--result", required=True)
    handoff_cmd.set_defaults(func=create_handoff)

    fix_request_cmd = sub.add_parser("create-fix-request", help="write a structured QA fix request artifact")
    fix_request_cmd.add_argument("--spec", required=True)
    fix_request_cmd.add_argument("--task", required=True)
    fix_request_cmd.add_argument("--summary", required=True)
    fix_request_cmd.add_argument("--result", required=True)
    fix_request_cmd.add_argument("--findings-json", default="")
    fix_request_cmd.add_argument("--findings-file", default="")
    fix_request_cmd.set_defaults(func=create_fix_request_cmd)

    show_fix_cmd = sub.add_parser("show-fix-request", help="show the structured QA fix request data")
    show_fix_cmd.add_argument("--spec", required=True)
    show_fix_cmd.set_defaults(func=show_fix_request)

    # Register worktree commands from worktree module
    worktree.add_subparser(sub)

    # Register repository commands from repository module
    repository.add_subparser(sub)

    # Register system commands from system module
    system.add_subparser(sub)

    # Register agent commands from agent module
    agent.add_subparser(sub)

    # Register memory commands from memory module
    memory.add_subparser(sub)

    # Register review commands from review module
    review.add_subparser(sub)

    # Strategy and planner commands (kept in main CLI)
    strategy_cmd = sub.add_parser("show-strategy", help="show accumulated planner/reflection strategy memory")
    strategy_cmd.add_argument("--spec", required=True)
    strategy_cmd.set_defaults(func=show_strategy_cmd)

    planner_cmd = sub.add_parser("add-planner-note", help="append a planner strategy note to strategy memory")
    planner_cmd.add_argument("--spec", required=True)
    planner_cmd.add_argument("--title", default="")
    planner_cmd.add_argument("--content", default="")
    planner_cmd.add_argument("--note", default="")
    planner_cmd.add_argument("--category", default="strategy")
    planner_cmd.add_argument("--scope", choices=["global", "spec"], default="spec")
    planner_cmd.set_defaults(func=add_planner_note_cmd)

    # Register integration commands from integration module
    integration.add_subparser(sub)

    # Register run commands from run module
    run.add_subparser(sub)

    # Event and workflow commands (kept in main CLI)
    events_cmd = sub.add_parser("show-events", help="show recent event records for a spec")
    events_cmd.add_argument("--spec", required=True)
    events_cmd.add_argument("--limit", type=int, default=20)
    events_cmd.set_defaults(func=show_events)

    workflow_cmd = sub.add_parser("workflow-state", help="show ready tasks and the next suggested action")
    workflow_cmd.add_argument("--spec", required=True)
    workflow_cmd.set_defaults(func=workflow_state)

    status_cmd = sub.add_parser("status", help="print current specs and runs")
    status_cmd.set_defaults(func=show_status)

    return parser


def main() -> None:
    """
    Main entry point for the Autoflow CLI.

    Parses command-line arguments and dispatches to the appropriate command handler.
    Each command is implemented as a separate function that receives the parsed arguments.

    The CLI uses argparse for argument parsing, with subcommands for each major operation:
    - init: Initialize Autoflow state directories
    - new-spec: Create a new specification
    - list-tasks: Show tasks for a spec
    - create-worktree: Create a git worktree for isolated development
    - status: Show overall Autoflow status
    - And many more...

    Error Handling:
        - Argument parsing errors are handled by argparse and display usage information
        - Command-specific errors are handled by individual command functions
        - Unhandled exceptions will propagate and display a traceback

    Example:
        # Initialize Autoflow
        python scripts/autoflow.py init

        # Create a new spec
        python scripts/autoflow.py new-spec --title "Add Feature" --summary "Description"

        # Show status
        python scripts/autoflow.py status
    """
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
