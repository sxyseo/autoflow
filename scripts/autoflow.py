#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
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
MEMORY_DIR = STATE_DIR / "memory"
STRATEGY_MEMORY_DIR = MEMORY_DIR / "strategy"
DISCOVERY_FILE = STATE_DIR / "discovered_agents.json"
SYSTEM_CONFIG_FILE = STATE_DIR / "system.json"
SYSTEM_CONFIG_TEMPLATE = ROOT / "config" / "system.example.json"
AGENTS_FILE = STATE_DIR / "agents.json"
BMAD_DIR = ROOT / "templates" / "bmad"
REVIEW_STATE_FILE = "review_state.json"
EVENTS_FILE = "events.jsonl"
QA_FIX_REQUEST_FILE = "QA_FIX_REQUEST.md"
QA_FIX_REQUEST_JSON_FILE = "QA_FIX_REQUEST.json"
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
    for path in [STATE_DIR, SPECS_DIR, TASKS_DIR, RUNS_DIR, LOGS_DIR, WORKTREES_DIR, MEMORY_DIR, STRATEGY_MEMORY_DIR]:
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
    resume: dict[str, Any] | None = None
    protocol: str = "cli"
    model: str = ""
    model_profile: str = ""
    tools: list[str] | None = None
    tool_profile: str = ""
    memory_scopes: list[str] | None = None
    transport: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "resume": self.resume or {},
            "protocol": self.protocol,
            "model": self.model,
            "model_profile": self.model_profile,
            "tools": self.tools or [],
            "tool_profile": self.tool_profile,
            "memory_scopes": self.memory_scopes or [],
            "transport": self.transport or {},
        }


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def resolve_root_path(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def resolve_agent_profiles(spec: dict[str, Any], system_config: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(spec)
    model_profiles = system_config.get("models", {}).get("profiles", {})
    tool_profiles = system_config.get("tools", {}).get("profiles", {})
    if not resolved.get("model") and resolved.get("model_profile"):
        resolved["model"] = model_profiles.get(resolved["model_profile"], "")
    if not resolved.get("tools") and resolved.get("tool_profile"):
        resolved["tools"] = tool_profiles.get(resolved["tool_profile"], [])
    if not resolved.get("memory_scopes"):
        resolved["memory_scopes"] = list(
            system_config.get("memory", {}).get("default_scopes", ["spec"])
        )
    return resolved


def load_agents() -> dict[str, AgentSpec]:
    if not AGENTS_FILE.exists():
        raise SystemExit(
            f"missing {AGENTS_FILE}. copy config/agents.example.json to .autoflow/agents.json first"
        )
    data = read_json(AGENTS_FILE)
    system_config = load_system_config()
    agents = {}
    for name, spec in data.get("agents", {}).items():
        resolved = resolve_agent_profiles(spec, system_config)
        agents[name] = AgentSpec(
            name=name,
            command=resolved["command"],
            args=list(resolved.get("args", [])),
            resume=resolved.get("resume"),
            protocol=resolved.get("protocol", "cli"),
            model=resolved.get("model", ""),
            model_profile=resolved.get("model_profile", ""),
            tools=list(resolved.get("tools", [])) if resolved.get("tools") else None,
            tool_profile=resolved.get("tool_profile", ""),
            memory_scopes=list(resolved.get("memory_scopes", [])) if resolved.get("memory_scopes") else None,
            transport=resolved.get("transport"),
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
        "qa_fix_request_json": directory / QA_FIX_REQUEST_JSON_FILE,
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


def system_config_default() -> dict[str, Any]:
    if SYSTEM_CONFIG_TEMPLATE.exists():
        return read_json_or_default(SYSTEM_CONFIG_TEMPLATE, {})
    return {
        "memory": {
            "enabled": True,
            "auto_capture_run_results": True,
            "global_file": str(MEMORY_DIR / "global.md"),
            "spec_dir": str(MEMORY_DIR / "specs"),
        },
        "models": {
            "profiles": {
                "spec": "gpt-5",
                "implementation": "gpt-5-codex",
                "review": "claude-sonnet-4-6",
            }
        },
        "tools": {
            "profiles": {
                "codex-default": [],
                "claude-review": ["Read", "Bash(git:*)"],
            }
        },
        "registry": {
            "acp_agents": []
        },
    }


def load_system_config() -> dict[str, Any]:
    config = system_config_default()
    if SYSTEM_CONFIG_FILE.exists():
        local = read_json_or_default(SYSTEM_CONFIG_FILE, {})
        config = deep_merge(config, local)
    return deep_merge(
        {
            "memory": {"default_scopes": ["spec"]},
            "models": {"profiles": {}},
            "tools": {"profiles": {}},
            "registry": {"acp_agents": []},
        },
        config,
    )


def memory_file(scope: str, spec_slug: str | None = None) -> Path:
    memory_cfg = load_system_config().get("memory", {})
    if scope == "global":
        return resolve_root_path(memory_cfg.get("global_file", MEMORY_DIR / "global.md"))
    if spec_slug:
        spec_dir = resolve_root_path(memory_cfg.get("spec_dir", MEMORY_DIR / "specs"))
        return spec_dir / f"{spec_slug}.md"
    raise SystemExit("spec scope requires a spec slug")


def append_memory(scope: str, content: str, spec_slug: str | None = None, title: str = "") -> Path:
    path = memory_file(scope, spec_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    heading = title or f"Memory @ {now_stamp()}"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"## {heading}\n\n{content.strip()}\n\n")
    return path


def load_memory_context(spec_slug: str, scopes: list[str] | None = None) -> str:
    config = load_system_config()
    memory_cfg = config.get("memory", {})
    if not memory_cfg.get("enabled", True):
        return "Memory is disabled."
    allowed_scopes = scopes or list(memory_cfg.get("default_scopes", ["spec"]))
    parts = []
    global_path = memory_file("global")
    spec_path = memory_file("spec", spec_slug)
    if "global" in allowed_scopes and global_path.exists():
        parts.append("### Global memory\n")
        parts.append(global_path.read_text(encoding="utf-8").strip())
    if "spec" in allowed_scopes and spec_path.exists():
        parts.append("### Spec memory\n")
        parts.append(spec_path.read_text(encoding="utf-8").strip())
    return "\n\n".join(part for part in parts if part).strip() or "No stored memory yet."


def strategy_memory_file(scope: str, spec_slug: str | None = None) -> Path:
    if scope == "global":
        return STRATEGY_MEMORY_DIR / "global.json"
    if spec_slug:
        return STRATEGY_MEMORY_DIR / "specs" / f"{spec_slug}.json"
    raise SystemExit("spec scope requires a spec slug")


def strategy_memory_default() -> dict[str, Any]:
    return {
        "updated_at": "",
        "reflections": [],
        "planner_notes": [],
        "stats": {
            "by_role": {},
            "by_result": {},
            "finding_categories": {},
            "severity": {},
            "files": {},
        },
        "playbook": [],
    }


def load_strategy_memory(scope: str, spec_slug: str | None = None) -> dict[str, Any]:
    return read_json_or_default(strategy_memory_file(scope, spec_slug), strategy_memory_default())


def save_strategy_memory(scope: str, payload: dict[str, Any], spec_slug: str | None = None) -> Path:
    payload["updated_at"] = now_stamp()
    path = strategy_memory_file(scope, spec_slug)
    write_json(path, payload)
    return path


def increment_counter(counters: dict[str, int], key: str) -> None:
    if not key:
        return
    counters[key] = counters.get(key, 0) + 1


def derive_strategy_actions(
    role: str,
    result: str,
    findings: list[dict[str, Any]],
    stats: dict[str, Any],
) -> list[str]:
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


def load_fix_request_data(spec_slug: str) -> dict[str, Any]:
    return read_json_or_default(
        spec_files(spec_slug)["qa_fix_request_json"],
        {"task": "", "result": "", "summary": "", "finding_count": 0, "findings": []},
    )


def normalize_findings(summary: str, findings: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if findings:
        normalized = []
        for index, finding in enumerate(findings, start=1):
            start_line = finding.get("line", finding.get("start_line"))
            end_line = finding.get("end_line")
            normalized.append(
                {
                    "id": finding.get("id") or f"F{index}",
                    "title": finding.get("title") or "Follow-up required",
                    "body": finding.get("body") or summary,
                    "file": finding.get("file", ""),
                    "line": int(start_line) if start_line not in (None, "") else None,
                    "end_line": int(end_line) if end_line not in (None, "") else None,
                    "severity": finding.get("severity", "medium"),
                    "category": finding.get("category", "general"),
                    "suggested_fix": finding.get("suggested_fix", ""),
                    "source_run": finding.get("source_run", ""),
                }
            )
        return normalized
    return [
        {
            "id": "F1",
            "title": "Follow-up required",
            "body": summary,
            "file": "",
            "line": None,
            "end_line": None,
            "severity": "medium",
            "category": "general",
            "suggested_fix": "",
            "source_run": "",
        }
    ]


def format_fix_request_markdown(task_id: str, summary: str, result: str, findings: list[dict[str, Any]]) -> str:
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


def native_resume_preview(agent: AgentSpec) -> list[str]:
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


def sync_discovered_agents(overwrite: bool = False) -> dict[str, Any]:
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
    write_json(AGENTS_FILE, payload)
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

# Cache data structures
_run_metadata_cache: dict[str, list[dict[str, Any]]] = {}
_cache_loaded_specs: set[str] = set()


def _populate_run_cache_for_spec(spec_slug: str) -> None:
    """Load run metadata for a specific spec_slug into the cache.

    This implements lazy-loading: runs are only loaded from disk when needed.
    Subsequent calls for the same spec_slug will use the cached data (O(1) lookup).

    Opportunistic Caching:
        Since we must scan all run directories to find runs for the requested spec,
        we opportunistically cache runs for ALL specs encountered during the scan.
        This means the first call for any spec effectively caches runs for all specs,
        making subsequent calls for other specs essentially free (O(1) lookup).

    Cache Invalidation:
        If the spec is already in _cache_loaded_specs, we skip the filesystem scan
        entirely and return immediately. This ensures that after the first load,
        all subsequent calls are pure memory lookups.

    Args:
        spec_slug: The spec identifier to load runs for.
    """
    global _run_metadata_cache, _cache_loaded_specs

    # Skip if this spec has already been loaded (cache hit)
    if spec_slug in _cache_loaded_specs:
        return

    # Ensure the spec has an entry in the cache
    if spec_slug not in _run_metadata_cache:
        _run_metadata_cache[spec_slug] = []

    # Load runs from filesystem for this spec
    # Note: We must scan all directories to find runs matching this spec
    if not RUNS_DIR.exists():
        _cache_loaded_specs.add(spec_slug)
        return

    # First pass: discover all specs and collect their run IDs
    # This enables opportunistic caching of all specs in one scan
    spec_runs = {}
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            metadata = read_json(metadata_path)
            run_spec = metadata.get("spec", "")
            if run_spec:
                if run_spec not in spec_runs:
                    spec_runs[run_spec] = []
                spec_runs[run_spec].append(metadata)

    # Second pass: add all discovered runs to cache
    # This implements opportunistic caching for all specs encountered
    for discovered_spec, runs in spec_runs.items():
        if discovered_spec not in _run_metadata_cache:
            _run_metadata_cache[discovered_spec] = []
        _run_metadata_cache[discovered_spec].extend(runs)
        _cache_loaded_specs.add(discovered_spec)


def _populate_run_cache() -> None:
    """Populate the run metadata cache from the filesystem for all specs.

    This is the non-lazy version that loads all runs at once.
    Prefer using _populate_run_cache_for_spec() for lazy-loading.
    """
    global _run_metadata_cache, _cache_loaded_specs

    # Load all specs that haven't been loaded yet
    if not RUNS_DIR.exists():
        return

    # First, discover all spec_slugs
    all_specs = set()
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run.json"
        if metadata_path.exists():
            metadata = read_json(metadata_path)
            spec_slug = metadata.get("spec", "")
            if spec_slug:
                all_specs.add(spec_slug)

    # Load each spec that hasn't been loaded yet
    for spec_slug in all_specs:
        _populate_run_cache_for_spec(spec_slug)


def invalidate_run_cache() -> None:
    """Invalidate the run metadata cache.

    Call this function whenever runs are created, modified, or deleted to ensure
    the cache remains consistent with the filesystem state. This is a simple but
    correct approach: we clear all cached data, and it will be reloaded on demand.

    Cache Invalidation Strategy:
        - Simple: clear all cached data (not selective invalidation)
        - Safe: ensures cache consistency after any run modification
        - Lazy: data is reloaded on next access (not immediately)
        - Called by: create_run_record() after creating new run directories

    Note: While invalidating the entire cache may seem aggressive, it's the
    correct approach because:
        1. Run creation is relatively rare (not a hot path)
        2. Cache rebuild is lazy (amortized cost)
        3. Simplicity avoids complex invalidation bugs
        4. Performance impact is minimal (cache rebuilds are fast)
    """
    global _run_metadata_cache, _cache_loaded_specs
    _run_metadata_cache.clear()
    _cache_loaded_specs.clear()


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
        if item.get("status") != "completed"
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


def parse_findings(args: argparse.Namespace) -> list[dict[str, Any]] | None:
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


def build_prompt(
    spec_slug: str,
    role: str,
    task_id: str | None,
    agent: AgentSpec,
    resume_from: str | None = None,
) -> str:
    files = spec_files(spec_slug)
    if not files["spec"].exists():
        raise SystemExit(f"unknown spec: {spec_slug}")
    tasks = load_tasks(spec_slug)
    selected_task = task_lookup(tasks, task_id) if task_id else next_task_data(spec_slug, role)
    review_summary = review_status_summary(spec_slug)
    fix_request = load_fix_request(spec_slug)
    fix_request_data = load_fix_request_data(spec_slug)
    memory_context = load_memory_context(spec_slug, agent.memory_scopes)
    strategy_context = render_strategy_context(spec_slug)
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
                },
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
    prompt_path.write_text(
        build_prompt(spec_slug, role, task_id, agent, resume_from=resume_from),
        encoding="utf-8",
    )
    branch = branch or f"codex/{slugify(spec_slug)}-{slugify(task_id)}"
    target_workdir = worktree_path(spec_slug) if worktree_path(spec_slug).exists() else ROOT
    command = [agent.command, *agent.args, str(prompt_path)]
    run_json_path = run_dir / "run.json"
    run_script = run_dir / "run.sh"
    run_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"cd {shlex.quote(str(target_workdir))}",
                f"exec {shlex.quote(str(ROOT / 'scripts' / 'run-agent.sh'))} {shlex.quote(agent_name)} {shlex.quote(str(prompt_path))} {shlex.quote(str(run_json_path))}",
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
        "native_resume_supported": bool(agent.resume),
        "native_resume_command_preview": native_resume_preview(agent),
        "agent_config": agent.to_dict(),
        "retry_policy": {
            "max_automatic_attempts": 3,
            "requires_fix_request_after_review_failure": True,
        },
    }
    write_json(run_json_path, metadata)
    record_event(spec_slug, "run.created", {"run": run_id, "task": task_id, "role": role})
    invalidate_run_cache()
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
    findings = parse_findings(args)
    metadata["status"] = "completed"
    metadata["result"] = args.result
    metadata["completed_at"] = now_stamp()
    metadata["findings_count"] = len(findings or [])
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
        fix_request_path = str(write_fix_request(metadata["spec"], metadata["task"], summary, args.result, findings=findings))
    if metadata["role"] == "implementation-runner" and args.result == "success":
        clear_fix_request(metadata["spec"])
    strategy_paths = record_reflection(metadata["spec"], metadata, args.result, summary, findings=findings)
    memory_cfg = load_system_config().get("memory", {})
    if memory_cfg.get("enabled", True) and memory_cfg.get("auto_capture_run_results", True):
        for scope in metadata.get("agent_config", {}).get("memory_scopes") or ["spec"]:
            append_memory(
                scope,
                f"role={metadata['role']}\nresult={args.result}\nsummary={summary}",
                spec_slug=metadata["spec"],
                title=f"{metadata['task']} {metadata['role']} {args.result}",
            )
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
                "strategy_memory": [str(path) for path in strategy_paths],
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def show_task_history(args: argparse.Namespace) -> None:
    print(json.dumps(task_run_history(args.spec, args.task), indent=2, ensure_ascii=True))


def show_events(args: argparse.Namespace) -> None:
    print(json.dumps(load_events(args.spec, args.limit), indent=2, ensure_ascii=True))


def show_fix_request(args: argparse.Namespace) -> None:
    print(json.dumps(load_fix_request_data(args.spec), indent=2, ensure_ascii=True))


def create_fix_request_cmd(args: argparse.Namespace) -> None:
    findings = parse_findings(args)
    path = write_fix_request(args.spec, args.task, args.summary, args.result, findings=findings)
    print(str(path))


def show_system_config(_: argparse.Namespace) -> None:
    print(json.dumps(load_system_config(), indent=2, ensure_ascii=True))


def init_system_config(_: argparse.Namespace) -> None:
    ensure_state()
    if not SYSTEM_CONFIG_FILE.exists():
        write_json(SYSTEM_CONFIG_FILE, system_config_default())
    print(str(SYSTEM_CONFIG_FILE))


def discover_agents_cmd(_: argparse.Namespace) -> None:
    print(json.dumps(discover_agents_registry(), indent=2, ensure_ascii=True))


def sync_agents_cmd(args: argparse.Namespace) -> None:
    print(json.dumps(sync_discovered_agents(overwrite=args.overwrite), indent=2, ensure_ascii=True))


def write_memory_cmd(args: argparse.Namespace) -> None:
    path = append_memory(args.scope, args.content, spec_slug=args.spec, title=args.title)
    print(str(path))


def show_memory_cmd(args: argparse.Namespace) -> None:
    path = memory_file(args.scope, args.spec)
    if not path.exists():
        print("")
        return
    print(path.read_text(encoding="utf-8"))


def show_strategy_cmd(args: argparse.Namespace) -> None:
    print(json.dumps(strategy_summary(args.spec), indent=2, ensure_ascii=True))


def add_planner_note_cmd(args: argparse.Namespace) -> None:
    path = add_planner_note(args.spec, args.title, args.content, category=args.category, scope=args.scope)
    print(str(path))


def taskmaster_payload(spec_slug: str) -> dict[str, Any]:
    tasks = load_tasks(spec_slug)
    return {
        "project": spec_slug,
        "exported_at": now_stamp(),
        "tasks": [
            {
                "id": task["id"],
                "title": task["title"],
                "status": task["status"],
                "dependencies": task.get("depends_on", []),
                "owner_role": task["owner_role"],
                "acceptanceCriteria": task.get("acceptance_criteria", []),
                "notes": task.get("notes", []),
            }
            for task in tasks.get("tasks", [])
        ],
    }


def export_taskmaster_cmd(args: argparse.Namespace) -> None:
    payload = taskmaster_payload(args.spec)
    if args.output:
        output = Path(args.output)
        write_json(output, payload)
        print(str(output))
        return
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def normalize_imported_task(entry: dict[str, Any], index: int) -> dict[str, Any]:
    depends = entry.get("depends_on", entry.get("dependencies", [])) or []
    criteria = entry.get("acceptance_criteria", entry.get("acceptanceCriteria", [])) or []
    status = entry.get("status", "todo")
    if status not in VALID_TASK_STATUSES:
        status = "todo"
    return {
        "id": entry.get("id") or f"T{index}",
        "title": entry.get("title", entry.get("name", f"Task {index}")),
        "status": status,
        "depends_on": depends,
        "owner_role": entry.get("owner_role", entry.get("role", "implementation-runner")),
        "acceptance_criteria": criteria,
        "notes": entry.get("notes", []),
    }


def import_taskmaster_cmd(args: argparse.Namespace) -> None:
    payload = read_json(Path(args.input))
    tasks_input = payload if isinstance(payload, list) else payload.get("tasks", [])
    normalized = [
        normalize_imported_task(item, index)
        for index, item in enumerate(tasks_input, start=1)
    ]
    data = {
        "spec_slug": args.spec,
        "updated_at": now_stamp(),
        "tasks": normalized,
    }
    write_json(task_file(args.spec), data)
    sync_review_state(args.spec, reason="taskmaster_import")
    record_event(args.spec, "taskmaster.imported", {"task_count": len(normalized), "source": args.input})
    print(json.dumps({"spec": args.spec, "task_count": len(normalized)}, indent=2, ensure_ascii=True))


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
        "fix_request": load_fix_request_data(args.spec),
        "strategy_summary": strategy_summary(args.spec),
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

    init_system_cmd = sub.add_parser("init-system-config", help="write the local system config scaffold")
    init_system_cmd.set_defaults(func=init_system_config)

    system_cmd = sub.add_parser("show-system-config", help="show system memory/model/tool config")
    system_cmd.set_defaults(func=show_system_config)

    discover_cmd = sub.add_parser("discover-agents", help="probe local agents and merge ACP registry entries")
    discover_cmd.set_defaults(func=discover_agents_cmd)

    sync_cmd = sub.add_parser("sync-agents", help="merge discovered CLI/ACP agents into .autoflow/agents.json")
    sync_cmd.add_argument("--overwrite", action="store_true")
    sync_cmd.set_defaults(func=sync_agents_cmd)

    write_memory = sub.add_parser("write-memory", help="append to global or spec memory")
    write_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    write_memory.add_argument("--spec")
    write_memory.add_argument("--title", default="")
    write_memory.add_argument("--content", required=True)
    write_memory.set_defaults(func=write_memory_cmd)

    show_memory = sub.add_parser("show-memory", help="show stored memory context")
    show_memory.add_argument("--scope", choices=["global", "spec"], required=True)
    show_memory.add_argument("--spec")
    show_memory.set_defaults(func=show_memory_cmd)

    strategy_cmd = sub.add_parser("show-strategy", help="show accumulated planner/reflection strategy memory")
    strategy_cmd.add_argument("--spec", required=True)
    strategy_cmd.set_defaults(func=show_strategy_cmd)

    planner_cmd = sub.add_parser("add-planner-note", help="append a planner strategy note to strategy memory")
    planner_cmd.add_argument("--spec", required=True)
    planner_cmd.add_argument("--title", required=True)
    planner_cmd.add_argument("--content", required=True)
    planner_cmd.add_argument("--category", default="strategy")
    planner_cmd.add_argument("--scope", choices=["global", "spec"], default="spec")
    planner_cmd.set_defaults(func=add_planner_note_cmd)

    export_taskmaster = sub.add_parser("export-taskmaster", help="export Autoflow tasks in a Taskmaster-friendly JSON shape")
    export_taskmaster.add_argument("--spec", required=True)
    export_taskmaster.add_argument("--output", default="")
    export_taskmaster.set_defaults(func=export_taskmaster_cmd)

    import_taskmaster = sub.add_parser("import-taskmaster", help="import task data from a Taskmaster-style JSON file")
    import_taskmaster.add_argument("--spec", required=True)
    import_taskmaster.add_argument("--input", required=True)
    import_taskmaster.set_defaults(func=import_taskmaster_cmd)

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
    complete_cmd.add_argument("--findings-json", default="")
    complete_cmd.add_argument("--findings-file", default="")
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
