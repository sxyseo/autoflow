#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise SystemExit(
            json.dumps(
                {
                    "command": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
                indent=2,
                ensure_ascii=True,
            )
        )
    return proc


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def merge_dummy_agent() -> None:
    agents_path = STATE_DIR / "agents.json"
    data = {"agents": {}}
    if agents_path.exists():
        data = json.loads(agents_path.read_text(encoding="utf-8"))
    data.setdefault("agents", {})["dummy"] = {
        "name": "Dummy CLI agent",
        "protocol": "cli",
        "command": "echo",
        "args": ["agent"],
        "memory_scopes": ["spec"],
        "roles": [
            "spec-writer",
            "task-graph-manager",
            "implementation-runner",
            "reviewer",
            "maintainer",
        ],
    }
    write_json(agents_path, data)


def cleanup_spec(slug: str) -> None:
    run(["python3", "scripts/autoflow.py", "cleanup-runs", "--spec", slug], check=False)
    run(
        ["python3", "scripts/autoflow.py", "remove-worktree", "--spec", slug, "--delete-branch"],
        check=False,
    )
    shutil.rmtree(STATE_DIR / "specs" / slug, ignore_errors=True)
    task_path = STATE_DIR / "tasks" / f"{slug}.json"
    if task_path.exists():
        task_path.unlink()
    spec_memory = STATE_DIR / "memory" / "specs" / f"{slug}.md"
    if spec_memory.exists():
        spec_memory.unlink()
    strategy_memory = STATE_DIR / "memory" / "strategy" / "specs" / f"{slug}.json"
    if strategy_memory.exists():
        strategy_memory.unlink()


def new_spec(slug: str, title: str) -> None:
    run(
        [
            "python3",
            "scripts/autoflow.py",
            "new-spec",
            "--slug",
            slug,
            "--title",
            title,
            "--summary",
            f"Validation scenario for {title}.",
        ]
    )
    run(["python3", "scripts/autoflow.py", "init-tasks", "--spec", slug])


def read_json_cmd(cmd: list[str]) -> dict[str, Any]:
    return json.loads(run(cmd).stdout)


def create_run(spec: str, role: str, task: str) -> str:
    proc = run(
        [
            "python3",
            "scripts/autoflow.py",
            "new-run",
            "--spec",
            spec,
            "--role",
            role,
            "--agent",
            "dummy",
            "--task",
            task,
        ]
    )
    return Path(proc.stdout.strip()).name


def complete_run(run_id: str, result: str, summary: str, findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cmd = [
        "python3",
        "scripts/autoflow.py",
        "complete-run",
        "--run",
        run_id,
        "--result",
        result,
        "--summary",
        summary,
    ]
    if findings:
        cmd.extend(["--findings-json", json.dumps(findings)])
    return read_json_cmd(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate stale-run recovery and bounded QA self-healing loop")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    recovery_slug = f"recovery-smoke-{stamp}"
    qa_slug = f"qa-smoke-{stamp}"
    results: dict[str, Any] = {
        "recovery_slug": recovery_slug,
        "qa_slug": qa_slug,
    }

    try:
        run(["python3", "scripts/autoflow.py", "init"])
        run(["python3", "scripts/autoflow.py", "init-system-config"])
        merge_dummy_agent()

        new_spec(recovery_slug, "Recovery Loop Validation")
        stale_run = create_run(recovery_slug, "spec-writer", "T1")
        run_json = STATE_DIR / "runs" / stale_run / "run.json"
        payload = json.loads(run_json.read_text(encoding="utf-8"))
        payload["status"] = "running"
        payload["heartbeat_at"] = "20200101T000000Z"
        payload["tmux_session"] = ""
        run_json.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        recovery = read_json_cmd(
            [
                "python3",
                "scripts/autoflow.py",
                "recover-run",
                "--run",
                stale_run,
                "--reason",
                "validation_stale_recovery",
            ]
        )
        recovery_state = read_json_cmd(
            ["python3", "scripts/autoflow.py", "workflow-state", "--spec", recovery_slug]
        )
        results["recovery"] = {
            "original_run": stale_run,
            "new_run": recovery["new_run"],
            "active_runs": len(recovery_state["active_runs"]),
            "recommended_next_action": recovery_state["recommended_next_action"],
        }

        new_spec(qa_slug, "QA Loop Validation")
        task_file = STATE_DIR / "tasks" / f"{qa_slug}.json"
        task_payload = json.loads(task_file.read_text(encoding="utf-8"))
        for task in task_payload["tasks"]:
            if task["id"] in {"T1", "T2"}:
                task["status"] = "done"
        task_file.write_text(json.dumps(task_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        run(["python3", "scripts/autoflow.py", "approve-spec", "--spec", qa_slug, "--approved-by", "validator"])

        impl_run = create_run(qa_slug, "implementation-runner", "T3")
        complete_run(impl_run, "success", "Initial implementation slice completed.")
        reviewer_run = create_run(qa_slug, "reviewer", "T3")
        complete_run(
            reviewer_run,
            "needs_changes",
            "Reviewer requested tighter validation before approval.",
            findings=[
                {
                    "file": "scripts/continuous_iteration.py",
                    "line": 1,
                    "severity": "medium",
                    "category": "workflow",
                    "title": "Retry path needs tighter validation",
                    "body": "Add follow-up validation before approving the task.",
                }
            ],
        )
        fix_state = read_json_cmd(
            ["python3", "scripts/autoflow.py", "workflow-state", "--spec", qa_slug]
        )
        retry_run = create_run(qa_slug, "implementation-runner", "T3")
        complete_run(retry_run, "success", "Applied reviewer follow-up fixes.")
        final_review_run = create_run(qa_slug, "reviewer", "T3")
        complete_run(final_review_run, "success", "Review passed after retry.")
        final_state = read_json_cmd(
            ["python3", "scripts/autoflow.py", "workflow-state", "--spec", qa_slug]
        )
        results["qa_loop"] = {
            "fix_request_present_after_review": fix_state["fix_request_present"],
            "retry_next_action": fix_state["recommended_next_action"],
            "final_ready_tasks": final_state["ready_tasks"],
            "final_recommended_next_action": final_state["recommended_next_action"],
        }

        results["validated"] = True
        print(json.dumps(results, indent=2, ensure_ascii=True))
    finally:
        if not args.keep_artifacts:
            cleanup_spec(recovery_slug)
            cleanup_spec(qa_slug)


if __name__ == "__main__":
    main()
