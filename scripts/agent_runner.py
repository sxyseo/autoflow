#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autoflow.agents.runner import build_command


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if len(sys.argv) not in {4, 5}:
        raise SystemExit("usage: agent_runner.py <agents-json> <agent-name> <prompt-file> [run-json]")
    agents_file = Path(sys.argv[1])
    agent_name = sys.argv[2]
    prompt_file = sys.argv[3]
    run_json = Path(sys.argv[4]) if len(sys.argv) == 5 else None

    data = read_json(agents_file)
    spec = data["agents"].get(agent_name)
    if not spec:
        raise SystemExit(f"unknown agent: {agent_name}")
    run_metadata = read_json(run_json) if run_json and run_json.exists() else None
    resolved_spec = dict(spec)
    if run_metadata and run_metadata.get("agent_config"):
        resolved_spec.update(run_metadata["agent_config"])
    command = build_command(resolved_spec, prompt_file, run_metadata=run_metadata)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
