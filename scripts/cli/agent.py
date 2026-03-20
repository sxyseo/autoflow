"""
Autoflow CLI - Agent Commands

Manage agent discovery, configuration, and testing.

Usage:
    from scripts.cli.agent import add_subparser, discover_agents_cmd

    # Register agent commands with argparse
    subparsers = parser.add_subparsers(dest="command")
    add_subparser(subparsers)

    # Use command functions directly
    discover_agents_cmd(args)
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

# Import utilities from cli.utils
from scripts.cli.utils import (
    AGENTS_FILE,
    DISCOVERY_FILE,
    ensure_state,
    now_stamp,
    print_json,
    read_json,
    read_json_or_default,
    run_cmd,
    write_json,
    load_system_config,
    invalidate_system_config_cache as invalidate_config_cache,
)

# Import ROOT for path setup
from scripts.cli.utils import ROOT


def discover_cli_agent(name: str, command: str) -> dict[str, Any] | None:
    """
    Discover a CLI agent by checking command availability and capabilities.

    Attempts to locate the specified command on the system PATH and analyzes
    its help output to determine supported capabilities. This enables automatic
    detection of agent features like resume support and model selection flags.

    Detection capabilities:
    - resume: Checks for "resume" or "--continue" in help text
    - model_flag: Checks for "--model" or " -m," in help text

    Args:
        name: Identifier name for the agent (e.g., "claude", "codex")
        command: Executable command to search for (e.g., "claude", "codex")

    Returns:
        Dictionary containing discovered agent information with keys:
        - name: Agent identifier
        - protocol: Always "cli" for this function
        - command: The command string
        - path: Full path to the executable
        - capabilities: Dict of boolean flags (resume, model_flag)

        Returns None if the command is not found on PATH.

    Example:
        >>> agent = discover_cli_agent("claude", "claude")
        >>> if agent:
        ...     print(agent["path"])
        ...     print(agent["capabilities"]["resume"])
    """
    executable = shutil.which(command)
    if not executable:
        return None
    help_result = run_cmd([command, "--help"], check=False)
    help_text = (help_result.stdout or "") + (help_result.stderr or "")
    capabilities = {
        "resume": "resume" in help_text.lower() or "--continue" in help_text,
        "model_flag": "--model" in help_text or " -m," in help_text,
    }
    protocol = "cli"
    return {
        "name": name,
        "protocol": protocol,
        "command": command,
        "path": executable,
        "capabilities": capabilities,
    }


def discover_agents_registry() -> dict[str, Any]:
    """
    Discover all available agents from CLI and system configuration registry.

    Performs comprehensive agent discovery by:
    1. Checking for CLI-based agents (codex, claude) on the system PATH
    2. Loading additional agents from the system config registry (ACP protocol)

    CLI agents are discovered by probing for executable commands and their
    capabilities. Registry agents are loaded from the system configuration's
    registry.acp_agents section, which typically contains ACP (Agent Control
    Protocol) agents with custom transport configurations.

    The discovery results are cached to DISCOVERY_FILE for persistence and
    returned with metadata about when the discovery was performed.

    Returns:
        Dictionary containing:
        - discovered_at: ISO 8601 timestamp of when discovery was performed
        - agents: List of discovered agent dictionaries, each containing:
            - name: Agent identifier
            - protocol: "cli" or "acp"
            - command/path (for CLI agents)
            - transport (for ACP agents)
            - capabilities: Dict of supported features
        - system_config: Relevant sections from system config including:
            - memory: Memory configuration
            - models: Model profiles
            - tools: Tool configurations

    Side Effects:
        Writes discovery results to DISCOVERY_FILE (discovered_agents.json)

    Example:
        >>> registry = discover_agents_registry()
        >>> print(f"Found {len(registry['agents'])} agents")
        >>> for agent in registry['agents']:
        ...     print(f"  - {agent['name']} ({agent['protocol']})")
    """
    config = load_system_config()
    discovered = []
    for name, command in [("codex", "codex"), ("claude", "claude")]:
        item = discover_cli_agent(name, command)
        if item:
            discovered.append(item)
    for agent in config.get("registry", {}).get("acp_agents", []):
        discovered.append(
            {
                "name": agent.get("name", "acp-agent"),
                "protocol": "acp",
                "transport": agent.get("transport", {}),
                "capabilities": agent.get("capabilities", {}),
            }
        )
    payload = {
        "discovered_at": now_stamp(),
        "agents": discovered,
        "system_config": {
            "memory": config.get("memory", {}),
            "models": config.get("models", {}),
            "tools": config.get("tools", {}),
        },
    }
    write_json(DISCOVERY_FILE, payload)
    return payload


def resolve_agent_profiles(spec: dict[str, Any], system_config: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve model and tool profiles in an agent specification.

    Expands named profiles (model_profile, tool_profile) to their actual
    values from system configuration. Also sets default memory_scopes
    if not specified.

    Args:
        spec: Agent specification dictionary with potential profile references
        system_config: System configuration containing model and tool profiles

    Returns:
        Resolved agent specification with expanded profiles
    """
    resolved = dict(spec)
    model_profiles = system_config.get("models", {}).get("profiles", {})
    tool_profiles = system_config.get("tools", {}).get("profiles", {})
    if not resolved.get("model") and resolved.get("model_profile"):
        resolved["model"] = model_profiles.get(resolved["model_profile"], "")
    if not resolved.get("tools") and resolved.get("tool_profile"):
        resolved["tools"] = tool_profiles.get(resolved["tool_profile"], [])
    if not resolved.get("memory_scopes"):
        resolved["memory_scopes"] = list(
            system_config.get("memory", {}).get("default_scopes", ["spec"])
        )
    return resolved


