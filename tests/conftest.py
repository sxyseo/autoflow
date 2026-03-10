"""
Pytest Configuration for Autoflow Tests

Provides fixtures and configuration for testing the autoflow package.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
from click.testing import CliRunner

import pytest

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Async Support
# ============================================================================


@pytest.fixture
def event_loop_policy():
    """Use default event loop policy for async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


# ============================================================================
# CLI Testing Fixtures
# ============================================================================


@pytest.fixture
def cli_runner():
    """
    Create a Click CLI runner for testing CLI commands.

    This provides a CliRunner instance that can be used to invoke CLI commands
    in tests and capture their output, exit codes, and exceptions.

    Example:
        def test_init_command(cli_runner):
            result = cli_runner.invoke(main, ["init"])
            assert result.exit_code == 0
    """
    return CliRunner(mix_stderr=False)


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """
    Create a temporary workspace directory for testing.

    This fixture creates a temporary directory that can be used as a workspace
    for CLI tests. The directory is automatically cleaned up after the test.

    Example:
        def test_workspace_init(temp_workspace):
            config_path = temp_workspace / "config.json5"
            # Use config_path for testing
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


@pytest.fixture
def sample_config(temp_workspace: Path) -> dict[str, Any]:
    """
    Provide a sample configuration dictionary for testing.

    This fixture returns a dictionary with typical configuration values
    that can be used to create config files or mock configuration objects.

    Example:
        def test_config_loading(sample_config):
            config_path = temp_workspace / "config.json5"
            config_path.write_text(json.dumps(sample_config))
    """
    return {
        "agents": {
            "claude-code": {
                "command": "claude",
                "args": [],
                "approval_policy": "suggest",
            },
        },
        "scheduler": {
            "enabled": True,
            "check_interval_seconds": 60,
        },
        "skills": {
            "enabled": True,
            "auto_load": True,
        },
        "ci": {
            "gates": [
                "tests_pass",
                "lint_pass",
                "coverage_adequate",
            ],
        },
    }


@pytest.fixture
def sample_config_file(temp_workspace: Path, sample_config: dict[str, Any]) -> Path:
    """
    Create a sample configuration file for testing.

    This fixture creates an actual config file with sample content in the
    temporary workspace directory.

    Example:
        def test_load_config(sample_config_file):
            config = load_config(sample_config_file)
            assert config is not None
    """
    config_file = temp_workspace / "config.json5"
    config_file.write_text(json.dumps(sample_config, indent=2))
    return config_file


@pytest.fixture
def mock_state_dir(tmp_path: Path) -> Path:
    """
    Create a mock state directory for testing.

    This fixture creates a temporary directory structure that mimics the
    Autoflow state directory, including subdirectories for tasks, memory,
    and other state data.

    Example:
        def test_state_persistence(mock_state_dir):
            state_file = mock_state_dir / "state.json"
            # Test state operations
    """
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()

    # Create common state subdirectories
    (state_dir / "tasks").mkdir()
    (state_dir / "memory").mkdir()
    (state_dir / "sessions").mkdir()
    (state_dir / "cache").mkdir()

    return state_dir


@pytest.fixture
def cli_context() -> click.Context:
    """
    Create a Click context with common settings for testing.

    This fixture provides a Click Context object pre-configured with
    typical settings that can be used to invoke CLI commands.

    Example:
        def test_command_with_context(cli_context):
            result = some_command.callback(cli_context)
    """
    from autoflow.cli.main import main

    ctx = click.Context(main)
    ctx.obj = {
        "config": None,
        "state_dir": None,
        "verbose": 0,
        "json": False,
    }
    return ctx


@pytest.fixture
def mock_config() -> MagicMock:
    """
    Create a mock configuration object for testing.

    This fixture provides a MagicMock object that can be used as a
    configuration object in tests, avoiding the need to load actual
    configuration files.

    Example:
        def test_with_mock_config(mock_config):
            mock_config.agents = {"claude-code": {...}}
            # Test with mock config
    """
    config = MagicMock()
    config.agents = {}
    config.scheduler = MagicMock()
    config.scheduler.enabled = False
    config.scheduler.check_interval_seconds = 60
    config.skills = MagicMock()
    config.skills.enabled = True
    config.skills.auto_load = True
    config.ci = MagicMock()
    config.ci.gates = []
    return config


@pytest.fixture
def isolated_cli_runner(cli_runner: CliRunner, temp_workspace: Path, mock_state_dir: Path):
    """
    Create a CLI runner isolated from the user's actual environment.

    This fixture provides a CliRunner that operates in an isolated environment
    with temporary workspace and state directories, ensuring tests don't
    affect the user's actual Autoflow installation.

    Example:
        def test_isolated_command(isolated_cli_runner):
            result = isolated_cli_runner.invoke(main, ["status"])
            assert result.exit_code == 0
    """
    def runner_isolated(cmd, args=None, **kwargs):
        # Set environment variables for isolation
        env = {
            "AUTOFLOW_CONFIG": str(temp_workspace / "config.json5"),
            "AUTOFLOW_STATE_DIR": str(mock_state_dir),
            "HOME": str(temp_workspace),
        }
        return cli_runner.invoke(
            cmd,
            args=args,
            env=env,
            catch_exceptions=False,
            **kwargs
        )

    return runner_isolated


@pytest.fixture
def sample_task_data() -> dict[str, Any]:
    """
    Provide sample task data for testing task-related commands.

    This fixture returns a dictionary with typical task structure that
    can be used for testing task creation, listing, and management.

    Example:
        def test_task_creation(sample_task_data):
            task = Task(**sample_task_data)
            assert task.status == "pending"
    """
    return {
        "id": "test-task-001",
        "title": "Test Task",
        "description": "A test task for unit testing",
        "status": "pending",
        "priority": "medium",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_skill_content() -> str:
    """
    Provide sample skill file content for testing skill commands.

    This fixture returns a string containing valid skill file content
    with YAML frontmatter and markdown body.

    Example:
        def test_skill_loading(temp_workspace, sample_skill_content):
            skill_file = temp_workspace / "SKILL.md"
            skill_file.write_text(sample_skill_content)
    """
    return '''---
name: TEST_SKILL
description: A test skill for unit testing
version: "1.0.0"
triggers:
  - test_trigger
  - another_trigger
inputs:
  - input1
  - input2
outputs:
  - output1
agents:
  - claude-code
  - codex
enabled: true
---

## Role

This is a test skill for unit testing.

## Workflow

1. Step one
2. Step two
3. Step three
'''


# ============================================================================
# Helper Functions
# ============================================================================


def create_test_file(directory: Path, filename: str, content: str) -> Path:
    """
    Helper function to create test files in a directory.

    Args:
        directory: The directory to create the file in
        filename: The name of the file to create
        content: The content to write to the file

    Returns:
        Path to the created file
    """
    file_path = directory / filename
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return file_path
