"""
Autoflow Agent Runner Module

Provides agent command building and execution functionality.
This module extracts business logic from scripts/agent_runner.py into a
testable class using dependency injection for configuration.

Usage:
    from autoflow.agents.runner import AgentRunner, build_command
    from autoflow.core.config import load_config

    config = load_config()
    runner = AgentRunner(config)
    command = runner.build_command(agent_spec, "prompt.txt")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional, Union

from autoflow.core.config import Config


class AgentRunnerError(Exception):
    """Base exception for agent runner errors."""

    pass


class AgentRunner:
    """
    Agent command builder and executor.

    This class encapsulates the business logic from the original
    scripts/agent_runner.py, making it testable through dependency
    injection of configuration.

    Attributes:
        config: Autoflow configuration object

    Example:
        >>> from autoflow.core.config import load_config
        >>> from autoflow.agents.runner import AgentRunner
        >>>
        >>> config = load_config()
        >>> runner = AgentRunner(config)
        >>> agent_spec = {
        ...     "command": "claude",
        ...     "args": ["--print"],
        ...     "protocol": "cli"
        ... }
        >>> command = runner.build_command(agent_spec, "prompt.txt")
    """

    def __init__(
        self,
        config: Config,
    ):
        """
        Initialize the AgentRunner.

        Args:
            config: Autoflow configuration object
        """
        self.config = config

    # === Utility Methods ===

    @staticmethod
    def read_json(path: Path) -> Any:
        """
        Read and parse a JSON file.

        Args:
            path: Path to the JSON file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def load_prompt(prompt_file: Union[str, Path]) -> str:
        """
        Load prompt text from a file.

        Args:
            prompt_file: Path to the prompt file

        Returns:
            Prompt text content

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        path = Path(prompt_file)
        return path.read_text(encoding="utf-8")

    @staticmethod
    def apply_runtime_config(command: list[str], agent_spec: dict[str, Any]) -> list[str]:
        """
        Apply runtime configuration to a command.

        Adds model, tools, and runtime arguments to the base command
        based on the agent specification.

        Args:
            command: Base command as list of strings
            agent_spec: Agent specification dictionary

        Returns:
            Command with runtime configuration applied
        """
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

    def build_command(
        self,
        agent_spec: dict[str, Any],
        prompt_file: Union[str, Path],
        run_metadata: Optional[dict[str, Any]] = None,
    ) -> list[str]:
        """
        Build a command list for running an agent.

        Constructs a complete command including the agent executable,
        arguments, resume configuration, and prompt text. Supports
        both CLI and ACP protocols.

        Args:
            agent_spec: Agent specification dictionary containing:
                - command: Agent executable/command
                - args: Base arguments for the command
                - protocol: Either "cli" or "acp" (default: "cli")
                - transport: ACP transport configuration (for acp protocol)
                - model: Optional model override
                - tools: Optional list of allowed tools
                - runtime_args: Optional additional runtime arguments
                - resume: Optional resume configuration dict
            prompt_file: Path to the file containing the prompt text
            run_metadata: Optional run metadata containing:
                - resume_from: Whether to resume from a previous run
                - agent_config: Optional agent config overrides

        Returns:
            Complete command as list of strings ready for subprocess execution

        Raises:
            AgentRunnerError: If an unsupported configuration is encountered
            FileNotFoundError: If the prompt file doesn't exist

        Example:
            >>> runner = AgentRunner(config)
            >>> spec = {
            ...     "command": "claude",
            ...     "args": ["--print"],
            ...     "protocol": "cli"
            ... }
            >>> cmd = runner.build_command(spec, "prompt.txt")
            >>> print(cmd[0])
            'claude'
        """
        prompt_text = self.load_prompt(prompt_file)
        protocol = agent_spec.get("protocol", "cli")

        # Handle ACP protocol
        if protocol == "acp":
            transport = agent_spec.get("transport", {})
            if transport.get("type", "stdio") != "stdio":
                raise AgentRunnerError(
                    "only stdio ACP transport is supported in the local runner"
                )

            entrypoint = transport.get("command") or agent_spec.get("command")
            args = list(transport.get("args", []))
            prompt_mode = transport.get("prompt_mode", "argv")

            if prompt_mode == "argv":
                return [entrypoint, *args, prompt_text]

            raise AgentRunnerError(
                f"unsupported ACP prompt mode for local runner: {prompt_mode}"
            )

        # Handle CLI protocol
        command = self.apply_runtime_config(
            [agent_spec["command"], *agent_spec.get("args", [])],
            agent_spec
        )

        # Handle resume configuration
        resume = agent_spec.get("resume")
        if run_metadata and run_metadata.get("resume_from") and resume:
            mode = resume.get("mode", "none")
            resume_args = list(resume.get("args", []))

            if mode == "subcommand":
                subcommand = resume.get("subcommand", "resume")
                return [*command, subcommand, *resume_args, prompt_text]

            if mode == "args":
                return [*command, *resume_args, prompt_text]

        # Standard command without resume
        return [*command, prompt_text]

    def execute_command(self, command: list[str]) -> None:
        """
        Execute a command, replacing the current process.

        This is a convenience wrapper around os.execvp that executes
        the given command, replacing the current process image.

        Args:
            command: Command as list of strings

        Raises:
            OSError: If the command cannot be executed

        Note:
            This function does not return - it replaces the current process
        """
        os.execvp(command[0], command)


def build_command(
    agent_spec: dict[str, Any],
    prompt_file: Union[str, Path],
    run_metadata: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Build a command list for running an agent.

    Convenience function that creates a default AgentRunner instance
    and uses it to build the command. This provides backward compatibility
    with the original scripts/agent_runner.py interface.

    Args:
        agent_spec: Agent specification dictionary
        prompt_file: Path to the prompt file
        run_metadata: Optional run metadata

    Returns:
        Complete command as list of strings

    Example:
        >>> from autoflow.agents.runner import build_command
        >>> spec = {"command": "claude", "args": ["--print"]}
        >>> cmd = build_command(spec, "prompt.txt")
        >>> print(cmd[0])
        'claude'
    """
    from autoflow.core.config import load_config

    config = load_config()
    runner = AgentRunner(config)
    return runner.build_command(agent_spec, prompt_file, run_metadata)
