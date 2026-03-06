#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt(prompt_file: str) -> str:
    return Path(prompt_file).read_text(encoding="utf-8")


def build_command(agent_spec: dict[str, Any], prompt_file: str, run_metadata: dict[str, Any] | None = None) -> list[str]:
    prompt_text = load_prompt(prompt_file)
    command = [agent_spec["command"], *agent_spec.get("args", [])]
    resume = agent_spec.get("resume")
    if run_metadata and run_metadata.get("resume_from") and resume:
        mode = resume.get("mode", "none")
        resume_args = list(resume.get("args", []))
        if mode == "subcommand":
            subcommand = resume.get("subcommand", "resume")
            return [agent_spec["command"], *agent_spec.get("args", []), subcommand, *resume_args, prompt_text]
        if mode == "args":
            return [agent_spec["command"], *agent_spec.get("args", []), *resume_args, prompt_text]
    return [*command, prompt_text]


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
    command = build_command(spec, prompt_file, run_metadata=run_metadata)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
