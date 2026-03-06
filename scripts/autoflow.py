#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
SPECS_DIR = STATE_DIR / "specs"
TASKS_DIR = STATE_DIR / "tasks"
RUNS_DIR = STATE_DIR / "runs"
LOGS_DIR = STATE_DIR / "logs"
WORKTREES_DIR = STATE_DIR / "worktrees" / "tasks"
AGENTS_FILE = STATE_DIR / "agents.json"
BMAD_DIR = ROOT / "templates" / "bmad"
REVIEW_STATE_FILE = "review_state.json"
EVENTS_FILE = "events.jsonl"
QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
VALID_TASK_STATUSES = {
    "todo",
    "in_progress",
    "in_review",
    "needs_changes",
    "blocked",
    "done",
}
RUN_RESULTS = {"success", "needs_changes", "blocked", "failed"}


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_stamp() -> str:
    return now_utc().strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    output = []
    for ch in value.lower():
        if ch.isalnum():
            output.append(ch)
        elif ch in {" ", "_", "-", "/", "."}:
            output.append("-")
    slug = "".join(output).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "spec"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_state() -> None:
    for path in [STATE_DIR, SPECS_DIR, TASKS_DIR, RUNS_DIR, LOGS_DIR, WORKTREES_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def run_cmd(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd or ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


@dataclass
class AgentSpec:
    name: str
    command: str
    args: list[str]


def load_agents() -> dict[str, AgentSpec]:
    if not AGENTS_FILE.exists():
        raise SystemExit(
            f"missing {AGENTS_FILE}. copy config/agents.example.json to .autoflow/agents.json first"
        )
    data = read_json(AGENTS_FILE)
    agents = {}
    for name, spec in data.get("agents", {}).items():
        agents[name] = AgentSpec(
            name=name,
            command=spec["command"],
            args=list(spec.get("args", [])),
        )
    return agents


def spec_dir(slug: str) -> Path:
    return SPECS_DIR / slug


def task_file(spec_slug: str) -> Path:
    return TASKS_DIR / f"{spec_slug}.json"


def worktree_path(spec_slug: str) -> Path:
    return WORKTREES_DIR / spec_slug


def worktree_branch(spec_slug: str) -> str:
    return f"codex/{slugify(spec_slug)}"


def spec_files(slug: str) -> dict[str, Path]:
    directory = spec_dir(slug)
    return {
        "dir": directory,
        "spec": directory / "spec.md",
        "metadata": directory / "metadata.json",
        "handoff": directory / "handoff.md",
        "handoffs_dir": directory / "handoffs",
        "review_state": directory / REVIEW_STATE_FILE,
        "events": directory / EVENTS_FILE,
        "qa_fix_request": directory / QA_FIX_REQUEST_FILE,
    }


def review_state_default() -> dict[str, Any]:
    return {
        "approved": False,
        "approved_by": "",
        "approved_at": "",
        "spec_hash": "",
        "review_count": 0,
        "feedback": [],
        "invalidated_at": "",
        "invalidated_reason": "",
    }


def read_json_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return read_json(path)
    except (OSError, json.JSONDecodeError):
        return default


def load_review_state(spec_slug: str) -> dict[str, Any]:
    return read_json_or_default(spec_files(spec_slug)["review_state"], review_state_default())


def save_review_state(spec_slug: str, state: dict[str, Any]) -> None:
    write_json(spec_files(spec_slug)["review_state"], state)


def load_tasks(spec_slug: str) -> dict[str, Any]:
    path = task_file(spec_slug)
    if not path.exists():
        raise SystemExit(f"missing task file: {path}")
    return read_json(path)


def task_lookup(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            return task
    raise SystemExit(f"unknown task: {task_id}")


def record_event(spec_slug: str, event_type: str, payload: dict[str, Any]) -> None:
    files = spec_files(spec_slug)
    files["events"].parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": now_stamp(),
        "type": event_type,
        "payload": payload,
    }
    with open(files["events"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True) + "\n")


def load_events(spec_slug: str, limit: int = 20) -> list[dict[str, Any]]:
    events_path = spec_files(spec_slug)["events"]
    if not events_path.exists():
        return []
    with open(events_path, encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def load_fix_request(spec_slug: str) -> str:
    path = spec_files(spec_slug)["qa_fix_request"]
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_fix_request(spec_slug: str, task_id: str, reviewer_summary: str, result: str) -> Path:
    path = spec_files(spec_slug)["qa_fix_request"]
    content = "\n".join(
        [
            f"# QA Fix Request: {task_id}",
            "",
            f"- created_at: {now_stamp()}",
            f"- result: {result}",
            "",
            "## Required follow-up",
            "",
            reviewer_summary,
            "",
            "## Retry policy",
            "",
            "- Read this file before retrying the implementation task.",
            "- Change approach instead of repeating the same edits.",
            "- Leave a handoff note explaining what changed in the retry.",
            "",
        ]
    )
    path.write_text(content, encoding="utf-8")
    record_event(spec_slug, "qa.fix_request_created", {"task": task_id, "result": result})
    return path


def clear_fix_request(spec_slug: str) -> None:
    path = spec_files(spec_slug)["qa_fix_request"]
    if path.exists():
        path.unlink()
        record_event(spec_slug, "qa.fix_request_cleared", {})


def compute_file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    return hashlib.md5(content.encode("utf-8"), usedforsecurity=False).hexdigest()


def planning_contract(spec_slug: str) -> dict[str, Any]:
    task_data = load_tasks(spec_slug)
    tasks = []
    for task in task_data.get("tasks", []):
        tasks.append(
            {
                "id": task["id"],
                "title": task["title"],
                "depends_on": task.get("depends_on", []),
                "owner_role": task["owner_role"],
                "acceptance_criteria": task.get("acceptance_criteria", []),
            }
        )
    return {"tasks": tasks}


def compute_spec_hash(spec_slug: str) -> str:
    files = spec_files(spec_slug)
    spec_hash = compute_file_hash(files["spec"])
    task_hash = hashlib.md5(
        json.dumps(planning_contract(spec_slug), sort_keys=True).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    combined = f"{spec_hash}:{task_hash}"
    return hashlib.md5(combined.encode("utf-8"), usedforsecurity=False).hexdigest()


def sync_review_state(spec_slug: str, reason: str = "planning_artifacts_changed") -> dict[str, Any]:
    state = load_review_state(spec_slug)
    if state.get("approved") and state.get("spec_hash") != compute_spec_hash(spec_slug):
        state["approved"] = False
        state["invalidated_at"] = now_stamp()
        state["invalidated_reason"] = reason
        save_review_state(spec_slug, state)
        record_event(spec_slug, "review.invalidated", {"reason": reason})
    return state


def review_status_summary(spec_slug: str) -> dict[str, Any]:
    state = sync_review_state(spec_slug)
    current_hash = compute_spec_hash(spec_slug)
    return {
        "approved": state.get("approved", False),
        "valid": bool(state.get("approved")) and state.get("spec_hash") == current_hash,
        "approved_by": state.get("approved_by", ""),
        "approved_at": state.get("approved_at", ""),
        "review_count": state.get("review_count", 0),
        "feedback_count": len(state.get("feedback", [])),
        "spec_changed": bool(state.get("spec_hash")) and state.get("spec_hash") != current_hash,
        "invalidated_at": state.get("invalidated_at", ""),
        "invalidated_reason": state.get("invalidated_reason", ""),
    }


def save_tasks(spec_slug: str, data: dict[str, Any], *, reason: str = "task_state_updated") -> None:
    data["updated_at"] = now_stamp()
    write_json(task_file(spec_slug), data)
    sync_review_state(spec_slug, reason=reason)


def detect_base_branch() -> str:
    for branch in ["main", "master"]:
        result = run_cmd(["git", "rev-parse", "--verify", branch], check=False)
        if result.returncode == 0:
            return branch
    current = run_cmd(["git", "branch", "--show-current"]).stdout.strip()
    return current or "main"


def load_bmad_template(role: str) -> str:
    path = BMAD_DIR / f"{role}.md"
    if not path.exists():
        return "No BMAD template configured for this role."
    return path.read_text(encoding="utf-8")


def run_metadata_iter() -> list[dict[str, Any]]:
    items = []
    if not RUNS_DIR.exists():
        return items
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            items.append(read_json(metadata_path))
    return items


def active_runs_for_spec(spec_slug: str) -> list[dict[str, Any]]:
    return [
        item
        for item in run_metadata_iter()
        if item.get("spec") == spec_slug and item.get("status") != "completed"
    ]


def task_run_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    history = [
        item
        for item in run_metadata_iter()
        if item.get("spec") == spec_slug and item.get("task") == task_id
    ]
    return sorted(history, key=lambda item: item.get("created_at", ""))[-limit:]


def latest_handoffs(spec_slug: str, limit: int = 3) -> list[Path]:
    handoffs_dir = spec_files(spec_slug)["handoffs_dir"]
    if not handoffs_dir.exists():
        return []
    return sorted(handoffs_dir.glob("*.md"))[-limit:]


def worktree_context(spec_slug: str) -> str:
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


def default_tasks() -> list[dict[str, Any]]:
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


def create_spec(args: argparse.Namespace) -> None:
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


def list_tasks(args: argparse.Namespace) -> None:
    tasks = load_tasks(args.spec)
    print(json.dumps(tasks, indent=2, ensure_ascii=True))


def next_task_data(spec_slug: str, role: str | None = None) -> dict[str, Any] | None:
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
            dep_task = task_lookup(tasks, dep)
            if dep_task["status"] != "done":
                blocked = True
                break
        if not blocked:
            return task
    return None


def next_task(args: argparse.Namespace) -> None:
    task = next_task_data(args.spec, args.role)
    if not task:
        print("{}")
        return
    print(json.dumps(task, indent=2, ensure_ascii=True))


def set_task_status(args: argparse.Namespace) -> None:
    if args.status not in VALID_TASK_STATUSES:
        raise SystemExit(f"invalid status: {args.status}")
    data = load_tasks(args.spec)
    task = task_lookup(data, args.task)
    task["status"] = args.status
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": args.note or f"status set to {args.status}"}
    )
    save_tasks(args.spec, data, reason="task_status_updated")
    record_event(args.spec, "task.status_updated", {"task": args.task, "status": args.status})
    print(json.dumps(task, indent=2, ensure_ascii=True))


def write_handoff(
    spec_slug: str,
    task_id: str,
    role: str,
    summary: str,
    next_role: str,
    result: str,
) -> Path:
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
    path = write_handoff(args.spec, args.task, args.role, args.summary, args.next_role, args.result)
    print(str(path))


def approve_spec(args: argparse.Namespace) -> None:
    state = load_review_state(args.spec)
    state["approved"] = True
    state["approved_by"] = args.approved_by
    state["approved_at"] = now_stamp()
    state["spec_hash"] = compute_spec_hash(args.spec)
    state["review_count"] = state.get("review_count", 0) + 1
    state["invalidated_at"] = ""
    state["invalidated_reason"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.approved", {"approved_by": args.approved_by})
    print(json.dumps(review_status_summary(args.spec), indent=2, ensure_ascii=True))


def invalidate_review(args: argparse.Namespace) -> None:
    state = load_review_state(args.spec)
    state["approved"] = False
    state["invalidated_at"] = now_stamp()
    state["invalidated_reason"] = args.reason
    state["spec_hash"] = ""
    save_review_state(args.spec, state)
    record_event(args.spec, "review.invalidated", {"reason": args.reason})
    print(json.dumps(review_status_summary(args.spec), indent=2, ensure_ascii=True))


def show_review_status(args: argparse.Namespace) -> None:
    print(json.dumps(review_status_summary(args.spec), indent=2, ensure_ascii=True))


def build_prompt(spec_slug: str, role: str, task_id: str | None, resume_from: str | None = None) -> str:
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id) if task_id else next_task_data(spec_slug, role)
    review_summary = review_status_summary(spec_slug)
    fix_request = load_fix_request(spec_slug)
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
            "## BMAD operating frame",
            load_bmad_template(role),
            "",
            worktree_context(spec_slug),
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
            "## QA fix request",
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
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(build_prompt(spec_slug, role, task_id, resume_from=resume_from), encoding="utf-8")
    branch = branch or f"codex/{slugify(spec_slug)}-{slugify(task_id)}"
    target_workdir = worktree_path(spec_slug) if worktree_path(spec_slug).exists() else ROOT
    command = [agent.command, *agent.args, str(prompt_path)]
    run_script = run_dir / "run.sh"
    run_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(target_workdir))}",
                f"exec {shlex.quote(str(ROOT / 'scripts' / 'run-agent.sh'))} {shlex.quote(agent_name)} {shlex.quote(str(prompt_path))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    summary_path = run_dir / "summary.md"
    summary_path.write_text("# Run Summary\n\nFill after execution.\n", encoding="utf-8")
    os.chmod(run_script, 0o755)
    metadata = {
        "id": run_id,
        "spec": spec_slug,
        "task": task_id,
        "role": role,
        "agent": agent_name,
        "branch": branch,
        "workdir": str(target_workdir),
        "created_at": now_stamp(),
        "command_preview": command,
        "status": "created",
        "attempt_count": len(task_run_history(spec_slug, task_id)) + 1,
        "resume_from": resume_from or "",
        "resume_command": f"python3 scripts/autoflow.py resume-run --run {run_id}",
        "retry_policy": {
            "max_automatic_attempts": 3,
            "requires_fix_request_after_review_failure": True,
        },
    }
    write_json(run_dir / "run.json", metadata)
    record_event(spec_slug, "run.created", {"run": run_id, "task": task_id, "role": role})
    return run_dir


def create_run(args: argparse.Namespace) -> None:
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
    task = task_lookup(tasks, chosen_task)
    expected_role = "reviewer" if task["status"] == "in_review" and args.role == "reviewer" else task["owner_role"]
    if expected_role != args.role:
        raise SystemExit(f"task {chosen_task} belongs to role {task['owner_role']}, not {args.role}")
    if task["status"] not in {"todo", "needs_changes", "in_progress", "in_review"}:
        raise SystemExit(f"task {chosen_task} is not runnable from status {task['status']}")
    task["status"] = "in_progress"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": f"run pending for role {args.role}"}
    )
    save_tasks(args.spec, tasks, reason="task_status_updated")
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
    task = task_lookup(tasks, metadata["task"])
    task["status"] = "in_progress"
    task.setdefault("notes", []).append({"at": now_stamp(), "note": f"retry created from {args.run}"})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated")
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


