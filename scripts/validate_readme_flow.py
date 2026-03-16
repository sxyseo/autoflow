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


def cleanup_spec(slug: str, run_ids: list[str], worktree_created: bool) -> None:
    if worktree_created:
        run(
            ["python3", "scripts/autoflow.py", "remove-worktree", "--spec", slug, "--delete-branch"],
            check=False,
        )
    for run_id in run_ids:
        shutil.rmtree(STATE_DIR / "runs" / run_id, ignore_errors=True)
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the README.zh-CN Autoflow flow with a disposable spec")
    parser.add_argument("--agent", default="codex", help="agent to use for generated runs")
    parser.add_argument("--keep-artifacts", action="store_true", help="keep the disposable spec and runs for inspection")
    args = parser.parse_args()

    slug = "readme-smoke-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    run_ids: list[str] = []
    worktree_created = False
    results: dict[str, Any] = {"slug": slug, "agent": args.agent}

    try:
        run(["python3", "scripts/autoflow.py", "init"])
        run(["python3", "scripts/autoflow.py", "init-system-config"])
        results["sync_agents"] = json.loads(run(["python3", "scripts/autoflow.py", "sync-agents"]).stdout)
        run(
            [
                "python3",
                "scripts/autoflow.py",
                "new-spec",
                "--slug",
                slug,
                "--title",
                "README Smoke Validation",
                "--summary",
                "Validate the README.zh-CN command flow.",
            ]
        )
        results["show_spec_initial"] = json.loads(
            run(["python3", "scripts/autoflow.py", "show-spec", "--slug", slug]).stdout
        )
        results["init_tasks"] = json.loads(
            run(["python3", "scripts/autoflow.py", "init-tasks", "--spec", slug]).stdout
        )
        results["update_spec"] = json.loads(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "update-spec",
                    "--slug",
                    slug,
                    "--append",
                    "README smoke validation note.",
                ]
            ).stdout
        )
        results["update_task"] = json.loads(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "update-task",
                    "--spec",
                    slug,
                    "--task",
                    "T1",
                    "--status",
                    "blocked",
                    "--note",
                    "simulate a stuck task before reset",
                ]
            ).stdout
        )
        results["reset_task"] = json.loads(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "reset-task",
                    "--spec",
                    slug,
                    "--task",
                    "T1",
                    "--note",
                    "reset after smoke validation",
                ]
            ).stdout
        )
        results["planner_note"] = run(
            [
                "python3",
                "scripts/autoflow.py",
                "add-planner-note",
                "--spec",
                slug,
                "--note",
                "README smoke note",
            ]
        ).stdout.strip()
        results["validate_config"] = json.loads(
            run(["python3", "scripts/autoflow.py", "validate-config"]).stdout
        )
        results["test_agent"] = json.loads(
            run(["python3", "scripts/autoflow.py", "test-agent", "--agent", args.agent]).stdout
        )
        if not results["validate_config"]["valid"]:
            raise SystemExit(json.dumps(results, indent=2, ensure_ascii=True))
        if not results["test_agent"]["ready"]:
            raise SystemExit(json.dumps(results, indent=2, ensure_ascii=True))

        results["create_worktree"] = json.loads(
            run(["python3", "scripts/autoflow.py", "create-worktree", "--spec", slug]).stdout
        )
        worktree_created = True
        results["force_worktree"] = json.loads(
            run(["python3", "scripts/autoflow.py", "create-worktree", "--spec", slug, "--force"]).stdout
        )

        spec_run_dir = Path(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "new-run",
                    "--spec",
                    slug,
                    "--role",
                    "spec-writer",
                    "--agent",
                    args.agent,
                    "--task",
                    "T1",
                ]
            ).stdout.strip()
        )
        run_ids.append(spec_run_dir.name)
        results["complete_run"] = json.loads(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "complete-run",
                    "--run",
                    spec_run_dir.name,
                    "--result",
                    "success",
                    "--summary",
                    "README smoke success.",
                ]
            ).stdout
        )
        results["capture_memory"] = json.loads(
            run(["python3", "scripts/autoflow.py", "capture-memory", "--run", spec_run_dir.name]).stdout
        )

        reviewer_run_dir = Path(
            run(
                [
                    "python3",
                    "scripts/autoflow.py",
                    "new-run",
                    "--spec",
                    slug,
                    "--role",
                    "reviewer",
                    "--agent",
                    args.agent,
                    "--task",
                    "T1",
                ]
            ).stdout.strip()
        )
        run_ids.append(reviewer_run_dir.name)
        results["cleanup_runs"] = json.loads(
            run(["python3", "scripts/autoflow.py", "cleanup-runs", "--spec", slug]).stdout
        )
        results["workflow_state"] = json.loads(
            run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", slug]).stdout
        )
        if results["workflow_state"]["active_runs"]:
            raise SystemExit(json.dumps(results, indent=2, ensure_ascii=True))
        if not any(
            item["id"] == "T1" and item["owner_role"] == "reviewer"
            for item in results["workflow_state"]["ready_tasks"]
        ):
            raise SystemExit(json.dumps(results, indent=2, ensure_ascii=True))

        results["validated"] = True
        print(json.dumps(results, indent=2, ensure_ascii=True))
    finally:
        if not args.keep_artifacts:
            cleanup_spec(slug, run_ids, worktree_created)


if __name__ == "__main__":
    main()