def discovered_agent_to_config(agent: dict[str, Any]) -> dict[str, Any]:
    """
    Transform a discovered agent registry entry into an Autoflow agent configuration.

    Converts agent discovery data into the standard Autoflow agent configuration format,
    handling both ACP (Agent Communication Protocol) agents and CLI agents. For CLI
    agents, configures resume behavior based on agent capabilities.

    Args:
        agent: Discovered agent metadata from the agent registry. Contains protocol,
            command, name, capabilities, and optional transport configuration.

    Returns:
        A dictionary with agent configuration including:
        - protocol: "acp" or "cli"
        - command: Command to run the agent
        - args: List of command arguments (typically empty)
        - transport: Transport config for ACP agents
        - resume: Resume configuration for CLI agents with resume capability
        - memory_scopes: List of memory scopes (defaults to ["spec"])
    """
    if agent.get("protocol") == "acp":
        return {
            "protocol": "acp",
            "command": agent.get("transport", {}).get("command", agent.get("name", "acp-agent")),
            "args": [],
            "transport": agent.get("transport", {}),
            "memory_scopes": ["spec"],
        }
    resume = None
    if agent.get("name") == "codex" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "subcommand", "subcommand": "resume", "args": ["--last"]}
    elif agent.get("name") == "claude" and agent.get("capabilities", {}).get("resume"):
        resume = {"mode": "args", "args": ["--continue"]}
    return {
        "protocol": "cli",
        "command": agent.get("command", agent.get("name", "")),
        "args": [],
        "resume": resume,
        "memory_scopes": ["spec"],
    }


