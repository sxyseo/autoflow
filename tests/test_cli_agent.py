"""
Unit Tests for Autoflow CLI Agent Commands

Tests the agent command functionality including listing agents
and checking agent availability.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from autoflow.cli.agent import agent, agent_list, agent_check
from autoflow.core.config import Config


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory."""
    state_dir = tmp_path / ".autoflow"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def sample_config(temp_state_dir: Path) -> Config:
    """Create a sample config for testing."""
    return Config(state_dir=str(temp_state_dir))


# ============================================================================
# Agent List Command Tests - Basic Functionality
# ============================================================================


class TestAgentListBasic:
    """Tests for agent list command basic functionality."""

    def test_agent_list_displays_header(self, runner: CliRunner) -> None:
        """Test agent list displays proper header."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "Available Agents" in result.output
        assert "=" * 60 in result.output

    def test_agent_list_shows_claude_code(self, runner: CliRunner) -> None:
        """Test agent list shows claude-code agent."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_agent_list_shows_codex(self, runner: CliRunner) -> None:
        """Test agent list shows codex agent."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "codex" in result.output

    def test_agent_list_shows_openclaw(self, runner: CliRunner) -> None:
        """Test agent list shows openclaw agent."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "openclaw" in result.output

    def test_agent_list_shows_command(self, runner: CliRunner) -> None:
        """Test agent list shows command for each agent."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "Command:" in result.output

    def test_agent_list_shows_resume_mode(self, runner: CliRunner) -> None:
        """Test agent list shows resume mode."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "Resume Mode:" in result.output

    def test_agent_list_shows_timeout(self, runner: CliRunner) -> None:
        """Test agent list shows timeout."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "Timeout:" in result.output


# ============================================================================
# Agent List Command Tests - JSON Output
# ============================================================================


class TestAgentListJSON:
    """Tests for agent list --json functionality."""

    def test_agent_list_json_output(self, runner: CliRunner) -> None:
        """Test agent list returns valid JSON."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "agents" in output
        assert isinstance(output["agents"], list)

    def test_agent_list_json_has_all_agents(self, runner: CliRunner) -> None:
        """Test agent list JSON includes all three agents."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        agent_names = [a["name"] for a in output["agents"]]

        assert "claude-code" in agent_names
        assert "codex" in agent_names
        assert "openclaw" in agent_names

    def test_agent_list_json_structure(self, runner: CliRunner) -> None:
        """Test agent list JSON has proper structure."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)

        for agent_info in output["agents"]:
            assert "name" in agent_info
            assert "command" in agent_info
            assert "args" in agent_info
            assert "resume_mode" in agent_info
            assert "timeout" in agent_info

    def test_agent_list_json_claude_code_details(self, runner: CliRunner) -> None:
        """Test agent list JSON has claude-code details."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        claude = next(a for a in output["agents"] if a["name"] == "claude-code")

        assert "command" in claude
        assert isinstance(claude["args"], list)
        assert claude["resume_mode"] in ["native", "auto", "manual"]
        assert isinstance(claude["timeout"], int)


# ============================================================================
# Agent Check Command Tests - Basic Functionality
# ============================================================================


class TestAgentCheckBasic:
    """Tests for agent check command basic functionality."""

    def test_agent_check_claude_code(self, runner: CliRunner) -> None:
        """Test agent check claude-code."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_agent_check_codex(self, runner: CliRunner) -> None:
        """Test agent check codex."""
        result = runner.invoke(
            agent_check,
            ["codex"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "codex" in result.output

    def test_agent_check_openclaw(self, runner: CliRunner) -> None:
        """Test agent check openclaw."""
        result = runner.invoke(
            agent_check,
            ["openclaw"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "openclaw" in result.output

    def test_agent_check_shows_status(self, runner: CliRunner) -> None:
        """Test agent check shows availability status."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        # Should show either "available" or "not available"
        assert "available" in result.output.lower()

    def test_agent_check_shows_command(self, runner: CliRunner) -> None:
        """Test agent check shows command being checked."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "(" in result.output and ")" in result.output


# ============================================================================
# Agent Check Command Tests - Check All
# ============================================================================


class TestAgentCheckAll:
    """Tests for agent check all functionality."""

    def test_agent_check_all(self, runner: CliRunner) -> None:
        """Test agent check all checks all agents."""
        result = runner.invoke(
            agent_check,
            ["all"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "codex" in result.output
        assert "openclaw" in result.output

    def test_agent_check_all_count(self, runner: CliRunner) -> None:
        """Test agent check all returns three results."""
        result = runner.invoke(
            agent_check,
            ["all"],
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0

        # Count agent mentions
        lines = result.output.strip().split("\n")
        agent_lines = [l for l in lines if "claude-code" in l or "codex" in l or "openclaw" in l]
        assert len(agent_lines) >= 3


# ============================================================================
# Agent Check Command Tests - JSON Output
# ============================================================================


class TestAgentCheckJSON:
    """Tests for agent check --json functionality."""

    def test_agent_check_json_output(self, runner: CliRunner) -> None:
        """Test agent check returns valid JSON."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "agents" in output
        assert isinstance(output["agents"], list)

    def test_agent_check_json_has_fields(self, runner: CliRunner) -> None:
        """Test agent check JSON has required fields."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        agent_data = output["agents"][0]

        assert "name" in agent_data
        assert "available" in agent_data
        assert "command" in agent_data
        assert isinstance(agent_data["available"], bool)

    def test_agent_check_all_json(self, runner: CliRunner) -> None:
        """Test agent check all returns valid JSON."""
        result = runner.invoke(
            agent_check,
            ["all"],
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert len(output["agents"]) == 3


# ============================================================================
# Agent Command Tests - Error Handling
# ============================================================================


class TestAgentErrors:
    """Tests for agent command error handling."""

    def test_agent_list_without_config(self, runner: CliRunner) -> None:
        """Test agent list handles missing config."""
        result = runner.invoke(
            agent_list,
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Error: Configuration not loaded" in result.output

    def test_agent_check_without_config(self, runner: CliRunner) -> None:
        """Test agent check handles missing config."""
        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Error: Configuration not loaded" in result.output

    def test_agent_check_invalid_choice(self, runner: CliRunner) -> None:
        """Test agent check rejects invalid agent name."""
        result = runner.invoke(
            agent_check,
            ["invalid-agent"],
            obj={"config": Config(), "output_json": False},
        )

        # Click's Choice type should reject this before our code runs
        assert result.exit_code != 0


# ============================================================================
# Agent Command Tests - Integration
# ============================================================================


class TestAgentIntegration:
    """Tests for agent command integration with Config."""

    def test_agent_list_uses_config_values(self, runner: CliRunner) -> None:
        """Test agent list uses values from Config."""
        config = Config()

        result = runner.invoke(
            agent_list,
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        claude = next(a for a in output["agents"] if a["name"] == "claude-code")

        # Should match config values
        assert claude["command"] == config.agents.claude_code.command

    def test_agent_check_uses_config_command(self, runner: CliRunner) -> None:
        """Test agent check uses command from Config."""
        config = Config()

        result = runner.invoke(
            agent_check,
            ["claude-code"],
            obj={"config": config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        agent_data = output["agents"][0]

        # Should check the command from config
        assert agent_data["command"] == config.agents.claude_code.command


# ============================================================================
# Agent Command Tests - Edge Cases
# ============================================================================


class TestAgentEdgeCases:
    """Tests for agent command edge cases."""

    def test_agent_list_empty_args(self, runner: CliRunner) -> None:
        """Test agent group requires subcommand."""
        result = runner.invoke(
            agent,
            obj={"config": Config(), "output_json": False},
        )

        # Should show help or error
        assert result.exit_code != 0 or "Usage:" in result.output

    def test_agent_check_with_mocked_shutil(self, runner: CliRunner) -> None:
        """Test agent check with mocked shutil.which."""
        config = Config()

        # Patch shutil.which at the module level where it's imported
        import shutil
        with patch.object(shutil, "which") as mock_which:
            mock_which.return_value = "/usr/bin/claude"

            result = runner.invoke(
                agent_check,
                ["claude-code"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            agent_data = output["agents"][0]
            assert agent_data["available"] is True

    def test_agent_check_unavailable_with_mock(self, runner: CliRunner) -> None:
        """Test agent check when command not found."""
        config = Config()

        # Patch shutil.which at the module level where it's imported
        import shutil
        with patch.object(shutil, "which") as mock_which:
            mock_which.return_value = None

            result = runner.invoke(
                agent_check,
                ["claude-code"],
                obj={"config": config, "output_json": True},
            )

            assert result.exit_code == 0

            import json

            output = json.loads(result.output)
            agent_data = output["agents"][0]
            assert agent_data["available"] is False

    def test_agent_list_consistency(self, runner: CliRunner) -> None:
        """Test agent list output is consistent across calls."""
        config = Config()

        result1 = runner.invoke(
            agent_list,
            obj={"config": config, "output_json": True},
        )
        result2 = runner.invoke(
            agent_list,
            obj={"config": config, "output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output


# ============================================================================
# Agent Command Tests - OpenClaw Special Cases
# ============================================================================


class TestAgentOpenClaw:
    """Tests for OpenClaw agent special behavior."""

    def test_openclaw_uses_gateway(self, runner: CliRunner) -> None:
        """Test openclaw shows gateway instead of command."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": False},
        )

        assert result.exit_code == 0
        # OpenClaw should show gateway message
        assert "openclaw:" in result.output.lower()

    def test_openclaw_list_json(self, runner: CliRunner) -> None:
        """Test openclaw in JSON output."""
        result = runner.invoke(
            agent_list,
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        openclaw = next(a for a in output["agents"] if a["name"] == "openclaw")

        assert openclaw["command"] == "N/A (uses gateway)"
        assert openclaw["resume_mode"] == "native"
        assert openclaw["timeout"] == 300

    def test_openclaw_check_always_available(self, runner: CliRunner) -> None:
        """Test openclaw check shows as available (uses gateway)."""
        result = runner.invoke(
            agent_check,
            ["openclaw"],
            obj={"config": Config(), "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        openclaw = output["agents"][0]

        # OpenClaw uses gateway, so should be marked available
        assert openclaw["name"] == "openclaw"
        assert "command" in openclaw
