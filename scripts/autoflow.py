#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
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
AGENTS_FILE = STATE_DIR / "agents.json"
BMAD_DIR = ROOT / "templates" / "bmad"
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
    for path in [STATE_DIR, SPECS_DIR, TASKS_DIR, RUNS_DIR, LOGS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


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


def spec_files(slug: str) -> dict[str, Path]:
    directory = spec_dir(slug)
    return {
        "dir": directory,
        "spec": directory / "spec.md",
        "metadata": directory / "metadata.json",
        "handoff": directory / "handoff.md",
        "handoffs_dir": directory / "handoffs",
    }


def task_file(spec_slug: str) -> Path:
    return TASKS_DIR / f"{spec_slug}.json"


def load_tasks(spec_slug: str) -> dict[str, Any]:
    path = task_file(spec_slug)
    if not path.exists():
        raise SystemExit(f"missing task file: {path}")
    return read_json(path)


def save_tasks(spec_slug: str, data: dict[str, Any]) -> None:
    data["updated_at"] = now_stamp()
    write_json(task_file(spec_slug), data)


def task_lookup(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            return task
    raise SystemExit(f"unknown task: {task_id}")


def latest_handoffs(spec_slug: str, limit: int = 3) -> list[Path]:
    handoffs_dir = spec_files(spec_slug)["handoffs_dir"]
    if not handoffs_dir.exists():
        return []
    return sorted(handoffs_dir.glob("*.md"))[-limit:]


def update_spec_metadata(spec_slug: str, **updates: Any) -> None:
    metadata_path = spec_files(spec_slug)["metadata"]
    metadata = read_json(metadata_path)
    metadata.update(updates)
    metadata["updated_at"] = now_stamp()
    write_json(metadata_path, metadata)


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
                "The system can prepare task branches.",
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
    }
    handoff = "# Handoff\n\nInitial spec created. Next role should refine scope and derive tasks.\n"
    files["spec"].write_text(spec_markdown, encoding="utf-8")
    files["handoff"].write_text(handoff, encoding="utf-8")
    write_json(files["metadata"], metadata)
    if not task_file(slug).exists():
        write_json(
            task_file(slug),
            {
                "spec_slug": slug,
                "updated_at": now_stamp(),
                "tasks": default_tasks(),
            },
        )
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
    save_tasks(args.spec, data)
    print(json.dumps(task, indent=2, ensure_ascii=True))


def write_handoff(spec_slug: str, task_id: str, role: str, summary: str, next_role: str, result: str) -> Path:
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
    return handoff_path


def create_handoff(args: argparse.Namespace) -> None:
    path = write_handoff(args.spec, args.task, args.role, args.summary, args.next_role, args.result)
    print(str(path))


def build_prompt(spec_slug: str, role: str, task_id: str | None) -> str:
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id) if task_id else next_task_data(spec_slug, role)
    handoff_sections = []
    for handoff_path in latest_handoffs(spec_slug):
        handoff_sections.append(f"### {handoff_path.name}\n")
        handoff_sections.append(handoff_path.read_text(encoding="utf-8"))
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


def create_run(args: argparse.Namespace) -> None:
    ensure_state()
    agents = load_agents()
    if args.agent not in agents:
        raise SystemExit(f"unknown agent: {args.agent}")
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
    agent = agents[args.agent]
    run_id = f"{now_stamp()}-{slugify(args.role)}-{slugify(args.spec)}-{slugify(chosen_task)}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(build_prompt(args.spec, args.role, chosen_task), encoding="utf-8")
    branch = args.branch or f"codex/{slugify(args.spec)}-{slugify(chosen_task)}"
    command = [agent.command, *agent.args, str(prompt_path)]
    run_script = run_dir / "run.sh"
    run_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(ROOT))}",
                f"exec scripts/run-agent.sh {shlex.quote(args.agent)} {shlex.quote(str(prompt_path))}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    summary_path = run_dir / "summary.md"
    summary_path.write_text("# Run Summary\n\nFill after execution.\n", encoding="utf-8")
    os.chmod(run_script, 0o755)
    task["status"] = "in_progress"
    task.setdefault("notes", []).append(
        {"at": now_stamp(), "note": f"run {run_id} created for role {args.role}"}
    )
    save_tasks(args.spec, tasks)
    metadata = {
        "id": run_id,
        "spec": args.spec,
        "task": chosen_task,
        "role": args.role,
        "agent": args.agent,
        "branch": branch,
        "created_at": now_stamp(),
        "command_preview": command,
        "status": "created",
    }
    write_json(run_dir / "run.json", metadata)
    print(str(run_dir))


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
    save_tasks(metadata["spec"], tasks)
    next_role = "reviewer" if metadata["role"] != "reviewer" else "maintainer"
    handoff_path = write_handoff(
        metadata["spec"], metadata["task"], metadata["role"], summary, next_role, args.result
    )
    print(json.dumps({"run": metadata["id"], "task_status": task["status"], "handoff": str(handoff_path)}, indent=2))


def workflow_state(args: argparse.Namespace) -> None:
    data = load_tasks(args.spec)
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
    payload = {
        "spec": args.spec,
        "active_runs": active_runs,
        "ready_tasks": ready,
        "blocked_or_active_tasks": blocked,
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

    run_cmd = sub.add_parser("new-run", help="create a runnable agent job")
    run_cmd.add_argument("--spec", required=True)
    run_cmd.add_argument("--role", required=True)
    run_cmd.add_argument("--agent", required=True)
    run_cmd.add_argument("--task")
    run_cmd.add_argument("--branch")
    run_cmd.set_defaults(func=create_run)

    complete_cmd = sub.add_parser("complete-run", help="close a run and update task state")
    complete_cmd.add_argument("--run", required=True)
    complete_cmd.add_argument("--result", required=True)
    complete_cmd.add_argument("--summary", default="")
    complete_cmd.set_defaults(func=complete_run)

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
