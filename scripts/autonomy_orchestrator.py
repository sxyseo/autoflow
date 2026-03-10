#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.orchestration.autonomy import coordination_brief, run_tick


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / ".autoflow"


def load_config(path: str) -> dict[str, Any]:
    """Load configuration from a path relative to ROOT."""
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


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
        continuous_config = config.get("continuous_iteration_config", "config/continuous-iteration.example.json")
        payload = coordination_brief(ROOT, STATE_DIR, args.spec, continuous_config, config)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return

    payload = run_tick(ROOT, STATE_DIR, args.spec, args.config, args.dispatch, args.commit_if_dirty, args.push)
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
