#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import cli_healthcheck
import continuous_iteration

from autoflow.core.commands import (
    get_strategy_summary,
    get_workflow_state,
    taskmaster_export,
    taskmaster_import,
)

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"
AGENTS_FILE = STATE_DIR / "agents.json"
DISCOVERED_AGENTS_FILE = STATE_DIR / "discovered_agents.json"


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def load_config(path: str) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return result


def get_config() -> dict[str, Any]:
    result: dict[str, Any] = load_config("config/autonomy.example.json")
    return result


def health_report(required: list[str] | None = None) -> dict[str, Any]:
    report = cli_healthcheck.build_report()
    payload: dict[str, Any] = dict(report)
    if required:
        missing = [
            item["name"]
            for item in report.get("binaries", [])
            if item["name"] in required and not item["available"]
        ]
        payload["returncode"] = 0 if not missing else 1
        payload["status"] = "ok" if not missing else "degraded"
    else:
        payload["returncode"] = 0
        payload["status"] = "ok"
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
            result = taskmaster_import(spec, str(input_path))
            payload["import"] = result
        else:
            payload["import"] = {"missing": str(input_path)}
    export_file = tm_cfg.get("export_file", "")
    if export_file:
        output_path = ROOT / export_file if not Path(export_file).is_absolute() else Path(export_file)
        taskmaster_export(spec, str(output_path))
        payload["export_file"] = str(output_path)
    return payload


def coordination_brief(spec: str, continuous_config: str, config: dict[str, Any]) -> dict[str, Any]:
    ci_config = load_config(continuous_config)
    workflow = get_workflow_state(spec)
    strategy = get_strategy_summary(spec)
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

    # Load continuous iteration config and run iteration
    ci_cfg = continuous_iteration.load_config(continuous_config)
    result: dict[str, Any] = {"spec": spec}
    initial_state = continuous_iteration.workflow_state(spec)
    if commit_if_dirty:
        result["commit"] = continuous_iteration.auto_commit(ci_cfg, spec, push, initial_state)
    result["dispatch"] = continuous_iteration.dispatch_next(ci_cfg, spec, dispatch)

    return {
        "spec": spec,
        "taskmaster": taskmaster,
        "coordination_brief": brief,
        "iteration": result,
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