def sync_discovered_agents(overwrite: bool = False) -> dict[str, Any]:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into agents.json, preserving existing
    agent configurations by default. Can optionally overwrite existing entries.
    Creates the agents file with default structure if it doesn't exist.

    Args:
        overwrite: If True, replace existing agent configurations with discovered
            ones. If False, preserve existing configurations and only add new agents.

    Returns:
        A dictionary containing sync results:
        - agents_file: Path to the agents.json file
        - added: List of agent names that were added or updated
        - total_agents: Total number of agents after sync
    """
    ensure_state()
    discovered = discover_agents_registry()
    existing = {"defaults": {"workspace": ".", "shell": "bash"}, "agents": {}}
    if AGENTS_FILE.exists():
        existing = read_json_or_default(AGENTS_FILE, existing)
        existing.setdefault("defaults", {"workspace": ".", "shell": "bash"})
        existing.setdefault("agents", {})
    merged = dict(existing["agents"])
    added = []
    for agent in discovered.get("agents", []):
        name = agent["name"]
        if name in merged and not overwrite:
            continue
        merged[name] = discovered_agent_to_config(agent)
        added.append(name)
    payload = {"defaults": existing["defaults"], "agents": merged}
    # NOTE: This writes to AGENTS_FILE (agents.json)
    # Cache invalidation required: call invalidate_config_cache() after this write
    write_json(AGENTS_FILE, payload)
    invalidate_config_cache()
    return {
        "agents_file": str(AGENTS_FILE),
        "added": added,
        "total_agents": len(merged),
    }


def discover_agents_cmd(_: argparse.Namespace) -> None:
    """
    Discover and display all available agents.

    Performs comprehensive agent discovery by checking for CLI-based agents
    (codex, claude) on the system PATH and loading additional agents from the
    system configuration registry (ACP protocol).

    The discovery results are printed as JSON containing:
    - discovered_at: ISO 8601 timestamp of when discovery was performed
    - agents: List of discovered agent dictionaries with name, protocol,
      command/path, transport, and capabilities
    - system_config: Relevant sections from system config including memory,
      models, and tools configurations

    The discovery results are also cached to .autoflow/discovered_agents.json
    for persistence and use by other commands.
    """
    print_json(discover_agents_registry())


def sync_agents_cmd(args: argparse.Namespace) -> None:
    """
    Sync discovered agents from the registry into the agents configuration file.

    Merges agents from the discovery registry into .autoflow/agents.json,
    preserving existing agent configurations by default. Can optionally
    overwrite existing entries when the --overwrite flag is provided.

    Creates the agents file with default structure if it doesn't exist.

    The sync results are printed as JSON containing:
    - agents_file: Path to the agents.json file
    - added: List of agent names that were added or updated
    - total_agents: Total number of agents after sync

    Args:
        args: Namespace with optional overwrite attribute (bool). If True,
            replaces existing agent configurations with discovered ones.
            If False, preserves existing configurations and only adds new agents.
    """
    print_json(sync_discovered_agents(overwrite=args.overwrite))


def test_agent_cmd(args: argparse.Namespace) -> None:
    """
    Test whether a configured or named agent is actually runnable.

    Checks if an agent is properly configured and available on the system.
    For configured agents, validates the resolved configuration including
    protocol, command, and model settings. For ACP protocol agents, checks
    if the transport command is executable. For CLI agents, checks if the
    binary is discoverable on the PATH.

    The test results are printed as JSON containing:
    - agent: Agent name being tested
    - configured: Whether the agent has a configuration in agents.json
    - ready: Whether the agent is ready to run
    - protocol: Agent protocol (cli or acp)
    - command: Command string for the agent
    - model: Resolved model identifier
    - path: Full path to the executable (if found)
    - transport: Transport configuration (for ACP agents)
    - capabilities: Discovered capabilities (for CLI agents)
    - issues: List of any issues found (empty if ready=True)

    Args:
        args: Namespace with agent attribute containing the name of the agent
            to test.
    """
    configured = read_json_or_default(AGENTS_FILE, {"agents": {}}).get("agents", {}).get(args.agent)
    payload = {
        "agent": args.agent,
        "configured": bool(configured),
        "ready": False,
        "issues": [],
    }
    if configured:
        resolved = resolve_agent_profiles(configured, load_system_config())
        payload["protocol"] = resolved.get("protocol", "cli")
        payload["command"] = resolved.get("command", "")
        payload["model"] = resolved.get("model", "")
        if payload["protocol"] == "acp":
            transport = resolved.get("transport", {})
            payload["transport"] = transport
            command = transport.get("command", resolved.get("command", ""))
            payload["path"] = shutil.which(command) or ""
            payload["ready"] = bool(command) and bool(payload["path"])
            if not payload["ready"]:
                payload["issues"].append("ACP transport command is not executable")
        else:
            discovered = discover_cli_agent(args.agent, resolved.get("command", ""))
            if not discovered:
                payload["issues"].append("CLI agent binary not found")
            else:
                payload["path"] = discovered.get("path", "")
                payload["capabilities"] = discovered.get("capabilities", {})
                payload["ready"] = True
    else:
        discovered = discover_cli_agent(args.agent, args.agent)
        if not discovered:
            payload["issues"].append("agent is neither configured nor discoverable by binary name")
        else:
            payload.update(
                {
                    "protocol": discovered.get("protocol", "cli"),
                    "command": discovered.get("command", args.agent),
                    "path": discovered.get("path", ""),
                    "capabilities": discovered.get("capabilities", {}),
                    "ready": True,
                }
            )
    print(json.dumps(payload, indent=2, ensure_ascii=True))


def add_subparser(sub: argparse._SubParsersAction) -> None:
    """
    Register agent command subparsers with the argument parser.

    This function is called during CLI initialization to add all agent-related
    commands to the argument parser.

    Args:
        sub: The subparsers action from the main argument parser

    Example:
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_subparser(subparsers)
    """
    discover_cmd = sub.add_parser("discover-agents", help="probe local agents and merge ACP registry entries")
    discover_cmd.set_defaults(func=discover_agents_cmd)

    sync_cmd = sub.add_parser("sync-agents", help="merge discovered CLI/ACP agents into .autoflow/agents.json")
    sync_cmd.add_argument("--overwrite", action="store_true")
    sync_cmd.set_defaults(func=sync_agents_cmd)

    test_agent = sub.add_parser("test-agent", help="test whether a configured or named agent is actually runnable")
    test_agent.add_argument("--agent", required=True)
    test_agent.set_defaults(func=test_agent_cmd)
