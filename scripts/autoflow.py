#!/usr/bin/env python3
"""Autoflow CLI - Control Plane Interface."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts.cli.utils import (
    EVENTS_FILE, QA_FIX_REQUEST_FILE, QA_FIX_REQUEST_JSON_FILE, RUNS_DIR, SPECS_DIR,
    ensure_state, load_tasks, now_stamp, print_json, read_json_or_default,
    review_status_summary, save_strategy_memory, spec_files, stale_runs_for_spec,
)
from scripts.cli import worktree, memory, review, agent, system, integration
from scripts.cli import spec, task, run, repository


# =============================================================================
# Strategy Functions
# =============================================================================

def add_planner_note(spec_slug: str, title: str, content: str, category: str = "strategy", scope: str = "spec") -> Path:
    from scripts.cli.utils import load_strategy_memory
    memory = load_strategy_memory(scope, spec_slug if scope == "spec" else None)
    notes = memory.setdefault("planner_notes", [])
    notes.append({"at": now_stamp(), "title": title, "category": category, "content": content.strip()})
    memory["planner_notes"] = notes[-25:]
    return save_strategy_memory(scope, memory, spec_slug if scope == "spec" else None)


def strategy_summary(spec_slug: str) -> dict[str, Any]:
    from scripts.cli.utils import load_strategy_memory
    spec_memory = load_strategy_memory("spec", spec_slug)
    return {
        "updated_at": spec_memory.get("updated_at", ""),
        "playbook": spec_memory.get("playbook", []),
        "planner_notes": spec_memory.get("planner_notes", [])[-5:],
        "recent_reflections": spec_memory.get("reflections", [])[-5:],
        "stats": spec_memory.get("stats", {}),
    }


def render_strategy_context(spec_slug: str) -> str:
    summary = strategy_summary(spec_slug)
    lines = ["## Strategy memory", ""]
    if summary.get("playbook"):
        lines.extend(["### Playbook", ""])
        for item in summary["playbook"][:5]:
            target = item.get("category") or item.get("file") or "general"
            lines.append(f"- {target}: {item['rule']} (evidence={item['evidence_count']})")
        lines.append("")
    if summary.get("planner_notes"):
        lines.extend(["### Planner notes", ""])
        for note in summary["planner_notes"][-3:]:
            lines.append(f"- {note['title']} [{note['category']}]")
            lines.append(f"  {note['content']}")
        lines.append("")
    if summary.get("recent_reflections"):
        lines.extend(["### Recent reflections", ""])
        for item in summary["recent_reflections"][-3:]:
            lines.append(f"- {item['task']} / {item['role']} -> {item['result']}: {item['summary']}")
            for action in item.get("recommended_actions", [])[:2]:
                lines.append(f"  action: {action}")
        lines.append("")
    if len(lines) <= 2:
        lines.append("No strategy memory recorded yet.")
    return "\n".join(lines).strip()


# =============================================================================
# Event and Fix Request Functions
# =============================================================================

def load_events(spec_slug: str, limit: int = 20) -> list[dict[str, Any]]:
    events_path = spec_files(spec_slug)["events"]
    if not events_path.exists():
        return []
    with open(events_path, encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def load_fix_request(spec_slug: str) -> str:
    path = spec_files(spec_slug)["qa_fix_request"]
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_fix_request_data(spec_slug: str) -> dict[str, Any]:
    return read_json_or_default(
        spec_files(spec_slug)["qa_fix_request_json"],
        {"task": "", "result": "", "summary": "", "finding_count": 0, "findings": []},
    )


def format_fix_request_markdown(task_id: str, summary: str, result: str, findings: list[dict[str, Any]]) -> str:
    lines = [f"# QA Fix Request: {task_id}", "", f"**Result:** {result}", "", "## Summary", "", summary, "", f"**Findings:** {len(findings)}", ""]
    if findings:
        lines.extend(["## Findings", ""])
        for idx, finding in enumerate(findings, 1):
            lines.append(f"### {idx}. {finding.get('title', 'Untitled')}\n")
            if finding.get("file"):
                location = f"{finding['file']}:{finding['line']}" if finding.get("line") else finding["file"]
                lines.append(f"**Location:** `{location}`\n")
            if finding.get("severity") or finding.get("category"):
                meta = " ".join([f"**{k.title()}:** {v}" for k, v in [("severity", finding["severity"]), ("category", finding["category"])] if v])
                if meta:
                    lines.append(meta + "\n")
            if finding.get("body"):
                lines.append(finding["body"] + "\n")
            if finding.get("suggested_fix"):
                lines.append("**Suggested fix:**\n\n" + finding["suggested_fix"] + "\n")
    return "\n".join(lines)


# =============================================================================
# Run-related Helper Functions
# =============================================================================

def write_handoff(spec_slug: str, task_id: str, role: str, summary: str, next_role: str, result: str) -> Path:
    from scripts.cli.utils import record_event, slugify
    files = spec_files(spec_slug)
    files["handoffs_dir"].mkdir(parents=True, exist_ok=True)
    handoff_path = files["handoffs_dir"] / f"{now_stamp()}-{task_id}-{slugify(role)}.md"
    handoff_text = f"# Handoff: {task_id}\n\n- role: {role}\n- next_role: {next_role}\n- result: {result}\n- created_at: {now_stamp()}\n\n## Summary\n\n{summary}\n"
    handoff_path.write_text(handoff_text, encoding="utf-8")
    files["handoff"].write_text(handoff_text, encoding="utf-8")
    record_event(spec_slug, "handoff.created", {"task": task_id, "role": role, "result": result})
    return handoff_path


def clear_fix_request(spec_slug: str) -> None:
    from scripts.cli.utils import record_event
    files = spec_files(spec_slug)
    if files["qa_fix_request"].exists():
        files["qa_fix_request"].unlink()
    if files["qa_fix_request_json"].exists():
        files["qa_fix_request_json"].unlink()
    record_event(spec_slug, "fix_request.cleared", {})


def record_reflection(spec_slug: str, task_id: str, role: str, result: str, summary: str, actions: list[str]) -> Path:
    from scripts.cli.utils import load_strategy_memory
    memory = load_strategy_memory("spec", spec_slug)
    reflections = memory.setdefault("reflections", [])
    reflections.append({"at": now_stamp(), "task": task_id, "role": role, "result": result, "summary": summary, "recommended_actions": actions})
    memory["reflections"] = reflections[-25:]
    return save_strategy_memory("spec", memory, spec_slug)


def write_fix_request(spec_slug: str, task_id: str, summary: str, result: str, findings: list[dict[str, Any]] | None = None) -> Path:
    from scripts.cli.utils import normalize_findings, record_event
    if findings is None:
        findings = []
    normalized = normalize_findings(summary, findings)
    files = spec_files(spec_slug)
    files["qa_fix_request"].parent.mkdir(parents=True, exist_ok=True)
    markdown = format_fix_request_markdown(task_id, summary, result, normalized)
    files["qa_fix_request"].write_text(markdown, encoding="utf-8")
    payload = {"task": task_id, "result": result, "summary": summary, "finding_count": len(normalized), "findings": normalized}
    files["qa_fix_request_json"].write_text(json.dumps(payload, indent=2), encoding="utf-8")
    record_event(spec_slug, "fix_request.created", payload)
    return files["qa_fix_request"]


def parse_findings(args: argparse.Namespace) -> list[dict[str, Any]]:
    from scripts.cli.utils import normalize_findings
    findings = None
    if hasattr(args, "findings_json") and args.findings_json:
        findings = json.loads(args.findings_json)
    elif hasattr(args, "findings_file") and args.findings_file:
        findings = json.loads(Path(args.findings_file).read_text(encoding="utf-8"))
    return normalize_findings(args.summary, findings)


def task_run_history(spec_slug: str, task_id: str, limit: int = 5) -> list[dict[str, Any]]:
    runs = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        metadata_file = run_dir / "metadata.json"
        if not metadata_file.exists():
            continue
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if metadata.get("spec") == spec_slug and metadata.get("task") == task_id:
                runs.append(metadata)
                if len(runs) >= limit:
                    break
        except (json.JSONDecodeError, KeyError):
            continue
    return runs


def native_resume_preview(agent: dict) -> list[str]:
    lines = []
    if agent.get("resume"):
        resume_cfg = agent["resume"]
        if resume_cfg.get("mode") == "subcommand" and resume_cfg.get("subcommand"):
            subcmd = resume_cfg["subcommand"]
            args_str = " ".join(resume_cfg.get("args", []))
            lines.append(f"  {agent['name']} supports native resume via '{subcmd} {args_str}'")
        else:
            lines.append(f"  {agent['name']} supports native resume (check docs for usage)")
    return lines


def build_prompt(spec_slug: str, role: str, task_id: str | None, agent: dict, resume_from: str | None = None, run_id: str | None = None) -> str:
    from autoflow.core.sanitization import sanitize_dict, sanitize_value
    from scripts.cli.utils import (
        AGENT_RESULT_FILE, load_memory_context, load_review_state, load_strategy_memory,
        normalize_findings, planning_contract, sanitize_dict, task_lookup, spec_files, load_tasks,
    )
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id, spec_slug=spec_slug) if task_id else task.next_task_data(spec_slug, role)
    review_summary = review_status_summary(spec_slug)
    fix_request = load_fix_request(spec_slug)
    fix_request_data = load_fix_request_data(spec_slug)
    memory_context = load_memory_context(spec_slug, agent.get("memory_scopes"))
    strategy_context = render_strategy_context(spec_slug)
    agent_result_path = str(RUNS_DIR / run_id / AGENT_RESULT_FILE) if run_id else ""
    handoff_sections = []
    for handoff_path in sorted(files["handoffs_dir"].glob("*.md"), reverse=True)[:3]:
        handoff_sections.append(f"### {handoff_path.name}\n" + handoff_path.read_text(encoding="utf-8"))
    recovery = f"Recovery context for task {selected_task['id']}" if selected_task else "No task selected."

    return "\n".join([
        f"Role: {role}",
        f"Spec slug: {spec_slug}",
        f"Task id: {selected_task['id'] if selected_task else 'none'}",
        "",
        "Read the repository state and execute the role carefully.",
        "Follow the selected task acceptance criteria.",
        "Keep changes scoped and leave a concise handoff summary.",
        "",
        "## Backend configuration",
        json.dumps(sanitize_dict({
            "agent": agent.get("name"), "protocol": agent.get("protocol"), "command": agent.get("command"),
            "model": agent.get("model"), "model_profile": agent.get("model_profile"), "tools": agent.get("tools") or [],
            "tool_profile": agent.get("tool_profile"), "memory_scopes": agent.get("memory_scopes") or [],
            "native_resume_supported": bool(agent.get("resume")), "transport": agent.get("transport") or {},
        }), indent=2, ensure_ascii=True),
        "",
        "## Spec", files["spec"].read_text(encoding="utf-8"),
        "",
        "## Tasks", json.dumps(tasks, indent=2),
        "",
        "## Selected task", json.dumps(selected_task, indent=2) if selected_task else "none",
        "",
        "## Review approval status", json.dumps(review_summary, indent=2),
        "",
        "## QA fix request" if fix_request else "## QA fix request (none)", fix_request if fix_request else "none",
        "",
        "## QA fix request data", json.dumps(fix_request_data, indent=2),
        "",
        "## Memory context", memory_context,
        "",
        strategy_context,
        "",
        "## Handoffs", "\n".join(handoff_sections) if handoff_sections else "none",
        "",
        f"## Agent result output path: {agent_result_path}" if agent_result_path else "",
        "",
        "## Recovery context", recovery,
        "",
        f"## Resume from run: {resume_from}" if resume_from else "",
    ]).strip()


def complete_run_record(run_id: str, task_id: str, result: str, summary: str, findings: list[dict] | None = None, agent_output: str = "") -> dict:
    from scripts.cli.utils import load_run_metadata, write_run_metadata
    metadata = load_run_metadata(run_id)
    metadata["completed_at"] = now_stamp()
    metadata["task"] = task_id
    metadata["result"] = result
    metadata["summary"] = summary
    if findings:
        metadata["findings"] = findings
    if agent_output:
        metadata["agent_output"] = agent_output
    write_run_metadata(run_id, metadata)
    return metadata


def finalize_run_record(run_id: str, commit_hash: str | None = None) -> dict:
    from scripts.cli.utils import load_run_metadata, write_run_metadata
    metadata = load_run_metadata(run_id)
    metadata["finalized_at"] = now_stamp()
    if commit_hash:
        metadata["commit_hash"] = commit_hash
    write_run_metadata(run_id, metadata)
    return metadata


def recover_run_record(run_id: str, reason: str, dispatch: bool = False) -> dict:
    from scripts.cli.utils import load_run_metadata, write_run_metadata, slugify
    old_metadata = load_run_metadata(run_id)
    new_run_id = f"{now_stamp()}-recover-{slugify(old_metadata['spec'][:20])}"
    new_metadata = {
        **old_metadata, "run_id": new_run_id, "created_at": now_stamp(), "resume_from": run_id,
        "recovery_reason": reason, "dispatch": dispatch, "completed_at": "", "result": "",
    }
    write_run_metadata(new_run_id, new_metadata)
    return new_metadata


def run_metadata_iter() -> list[dict[str, Any]]:
    """Iterate over all run metadata."""
    runs = []
    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        metadata_file = run_dir / "metadata.json"
        if metadata_file.exists():
            try:
                runs.append(json.loads(metadata_file.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError):
                continue
    return sorted(runs, key=lambda r: r.get("created_at", ""), reverse=True)


def active_runs_for_spec(spec_slug: str) -> list[dict[str, Any]]:
    """Get active runs for a spec."""
    return [r for r in run_metadata_iter() if r.get("spec") == spec_slug and r.get("status") in {"created", "running", "stale"}]


# =============================================================================
# Workflow and Status Functions
# =============================================================================

def workflow_state(args: argparse.Namespace) -> None:
    from scripts.cli.utils import normalize_worktree_metadata
    from scripts.cli.task import task_lookup
    data = load_tasks(args.spec)
    review_summary = review_status_summary(args.spec)
    active_runs = run.active_runs_for_spec(args.spec)
    stale_runs = stale_runs_for_spec(args.spec)
    ready, blocked = [], []
    for t in data.get("tasks", []):
        deps_done = all(task_lookup(data, d, spec_slug=args.spec)["status"] == "done" for d in t.get("depends_on", []))
        entry = {"id": t["id"], "title": t["title"], "status": t["status"], "owner_role": t["owner_role"]}
        is_ready = (t["status"] in {"todo", "needs_changes"} and deps_done) or (t["status"] == "in_review" and (entry.update({"owner_role": "reviewer"}), True)[1])
        if is_ready:
            ready.append(entry)
        elif t["status"] != "done":
            blocked.append(entry)
    next_entry = ready[0] if ready else None
    blocking_reason = ""
    if next_entry and next_entry["owner_role"] in {"implementation-runner", "maintainer"} and not review_summary["valid"]:
        blocking_reason = "review_approval_required"
        next_entry = None
    print_json({"spec": args.spec, "review_status": review_summary, "worktree": normalize_worktree_metadata(args.spec).get("worktree", {}), "fix_request_present": bool(load_fix_request(args.spec)), "fix_request": load_fix_request_data(args.spec), "strategy_summary": strategy_summary(args.spec), "active_runs": active_runs, "stale_runs": stale_runs, "ready_tasks": ready, "blocked_or_active_tasks": blocked, "blocking_reason": blocking_reason, "recommended_next_action": None if active_runs else next_entry})


def show_status(_: argparse.Namespace) -> None:
    ensure_state()
    print_json({"specs": sorted(p.name for p in SPECS_DIR.iterdir() if p.is_dir()), "runs": sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())})


# =============================================================================
# Command Handler Wrappers
# =============================================================================

def show_events(args: argparse.Namespace) -> None:
    print_json(load_events(args.spec, args.limit))


def show_fix_request(args: argparse.Namespace) -> None:
    print_json(load_fix_request_data(args.spec))


def create_fix_request_cmd(args: argparse.Namespace) -> None:
    findings = parse_findings(args)
    print(str(write_fix_request(args.spec, args.task, args.summary, args.result, findings=findings)))


def show_strategy_cmd(args: argparse.Namespace) -> None:
    print_json(strategy_summary(args.spec))


def add_planner_note_cmd(args: argparse.Namespace) -> None:
    content = args.content or args.note or ""
    if not content:
        raise SystemExit("planner note content is required")
    print(str(add_planner_note(args.spec, args.title or "Planner note", content, category=args.category, scope=args.scope)))


def create_handoff(args: argparse.Namespace) -> None:
    print(str(write_handoff(args.spec, args.task, args.role, args.summary, args.next_role, args.result)))


# =============================================================================
# Parser and Main Entry Point
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    """Build and configure the Autoflow CLI argument parser."""
    parser = argparse.ArgumentParser(description="Autoflow control-plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # Core system command
    init_cmd = sub.add_parser("init", help="create .autoflow state directories")
    init_cmd.set_defaults(func=lambda _: ensure_state())

    # Register modular CLI subcommands
    spec.add_subparser(sub)
    task.add_subparser(sub)

    # Handoff and fix request commands
    handoff_cmd = sub.add_parser("create-handoff", help="write a handoff artifact")
    for arg, req in [("--spec", True), ("--task", True), ("--role", True), ("--summary", True), ("--next-role", True), ("--result", True)]:
        handoff_cmd.add_argument(arg, required=req)
    handoff_cmd.set_defaults(func=create_handoff)

    fix_request_cmd = sub.add_parser("create-fix-request", help="write a structured QA fix request artifact")
    for arg, req in [("--spec", True), ("--task", True), ("--summary", True), ("--result", True)]:
        fix_request_cmd.add_argument(arg, required=req)
    fix_request_cmd.add_argument("--findings-json", default="")
    fix_request_cmd.add_argument("--findings-file", default="")
    fix_request_cmd.set_defaults(func=create_fix_request_cmd)

    show_fix_cmd = sub.add_parser("show-fix-request", help="show the structured QA fix request data")
    show_fix_cmd.add_argument("--spec", required=True)
    show_fix_cmd.set_defaults(func=show_fix_request)

    worktree.add_subparser(sub)
    repository.add_subparser(sub)
    system.add_subparser(sub)
    agent.add_subparser(sub)
    memory.add_subparser(sub)
    review.add_subparser(sub)

    # Strategy and planner commands
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

    integration.add_subparser(sub)
    run.add_subparser(sub)

    # Event and workflow commands
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
    """Main entry point for the Autoflow CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