def complete_run(args: argparse.Namespace) -> None:
    if args.result not in RUN_RESULTS:
        raise SystemExit(f"invalid result: {args.result}")
    run_dir = RUNS_DIR / args.run
    metadata_path = run_dir / "run.json"
    if not metadata_path.exists():
        raise SystemExit(f"unknown run: {args.run}")
    metadata = read_json(metadata_path)
    metadata["status"] = "completed"
    metadata["result"] = args.result
    metadata["completed_at"] = now_stamp()
    write_json(metadata_path, metadata)
    summary = args.summary or f"Run {args.run} completed with result {args.result}."
    (run_dir / "summary.md").write_text(f"# Run Summary\n\n{summary}\n", encoding="utf-8")

    tasks = load_tasks(metadata["spec"])
    task = task_lookup(tasks, metadata["task"])
    if metadata["role"] == "reviewer":
        next_status = "done" if args.result == "success" else args.result
    elif args.result == "success":
        next_status = "in_review"
    else:
        next_status = args.result
    status_map = {
        "success": next_status,
        "needs_changes": "needs_changes",
        "blocked": "blocked",
        "failed": "blocked",
    }
    task["status"] = status_map[args.result]
    task.setdefault("notes", []).append({"at": now_stamp(), "note": summary})
    save_tasks(metadata["spec"], tasks, reason="task_status_updated")
    next_role = "reviewer" if metadata["role"] != "reviewer" else task["owner_role"]
    fix_request_path = ""
    if metadata["role"] == "reviewer" and args.result in {"needs_changes", "blocked", "failed"}:
        fix_request_path = str(write_fix_request(metadata["spec"], metadata["task"], summary, args.result))
    if metadata["role"] == "implementation-runner" and args.result == "success":
        clear_fix_request(metadata["spec"])
    handoff_path = write_handoff(
        metadata["spec"], metadata["task"], metadata["role"], summary, next_role, args.result
    )
    record_event(
        metadata["spec"],
        "run.completed",
        {
            "run": metadata["id"],
            "task": metadata["task"],
            "role": metadata["role"],
            "result": args.result,
            "fix_request": fix_request_path,
        },
    )
    print(
        json.dumps(
            {
                "run": metadata["id"],
                "task_status": task["status"],
                "handoff": str(handoff_path),
                "fix_request": fix_request_path,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def show_task_history(args: argparse.Namespace) -> None:
    print(json.dumps(task_run_history(args.spec, args.task), indent=2, ensure_ascii=True))


def show_events(args: argparse.Namespace) -> None:
    print(json.dumps(load_events(args.spec, args.limit), indent=2, ensure_ascii=True))


def create_worktree(args: argparse.Namespace) -> None:
    ensure_state()
    path = worktree_path(args.spec)
    branch = worktree_branch(args.spec)
    base_branch = args.base_branch or detect_base_branch()
    metadata = read_json_or_default(spec_files(args.spec)["metadata"], {})

    if path.exists():
        metadata["worktree"] = {
            "path": str(path),
            "branch": branch,
            "base_branch": base_branch,
        }
        write_json(spec_files(args.spec)["metadata"], metadata)
        print(json.dumps(metadata["worktree"], indent=2, ensure_ascii=True))
        return

    branch_exists = run_cmd(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0
    if branch_exists:
        run_cmd(["git", "worktree", "add", str(path), branch])
    else:
        run_cmd(["git", "worktree", "add", "-b", branch, str(path), base_branch])

    metadata["worktree"] = {
        "path": str(path),
        "branch": branch,
        "base_branch": base_branch,
    }
    write_json(spec_files(args.spec)["metadata"], metadata)
    record_event(args.spec, "worktree.created", metadata["worktree"])
    print(json.dumps(metadata["worktree"], indent=2, ensure_ascii=True))


def remove_worktree(args: argparse.Namespace) -> None:
    path = worktree_path(args.spec)
    branch = worktree_branch(args.spec)
    if path.exists():
        run_cmd(["git", "worktree", "remove", "--force", str(path)])
    if args.delete_branch:
        run_cmd(["git", "branch", "-D", branch], check=False)
    metadata = read_json_or_default(spec_files(args.spec)["metadata"], {})
    metadata["worktree"] = {"path": "", "branch": branch, "base_branch": detect_base_branch()}
    write_json(spec_files(args.spec)["metadata"], metadata)
    record_event(args.spec, "worktree.removed", {"path": str(path), "branch_deleted": args.delete_branch})
    print(json.dumps(metadata["worktree"], indent=2, ensure_ascii=True))


def list_worktrees(_: argparse.Namespace) -> None:
    items = []
    for metadata_path in sorted(SPECS_DIR.glob("*/metadata.json")):
        metadata = read_json(metadata_path)
        items.append(
            {
                "spec": metadata.get("slug", metadata_path.parent.name),
                "worktree": metadata.get("worktree", {}),
            }
        )
    print(json.dumps(items, indent=2, ensure_ascii=True))


def workflow_state(args: argparse.Namespace) -> None:
    data = load_tasks(args.spec)
    review_summary = review_status_summary(args.spec)
    active_runs = active_runs_for_spec(args.spec)
    ready = []
    blocked = []
    for task in data.get("tasks", []):
        deps_done = all(task_lookup(data, dep)["status"] == "done" for dep in task.get("depends_on", []))
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
        "worktree": read_json_or_default(spec_files(args.spec)["metadata"], {}).get("worktree", {}),
        "fix_request_present": bool(load_fix_request(args.spec)),
        "active_runs": active_runs,
        "ready_tasks": ready,
        "blocked_or_active_tasks": blocked,
        "blocking_reason": blocking_reason,
        "recommended_next_action": None if active_runs else next_entry,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def show_status(_: argparse.Namespace) -> None:
    ensure_state()
    specs = sorted(p.name for p in SPECS_DIR.iterdir() if p.is_dir())
    runs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
    status = {"specs": specs, "runs": runs}
    print(json.dumps(status, indent=2, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autoflow control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    init_cmd = sub.add_parser("init", help="create .autoflow state directories")
    init_cmd.set_defaults(func=lambda _: ensure_state())

    spec_cmd = sub.add_parser("new-spec", help="create a spec scaffold")
    spec_cmd.add_argument("--slug", default="")
    spec_cmd.add_argument("--title", required=True)
    spec_cmd.add_argument("--summary", required=True)
    spec_cmd.set_defaults(func=create_spec)

    tasks_cmd = sub.add_parser("list-tasks", help="print the task graph for a spec")
    tasks_cmd.add_argument("--spec", required=True)
    tasks_cmd.set_defaults(func=list_tasks)

    next_cmd = sub.add_parser("next-task", help="print the next ready task")
    next_cmd.add_argument("--spec", required=True)
    next_cmd.add_argument("--role")
    next_cmd.set_defaults(func=next_task)

    set_task_cmd = sub.add_parser("set-task-status", help="update a task lifecycle state")
    set_task_cmd.add_argument("--spec", required=True)
    set_task_cmd.add_argument("--task", required=True)
    set_task_cmd.add_argument("--status", required=True)
    set_task_cmd.add_argument("--note", default="")
    set_task_cmd.set_defaults(func=set_task_status)

    handoff_cmd = sub.add_parser("create-handoff", help="write a handoff artifact")
    handoff_cmd.add_argument("--spec", required=True)
    handoff_cmd.add_argument("--task", required=True)
    handoff_cmd.add_argument("--role", required=True)
    handoff_cmd.add_argument("--summary", required=True)
    handoff_cmd.add_argument("--next-role", required=True)
    handoff_cmd.add_argument("--result", required=True)
    handoff_cmd.set_defaults(func=create_handoff)

    review_status_cmd = sub.add_parser("review-status", help="show hash-based review approval status")
    review_status_cmd.add_argument("--spec", required=True)
    review_status_cmd.set_defaults(func=show_review_status)

    approve_cmd = sub.add_parser("approve-spec", help="approve the current spec/task contract hash")
    approve_cmd.add_argument("--spec", required=True)
    approve_cmd.add_argument("--approved-by", default="user")
    approve_cmd.set_defaults(func=approve_spec)

    invalidate_cmd = sub.add_parser("invalidate-review", help="manually invalidate approval state")
    invalidate_cmd.add_argument("--spec", required=True)
    invalidate_cmd.add_argument("--reason", default="manual_invalidation")
    invalidate_cmd.set_defaults(func=invalidate_review)

    worktree_create_cmd = sub.add_parser("create-worktree", help="create or reuse an isolated git worktree for a spec")
    worktree_create_cmd.add_argument("--spec", required=True)
    worktree_create_cmd.add_argument("--base-branch", default="")
    worktree_create_cmd.set_defaults(func=create_worktree)

    worktree_remove_cmd = sub.add_parser("remove-worktree", help="remove a spec worktree")
    worktree_remove_cmd.add_argument("--spec", required=True)
    worktree_remove_cmd.add_argument("--delete-branch", action="store_true")
    worktree_remove_cmd.set_defaults(func=remove_worktree)

    worktree_list_cmd = sub.add_parser("list-worktrees", help="show known spec worktrees")
    worktree_list_cmd.set_defaults(func=list_worktrees)

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

    complete_cmd = sub.add_parser("complete-run", help="close a run and update task state")
    complete_cmd.add_argument("--run", required=True)
    complete_cmd.add_argument("--result", required=True)
    complete_cmd.add_argument("--summary", default="")
    complete_cmd.set_defaults(func=complete_run)

    history_cmd = sub.add_parser("task-history", help="show run history for a task")
    history_cmd.add_argument("--spec", required=True)
    history_cmd.add_argument("--task", required=True)
    history_cmd.set_defaults(func=show_task_history)

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
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
