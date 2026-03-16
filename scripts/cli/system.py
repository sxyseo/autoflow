"""
Autoflow CLI - System Commands

Manage system configuration, validation, and initialization.

Usage:
    from scripts.cli.system import add_subparser, show_system_config

    # Register system commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    show_system_config(args)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    AGENTS_FILE,
    SYSTEM_CONFIG_FILE,
    ensure_state,
    invalidate_system_config_cache,
    load_system_config,
    print_json,
    read_json,
    read_json_or_default,
    system_config_default,
    write_json,
)

# For now, import helper functions from the monolithic autoflow.py
# These will be moved to utils.py in future tasks
# Use lazy imports to avoid circular dependency issues


def _get_invalidate_config_cache():
    """Lazy import of invalidate_config_cache from autoflow.py (temporary)."""
    # This function will be moved to utils.py in future tasks
    import scripts.autoflow as af
    return af.invalidate_config_cache


def show_system_config(_: argparse.Namespace) -> None:
    """
    Display the current system configuration.

    Prints the system configuration as formatted JSON. The configuration is
    loaded from system.json (if it exists) and merged with defaults from
    the system config template.

    The output includes:
    - memory: Memory settings and file paths
    - models: Model profile configurations
    - tools: Tool profile configurations
    - registry: Registry settings
    """
    print_json(load_system_config())


def init_system_config(_: argparse.Namespace) -> None:
    """
    Initialize the system configuration file.

    Creates the system configuration file at .autoflow/system.json with default
    values. If the file already exists, this command does nothing (it will not
    overwrite existing configuration).

    The configuration is loaded from config/system.example.json if it exists,
    otherwise uses hardcoded defaults. The configuration includes:
    - memory: Memory settings and file paths
    - models: Model profile configurations
    - tools: Tool profile configurations
    - registry: Registry settings

    Prints the path to the configuration file after initialization.
    """
    ensure_state()
    if not SYSTEM_CONFIG_FILE.exists():
        # NOTE: This writes to SYSTEM_CONFIG_FILE (system.json)
        # Cache invalidation required: call invalidate_config_cache() after this write
        write_json(SYSTEM_CONFIG_FILE, system_config_default())
        _get_invalidate_config_cache()()
    print(str(SYSTEM_CONFIG_FILE))


def validate_config_cmd(_: argparse.Namespace) -> None:
    """
    Validate Autoflow system and agent configuration files.

    Performs comprehensive validation of system and agent configuration files,
    checking for missing files, invalid agent specifications, unknown profiles,
    and missing required fields.

    The validation results are printed as JSON containing:
    - valid: Overall validation status (True if no issues)
    - issues: List of critical issues found (empty if valid)
    - warnings: List of non-critical warnings
    - checks: Detailed breakdown of validation results including:
        - system_config_file: Path and existence status
        - agents_file: Path and existence status
        - agents: List of per-agent validation results with:
            - name: Agent name
            - protocol: Agent protocol (cli or acp)
            - command: Agent command string
            - valid: Whether the agent configuration is valid
            - issues: List of issues specific to this agent
            - warnings: List of warnings specific to this agent

    Validation checks:
    - system.json exists
    - agents.json exists
    - Each agent has a command field
    - ACP agents have transport configuration
    - model_profile references exist in system config
    - tool_profile references exist in system config
    """
    ensure_state()
    issues: list[str] = []
    warnings: list[str] = []
    system_config = load_system_config()
    checks: dict[str, Any] = {
        "system_config_file": {
            "path": str(SYSTEM_CONFIG_FILE),
            "exists": SYSTEM_CONFIG_FILE.exists(),
        },
        "agents_file": {
            "path": str(AGENTS_FILE),
            "exists": AGENTS_FILE.exists(),
        },
    }
    if not AGENTS_FILE.exists():
        issues.append("missing .autoflow/agents.json")
        agents_payload = {"agents": {}}
    else:
        agents_payload = read_json_or_default(AGENTS_FILE, {"agents": {}})
    model_profiles = system_config.get("models", {}).get("profiles", {})
    tool_profiles = system_config.get("tools", {}).get("profiles", {})
    agent_checks = []
    for name, spec in agents_payload.get("agents", {}).items():
        entry = {
            "name": name,
            "protocol": spec.get("protocol", "cli"),
            "command": spec.get("command", ""),
            "valid": True,
            "issues": [],
            "warnings": [],
        }
        if not entry["command"]:
            entry["valid"] = False
            entry["issues"].append("missing command")
        if spec.get("model_profile") and spec["model_profile"] not in model_profiles:
            entry["warnings"].append(f"unknown model_profile: {spec['model_profile']}")
        if spec.get("tool_profile") and spec["tool_profile"] not in tool_profiles:
            entry["warnings"].append(f"unknown tool_profile: {spec['tool_profile']}")
        if spec.get("protocol") == "acp" and not spec.get("transport"):
            entry["valid"] = False
            entry["issues"].append("missing ACP transport")
        if not entry["valid"]:
            issues.extend(f"{name}: {item}" for item in entry["issues"])
        warnings.extend(f"{name}: {item}" for item in entry["warnings"])
        agent_checks.append(entry)
    checks["agents"] = agent_checks
    print(
        json.dumps(
            {
                "valid": not issues,
                "issues": issues,
                "warnings": warnings,
                "checks": checks,
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register system command subparsers with the argument parser.

    This function is called during CLI initialization to add all system-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    init_system_cmd = sub.add_parser("init-system-config", help="write the local system config scaffold")
    init_system_cmd.set_defaults(func=init_system_config)

    system_cmd = sub.add_parser("show-system-config", help="show system memory/model/tool config")
    system_cmd.set_defaults(func=show_system_config)

    validate_cmd = sub.add_parser("validate-config", help="validate Autoflow system and agent config files")
    validate_cmd.set_defaults(func=validate_config_cmd)
