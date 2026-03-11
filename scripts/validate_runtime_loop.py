#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"


def run(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, env=env)
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


def merge_dummy_agent(agent_name: str) -> None:
    agents_path = STATE_DIR / "agents.json"
    data = {"agents": {}}
    if agents_path.exists():
        data = json.loads(agents_path.read_text(encoding="utf-8"))
    data.setdefault("agents", {})[agent_name] = {
        "name": "Dummy ACP agent",
        "protocol": "acp",
        "command": "acp-agent",
        "transport": {
            "type": "stdio",
            "command": "acp-agent",
            "args": [],
            "prompt_mode": "argv",
        },
        "memory_scopes": ["spec"],
        "roles": [
            "spec-writer",
            "task-graph-manager",
            "implementation-runner",
            "reviewer",
            "maintainer",
        ],
        "max_concurrent": 2,
    }
    write_json(agents_path, data)


def create_dummy_agent(binary_dir: Path) -> Path:
    binary_dir.mkdir(parents=True, exist_ok=True)
    log_path = binary_dir / "dummy-acp.log"
    script_path = binary_dir / "acp-agent"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from pathlib import Path",
                "import json",
                "import sys",
                "import time",
                f"log_path = Path({str(log_path)!r})",
                "log_path.parent.mkdir(parents=True, exist_ok=True)",
                "with log_path.open('a', encoding='utf-8') as handle:",
                "    handle.write(json.dumps({'argv': sys.argv[1:]}) + '\\n')",
                "time.sleep(2)",
                "print('dummy acp agent complete')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.chmod(script_path, 0o755)
    return script_path


def cleanup_spec(slug: str, session_names: list[str]) -> None:
    for session_name in session_names:
        run(["tmux", "kill-session", "-t", session_name], check=False)
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


def create_disposable_spec(slug: str) -> None:
    run(
        [
            "python3",
            "scripts/autoflow.py",
            "new-spec",
            "--slug",
            slug,
            "--title",
            "Runtime Loop Validation",
            "--summary",
            "Validate scheduler and dispatch runtime behavior.",
        ]
    )
    run(["python3", "scripts/autoflow.py", "init-tasks", "--spec", slug])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate runtime dispatch and scheduler loop with a disposable ACP agent")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    dispatch_slug = f"runtime-dispatch-{stamp}"
    scheduler_slug = f"runtime-scheduler-{stamp}"
    runtime_dir = STATE_DIR / "runtime-validation" / stamp
    dummy_bin_dir = runtime_dir / "bin"
    continuous_config = runtime_dir / "continuous-config.json"
    scheduler_config = runtime_dir / "scheduler-config.json"
    agent_name = "dummy-acp"
    sessions: list[str] = []
    results: dict[str, Any] = {
        "dispatch_slug": dispatch_slug,
        "scheduler_slug": scheduler_slug,
        "agent": agent_name,
    }

    create_dummy_agent(dummy_bin_dir)
    env = os.environ.copy()
    env["PATH"] = f"{dummy_bin_dir}:{env.get('PATH', '')}"

    try:
        run(["python3", "scripts/autoflow.py", "init"], env=env)
        run(["python3", "scripts/autoflow.py", "init-system-config"], env=env)
        run(["python3", "scripts/autoflow.py", "sync-agents"], env=env)
        merge_dummy_agent(agent_name)
        create_disposable_spec(dispatch_slug)
        create_disposable_spec(scheduler_slug)

        write_json(
            continuous_config,
            {
                "role_agents": {
                    "spec-writer": agent_name,
                    "task-graph-manager": agent_name,
                    "implementation-runner": agent_name,
                    "reviewer": agent_name,
                    "maintainer": agent_name,
                },
                "agent_selection": {
                    "sync_before_dispatch": False,
                },
                "dispatch": {
                    "max_concurrent_runs": 2,
                    "dispatch_interval_seconds": 120,
                },
                "verify_commands": [],
                "commit": {
                    "message_prefix": "autoflow",
                    "push": False,
                    "allow_during_active_runs": False,
                },
                "retry_policy": {
                    "max_automatic_attempts": 3,
                    "require_fix_request_for_retry": True,
                },
            },
        )
        write_json(
            scheduler_config,
            {
                "scheduler": {
                    "timezone": "UTC",
                    "max_instances": 1,
                    "coalesce": True,
                    "misfire_grace_time": 300,
                },
                "jobs": {
                    "continuous_iteration": {
                        "enabled": True,
                        "cron": "*/5 * * * *",
                        "max_instances": 1,
                        "description": "Disposable continuous iteration validation",
                        "args": {
                            "spec": scheduler_slug,
                            "config": str(continuous_config),
                            "dispatch": True,
                            "commit_if_dirty": False,
                            "push": False,
                        },
                    }
                },
                "job_defaults": {
                    "max_instances": 1,
                    "coalesce": True,
                    "misfire_grace_time": 300,
                },
            },
        )

        dispatch_result = json.loads(
            run(
                [
                    "python3",
                    "scripts/continuous_iteration.py",
                    "--spec",
                    dispatch_slug,
                    "--config",
                    str(continuous_config),
                    "--dispatch",
                ],
                env=env,
            ).stdout
        )
        sessions.append(dispatch_result["dispatch"]["payload"]["tmux_session"])
        run(["tmux", "has-session", "-t", sessions[-1]], env=env)
        dispatch_state = json.loads(
            run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", dispatch_slug], env=env).stdout
        )
        if not dispatch_state["active_runs"]:
            raise SystemExit("direct dispatch did not leave an active run record")
        results["direct_dispatch"] = dispatch_result
        results["direct_dispatch_state"] = {
            "active_runs": len(dispatch_state["active_runs"]),
            "ready_tasks": dispatch_state["ready_tasks"],
        }

        scheduler_run = run(
            [
                "python3",
                "scripts/scheduler.py",
                "run-once",
                "--job-type",
                "continuous_iteration",
                "--config",
                str(scheduler_config),
                "--verbose",
            ],
            env=env,
        )
        scheduler_state = json.loads(
            run(["python3", "scripts/autoflow.py", "workflow-state", "--spec", scheduler_slug], env=env).stdout
        )
        if not scheduler_state["active_runs"]:
            raise SystemExit("scheduler run-once did not dispatch an active run")
        active_sessions = run(["tmux", "ls"], env=env, check=False).stdout.splitlines()
        for line in active_sessions:
            name = line.split(":", 1)[0]
            if name.startswith("autoflow-") and name not in sessions:
                sessions.append(name)
        results["scheduler_run_once"] = {
            "stdout": scheduler_run.stdout,
            "stderr": scheduler_run.stderr,
            "active_runs": len(scheduler_state["active_runs"]),
        }
        results["validated"] = True
        print(json.dumps(results, indent=2, ensure_ascii=True))
    finally:
        if not args.keep_artifacts:
            cleanup_spec(dispatch_slug, sessions)
            cleanup_spec(scheduler_slug, sessions)
            shutil.rmtree(runtime_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
