#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from scripts.agent_validation import ValidationError, validate_agent_spec, validate_path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt(prompt_file: str) -> str:
    return Path(prompt_file).read_text(encoding="utf-8")


def apply_runtime_config(command: list[str], agent_spec: dict[str, Any]) -> list[str]:
    configured = list(command)
    model = agent_spec.get("model")
    if model:
        configured.extend(["--model", model])
    tools = agent_spec.get("tools") or []
    if tools and agent_spec.get("command") == "claude":
        configured.extend(["--allowedTools", ",".join(tools)])
    extra = agent_spec.get("runtime_args") or []
    configured.extend(extra)
    return configured


def build_command(agent_spec: dict[str, Any], prompt_file: str, run_metadata: dict[str, Any] | None = None) -> list[str]:
    # Security: Validate agent specification before building command
    try:
        validate_agent_spec(agent_spec, validate_all_fields=True)
    except (ValidationError, ValueError) as e:
        raise SystemExit(f"Invalid agent specification: {e}") from e

    prompt_text = load_prompt(prompt_file)
    protocol = agent_spec.get("protocol", "cli")
    if protocol == "acp":
        transport = agent_spec.get("transport", {})
        if transport.get("type", "stdio") != "stdio":
            raise SystemExit("only stdio ACP transport is supported in the local runner")
        entrypoint = transport.get("command") or agent_spec.get("command")

        # Security: Validate that entrypoint is present for ACP protocol
        if not entrypoint:
            raise SystemExit(
                "ACP protocol requires a command. "
                "Set transport.command or agent_spec.command"
            )

        args = list(transport.get("args", []))
        prompt_mode = transport.get("prompt_mode", "argv")
        if prompt_mode == "argv":
            return [entrypoint, *args, prompt_text]
        raise SystemExit("unsupported ACP prompt mode for local runner")

    command = apply_runtime_config([agent_spec["command"], *agent_spec.get("args", [])], agent_spec)
    resume = agent_spec.get("resume")
    if run_metadata and run_metadata.get("resume_from") and resume:
        mode = resume.get("mode", "none")
        resume_args = list(resume.get("args", []))
        if mode == "subcommand":
            subcommand = resume.get("subcommand", "resume")
            return [*command, subcommand, *resume_args, prompt_text]
        if mode == "args":
            return [*command, *resume_args, prompt_text]
    return [*command, prompt_text]


def main() -> None:
    if len(sys.argv) not in {4, 5}:
        raise SystemExit("usage: agent_runner.py <agents-json> <agent-name> <prompt-file> [run-json]")

    # Security: Validate agents_file is within expected directory
    agents_file = Path(sys.argv[1])
    try:
        validated_agents_path = validate_path(
            str(agents_file),
            base_dir=str(Path.cwd()),  # Use current directory as base
            allow_absolute=True  # Allow absolute paths within current directory
        )
        agents_file = validated_agents_path
    except ValidationError as e:
        raise SystemExit(f"Invalid agents file path: {e}") from e

    # Security: Validate agent_name format
    agent_name = sys.argv[2]
    if not re.match(r"^[a-zA-Z0-9_-]+$", agent_name):
        raise SystemExit(f"Invalid agent name: {agent_name}")

    # Security: Validate prompt_file is within expected directory
    prompt_file = sys.argv[3]
    try:
        validated_prompt_path = validate_path(
            prompt_file,
            base_dir=str(Path.cwd()),  # Use current directory as base
            allow_absolute=True  # Allow absolute paths within current directory
        )
        prompt_file = str(validated_prompt_path)
    except ValidationError as e:
        raise SystemExit(f"Invalid prompt file path: {e}") from e

    # Security: Validate run_json if provided
    run_json = None
    if len(sys.argv) == 5:
        run_json = Path(sys.argv[4])
        try:
            validated_run_json = validate_path(
                str(run_json),
                base_dir=str(Path.cwd()),  # Use current directory as base
                allow_absolute=True  # Allow absolute paths within current directory
            )
            run_json = validated_run_json
        except ValidationError as e:
            raise SystemExit(f"Invalid run metadata path: {e}") from e

    data = read_json(agents_file)
    spec = data["agents"].get(agent_name)
    if not spec:
        raise SystemExit(f"unknown agent: {agent_name}")
    run_metadata = read_json(run_json) if run_json and run_json.exists() else None
    resolved_spec = dict(spec)
    if run_metadata and run_metadata.get("agent_config"):
        resolved_spec.update(run_metadata["agent_config"])
    command = build_command(resolved_spec, prompt_file, run_metadata=run_metadata)

    # Security: Final validation before executing command
    try:
        validate_agent_spec(resolved_spec, validate_all_fields=True)
    except (ValidationError, ValueError) as e:
        raise SystemExit(f"Invalid agent configuration: {e}") from e

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
