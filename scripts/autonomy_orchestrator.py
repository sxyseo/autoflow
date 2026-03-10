#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import continuous_iteration

# Ensure we import from the autoflow package, not scripts/autoflow.py
# Project root must be in path BEFORE scripts directory
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    # Insert at position 0 to ensure it's found before scripts/autoflow.py
    sys.path.insert(0, str(_root))
    # If scripts is already in path, remove and re-add after root
    scripts_path = str(_root / 'scripts')
    if scripts_path in sys.path:
        sys.path.remove(scripts_path)
    sys.path.insert(1, scripts_path)

# Import shared utilities from autoflow.utils
from autoflow.utils import load_config, load_json, run_cmd


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"
DISCOVERED_AGENTS_FILE = STATE_DIR / "discovered_agents.json"

# Old duplicate functions - replaced by autoflow.utils imports
# def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
#     return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=True, text=True)
#
# def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
#     if not path.exists():
#         return default or {}
#     return json.loads(path.read_text(encoding="utf-8"))
#
# def load_config(path: str) -> dict[str, Any]:
#     return json.loads((ROOT / path).read_text(encoding="utf-8"))


def autoflow_json(*args: str) -> dict[str, Any]:
    result = run_cmd(["python3", "scripts/autoflow.py", *args], cwd=ROOT)
    return json.loads(result.stdout)


def health_report(required: list[str] | None = None) -> dict[str, Any]:
    cmd = ["python3", "scripts/cli_healthcheck.py"]
    for item in required or []:
        cmd.extend(["--require", item])
    result = run_cmd(cmd, cwd=ROOT, check=False)
    payload = json.loads(result.stdout) if result.stdout.strip() else {"binaries": [], "tmux_sessions": []}
    payload["status"] = "ok" if result.returncode == 0 else "degraded"
    payload["returncode"] = result.returncode
    return payload


def taskmaster_sync(spec: str, config: dict[str, Any]) -> dict[str, Any]:
    tm_cfg = config.get("taskmaster", {})
    if not tm_cfg.get("enabled", False):
        return {"enabled": False}

    payload: dict[str, Any] = {"enabled": True}
    import_file = tm_cfg.get("import_file", "")
    if import_file:
        input_path = ROOT / import_file if not Path(import_file).is_absolute() else Path(import_file)
        if input_path.exists():
            result = autoflow_json("import-taskmaster", "--spec", spec, "--input", str(input_path))
            payload["import"] = result
        else:
            payload["import"] = {"missing": str(input_path)}
    export_file = tm_cfg.get("export_file", "")
    if export_file:
        output_path = ROOT / export_file if not Path(export_file).is_absolute() else Path(export_file)
        run_cmd(["python3", "scripts/autoflow.py", "export-taskmaster", "--spec", spec, "--output", str(output_path)], cwd=ROOT)
        payload["export_file"] = str(output_path)
    return payload


def coordination_brief(spec: str, continuous_config: str, config: dict[str, Any]) -> dict[str, Any]:
    ci_config = load_config(continuous_config)
    workflow = autoflow_json("workflow-state", "--spec", spec)
    strategy = autoflow_json("show-strategy", "--spec", spec)
    health = health_report(config.get("monitoring", {}).get("required_binaries", []))
    agents_catalog = load_json(AGENTS_FILE, default={"agents": {}}).get("agents", {})
    discovered = load_json(DISCOVERED_AGENTS_FILE, default={}).get("agents", [])
    next_action = workflow.get("recommended_next_action")
    proposed_dispatch: dict[str, Any] | None = None
    if next_action:
        agent, source = continuous_iteration.select_agent_for_role(
            ci_config,
            next_action["owner_role"],
            agents_catalog,
        )
        proposed_dispatch = {
            "task": next_action["id"],
            "role": next_action["owner_role"],
            "agent": agent,
            "agent_selection": source,
        }
    return {
        "spec": spec,
        "workflow_state": workflow,
        "strategy": strategy,
        "health": health,
        "available_agents": sorted(agents_catalog.keys()),
        "discovered_agents": discovered,
        "proposed_dispatch": proposed_dispatch,
        "openclaw": config.get("openclaw", {}),
    }


def run_tick(
    spec: str,
    autonomy_config: str,
    dispatch: bool,
    commit_if_dirty: bool,
    push: bool,
) -> dict[str, Any]:
    config = load_config(autonomy_config)
    continuous_config = config.get("continuous_iteration_config", "config/continuous-iteration.example.json")
    taskmaster = taskmaster_sync(spec, config)
    brief = coordination_brief(spec, continuous_config, config)
    monitoring_cfg = config.get("monitoring", {})
    if brief["health"].get("returncode", 0) != 0 and monitoring_cfg.get("block_on_missing_binaries", True):
        return {
            "spec": spec,
            "taskmaster": taskmaster,
            "coordination_brief": brief,
            "blocked": "binary_healthcheck_failed",
        }

    cmd = [
        "python3",
        "scripts/continuous_iteration.py",
        "--spec",
        spec,
        "--config",
        continuous_config,
    ]
    if dispatch:
        cmd.append("--dispatch")
    if commit_if_dirty:
        cmd.append("--commit-if-dirty")
    if push:
        cmd.append("--push")
    iteration = json.loads(run_cmd(cmd, cwd=ROOT).stdout)

    return {
        "spec": spec,
        "taskmaster": taskmaster,
        "coordination_brief": brief,
        "iteration": iteration,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Outer-loop autonomy orchestrator for Autoflow")
    sub = parser.add_subparsers(dest="command", required=True)

    brief_cmd = sub.add_parser("coordination-brief", help="build an OpenClaw-friendly coordination brief")
    brief_cmd.add_argument("--spec", required=True)
    brief_cmd.add_argument("--config", default="config/autonomy.example.json")

    tick_cmd = sub.add_parser("tick", help="run one outer-loop orchestration tick")
    tick_cmd.add_argument("--spec", required=True)
    tick_cmd.add_argument("--config", default="config/autonomy.example.json")
    tick_cmd.add_argument("--dispatch", action="store_true")
    tick_cmd.add_argument("--commit-if-dirty", action="store_true")
    tick_cmd.add_argument("--push", action="store_true")

    args = parser.parse_args()
    if args.command == "coordination-brief":
        config = load_config(args.config)
        payload = coordination_brief(
            args.spec,
            config.get("continuous_iteration_config", "config/continuous-iteration.example.json"),
            config,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return

    payload = run_tick(args.spec, args.config, args.dispatch, args.commit_if_dirty, args.push)
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
