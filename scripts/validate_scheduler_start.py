#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
START_MARKER = "Scheduler started. Press Ctrl+C to stop."
STOP_MARKER = "Stopping scheduler..."
STOPPED_MARKER = "Scheduler stopped."


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def make_config(
    path: Path,
    *,
    enabled_jobs: dict[str, dict[str, Any]],
) -> None:
    write_json(
        path,
        {
            "scheduler": {
                "timezone": "UTC",
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 300,
            },
            "jobs": enabled_jobs,
            "job_defaults": {
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 300,
            },
        },
    )


def terminate_process(proc: subprocess.Popen[str], *, timeout: float) -> tuple[int, str]:
    proc.send_signal(signal.SIGTERM)
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = proc.wait(timeout=timeout)
    remaining = proc.stdout.read() if proc.stdout else ""
    return returncode, remaining


def run_start_cycle(
    label: str,
    config_path: Path,
    *,
    startup_timeout: float,
    shutdown_timeout: float,
    settle_seconds: float,
) -> dict[str, Any]:
    proc = subprocess.Popen(
        [sys.executable, "scripts/scheduler.py", "start", "--config", str(config_path)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines: list[str] = []
    deadline = time.time() + startup_timeout
    started = False

    while time.time() < deadline:
        if proc.poll() is not None:
            break
        line = proc.stdout.readline() if proc.stdout else ""
        if line:
            lines.append(line.rstrip())
            if START_MARKER in line:
                started = True
                break
        else:
            time.sleep(0.05)

    if not started:
        returncode, remaining = terminate_process(proc, timeout=shutdown_timeout)
        log_output = "\n".join(lines + [chunk for chunk in remaining.splitlines() if chunk])
        raise SystemExit(
            json.dumps(
                {
                    "error": "scheduler_start_timeout",
                    "label": label,
                    "returncode": returncode,
                    "log_output": log_output,
                },
                indent=2,
                ensure_ascii=True,
            )
        )

    time.sleep(settle_seconds)
    returncode, remaining = terminate_process(proc, timeout=shutdown_timeout)
    combined_lines = lines + [chunk for chunk in remaining.splitlines() if chunk]
    combined_output = "\n".join(combined_lines)
    result = {
        "label": label,
        "returncode": returncode,
        "started": started,
        "saw_stop_marker": STOP_MARKER in combined_output,
        "saw_stopped_marker": STOPPED_MARKER in combined_output,
        "log_excerpt": combined_lines[-12:],
    }

    if returncode != 0:
        raise SystemExit(json.dumps({"error": "scheduler_nonzero_exit", **result}, indent=2, ensure_ascii=True))
    if STOP_MARKER not in combined_output or STOPPED_MARKER not in combined_output:
        raise SystemExit(
            json.dumps(
                {"error": "scheduler_missing_shutdown_markers", **result},
                indent=2,
                ensure_ascii=True,
            )
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate long-running scheduler start mode by launching it and stopping it cleanly."
    )
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    parser.add_argument("--shutdown-timeout", type=float, default=5.0)
    parser.add_argument("--settle-seconds", type=float, default=1.0)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="autoflow-scheduler-start-") as tmp:
        tmpdir = Path(tmp)
        idle_config = tmpdir / "idle.json"
        enabled_config = tmpdir / "enabled.json"

        make_config(
            idle_config,
            enabled_jobs={
                "continuous_iteration": {
                    "enabled": False,
                    "cron": "*/5 * * * *",
                    "description": "Disabled idle validation job",
                }
            },
        )
        make_config(
            enabled_config,
            enabled_jobs={
                "weekly_consolidation": {
                    "enabled": True,
                    "cron": "0 3 * * 0",
                    "max_instances": 1,
                    "description": "Weekly validation job",
                },
                "monthly_dependency_update": {
                    "enabled": True,
                    "cron": "0 4 1 * *",
                    "max_instances": 1,
                    "description": "Monthly validation job",
                },
            },
        )

        results = {
            "validated": True,
            "profiles": [
                run_start_cycle(
                    "idle-start-stop",
                    idle_config,
                    startup_timeout=args.startup_timeout,
                    shutdown_timeout=args.shutdown_timeout,
                    settle_seconds=args.settle_seconds,
                ),
                run_start_cycle(
                    "enabled-jobs-start-stop",
                    enabled_config,
                    startup_timeout=args.startup_timeout,
                    shutdown_timeout=args.shutdown_timeout,
                    settle_seconds=args.settle_seconds,
                ),
                run_start_cycle(
                    "enabled-jobs-restart-stop",
                    enabled_config,
                    startup_timeout=args.startup_timeout,
                    shutdown_timeout=args.shutdown_timeout,
                    settle_seconds=args.settle_seconds,
                ),
            ],
        }

    print(json.dumps(results, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
