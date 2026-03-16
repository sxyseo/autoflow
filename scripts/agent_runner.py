#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.integrity import verify_file_integrity
from scripts.agent_validation import ValidationError, validate_agent_spec, validate_path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def get_config(config_path: str | Path) -> dict[str, Any]:
    """Load configuration from a JSON file.

    Args:
        config_path: Path to the configuration file

    Returns:
        Parsed configuration dictionary

    Raises:
        SystemExit: If the config file doesn't exist or contains invalid JSON
    """
    config_file = Path(config_path)
    if not config_file.exists():
        raise SystemExit(f"configuration file not found: {config_file}")
    try:
        return read_json(config_file)
    except json.JSONDecodeError as e:
        raise SystemExit(f"invalid JSON in configuration file {config_file}: {e}") from e
    except OSError as e:
        raise SystemExit(f"error reading configuration file {config_file}: {e}") from e


def verify_prompt_integrity(prompt_file: str, run_metadata: dict[str, Any] | None) -> None:
    """Verify prompt.md file integrity before loading.

    Args:
        prompt_file: Path to the prompt file
        run_metadata: Run metadata containing integrity hashes

    Raises:
        SystemExit: If integrity verification fails
    """
    if not run_metadata:
        # No integrity metadata available, skip verification
        return

    integrity = run_metadata.get("integrity")
    if not integrity:
        # No integrity hashes in metadata, skip verification
        return

    expected_hash = integrity.get("prompt.md")
    if not expected_hash:
        # No hash for prompt.md, skip verification
        return

    # Verify the prompt file integrity
    if not verify_file_integrity(prompt_file, expected_hash):
        raise SystemExit(
            f"integrity check failed for {prompt_file}: file may have been tampered with"
        )


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


def resolve_cli_base_dir(raw_paths: list[str]) -> Path:
    """Infer a safe shared base directory for CLI file arguments."""
    resolved_paths = [Path(path).expanduser().resolve() for path in raw_paths]
    common_path = Path(os.path.commonpath([str(path) for path in resolved_paths]))
    root_path = Path(common_path.anchor)
    if common_path == root_path or common_path.parent == root_path:
        raise SystemExit(
            "Invalid file paths: arguments must share a non-root base directory"
        )
    return common_path


def main() -> None:
    if len(sys.argv) not in {4, 5}:
        raise SystemExit("usage: agent_runner.py <agents-json> <agent-name> <prompt-file> [run-json]")

    raw_paths = [sys.argv[1], sys.argv[3]]
    if len(sys.argv) == 5:
        raw_paths.append(sys.argv[4])
    cli_base_dir = resolve_cli_base_dir(raw_paths)

    # Security: Validate agents_file is within expected directory
    agents_file = Path(sys.argv[1])
    try:
        validated_agents_path = validate_path(
            str(agents_file),
            base_dir=str(cli_base_dir),
            allow_absolute=True,
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
            base_dir=str(cli_base_dir),
            allow_absolute=True,
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
                base_dir=str(cli_base_dir),
                allow_absolute=True,
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

    # Verify prompt.md integrity before loading
    verify_prompt_integrity(prompt_file, run_metadata)

    command = build_command(resolved_spec, prompt_file, run_metadata=run_metadata)

    # Security: Final validation before executing command
    try:
        validate_agent_spec(resolved_spec, validate_all_fields=True)
    except (ValidationError, ValueError) as e:
        raise SystemExit(f"Invalid agent configuration: {e}") from e

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
