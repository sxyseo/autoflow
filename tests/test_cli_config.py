"""
Unit Tests for Autoflow CLI Config Commands

Tests the config command functionality including showing configuration
in different formats (text and JSON).

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.config import config as config_cmd
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
# Config Command Tests - Basic Functionality
# ============================================================================


class TestConfigBasic:
    """Tests for basic config command functionality."""

    def test_config_show_displays_header(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show displays proper header."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Current Configuration" in result.output
        assert "=" * 60 in result.output

    def test_config_show_shows_state_dir(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows state directory."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "State Directory:" in result.output

    def test_config_show_shows_openclaw_gateway(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows OpenClaw gateway."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "OpenClaw Gateway:" in result.output

    def test_config_show_shows_openclaw_config(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows OpenClaw config path."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "OpenClaw Config:" in result.output

    def test_config_show_shows_scheduler_status(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows scheduler enabled status."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Scheduler Enabled:" in result.output

    def test_config_show_shows_ci_require_all(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows CI require all setting."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "CI Require All:" in result.output


# ============================================================================
# Config Command Tests - Agent Configuration
# ============================================================================


class TestConfigAgents:
    """Tests for config command agent configuration display."""

    def test_config_show_shows_agents_header(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows agents header."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "Agents:" in result.output

    def test_config_show_shows_claude_code_agent(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows claude-code agent command."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code:" in result.output

    def test_config_show_shows_codex_agent(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show shows codex agent command."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0
        assert "codex:" in result.output


# ============================================================================
# Config Command Tests - JSON Output
# ============================================================================


class TestConfigJSON:
    """Tests for config command JSON output."""

    def test_config_show_json_output(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show returns valid JSON."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        # Parse JSON
        import json

        output = json.loads(result.output)
        assert isinstance(output, dict)

    def test_config_show_json_has_state_dir(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show JSON includes state_dir."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "state_dir" in output

    def test_config_show_json_has_openclaw(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show JSON includes openclaw section."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "openclaw" in output
        assert "gateway_url" in output["openclaw"]
        assert "config_path" in output["openclaw"]

    def test_config_show_json_has_scheduler(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show JSON includes scheduler section."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "scheduler" in output
        assert "enabled" in output["scheduler"]

    def test_config_show_json_has_ci(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show JSON includes ci section."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "ci" in output
        assert "require_all" in output["ci"]

    def test_config_show_json_has_agents(self, runner: CliRunner, sample_config: Config) -> None:
        """Test config show JSON includes agents section."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "agents" in output
        assert "claude_code" in output["agents"]
        assert "codex" in output["agents"]


# ============================================================================
# Config Command Tests - Error Handling
# ============================================================================


class TestConfigErrors:
    """Tests for config command error handling."""

    def test_config_show_without_config(self, runner: CliRunner) -> None:
        """Test config show fails gracefully without config."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": None, "output_json": False},
        )

        assert result.exit_code == 1
        assert "Error: Configuration not loaded" in result.output
        assert result.output.count("Configuration not loaded") > 0

    def test_config_show_json_without_config(self, runner: CliRunner) -> None:
        """Test config show JSON fails gracefully without config."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": None, "output_json": True},
        )

        assert result.exit_code == 1
        assert "Error: Configuration not loaded" in result.output


# ============================================================================
# Config Command Tests - Integration
# ============================================================================


class TestConfigIntegration:
    """Tests for config command integration with Config model."""

    def test_config_show_matches_config_model(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test config show output matches Config model."""
        cfg = Config(state_dir=str(temp_state_dir))

        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": cfg, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["state_dir"] == cfg.state_dir
        assert output["openclaw"]["gateway_url"] == cfg.openclaw.gateway_url
        assert output["openclaw"]["config_path"] == cfg.openclaw.config_path
        assert output["scheduler"]["enabled"] == cfg.scheduler.enabled
        assert output["ci"]["require_all"] == cfg.ci.require_all

    def test_config_show_with_custom_state_dir(
        self, runner: CliRunner, temp_state_dir: Path
    ) -> None:
        """Test config show with custom state directory."""
        custom_dir = temp_state_dir / "custom_autoflow"
        custom_dir.mkdir()
        cfg = Config(state_dir=str(custom_dir))

        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": cfg, "output_json": False},
        )

        assert result.exit_code == 0
        assert str(custom_dir) in result.output

    def test_config_show_agents_commands(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test config show displays agent commands correctly."""
        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result.exit_code == 0

        # Check for agent command format
        assert "claude-code:" in result.output
        assert "codex:" in result.output


# ============================================================================
# Config Command Tests - Edge Cases
# ============================================================================


class TestConfigEdgeCases:
    """Tests for config command edge cases."""

    def test_config_show_consistency(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test config show output is consistent across calls."""
        result1 = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )
        result2 = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": False},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_config_show_json_consistency(
        self, runner: CliRunner, sample_config: Config
    ) -> None:
        """Test config show JSON output is consistent."""
        result1 = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )
        result2 = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": sample_config, "output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        import json

        output1 = json.loads(result1.output)
        output2 = json.loads(result2.output)
        assert output1 == output2

    def test_config_show_with_default_config(self, runner: CliRunner) -> None:
        """Test config show works with default config."""
        cfg = Config()  # Use all defaults

        result = runner.invoke(
            config_cmd,
            ["show"],
            obj={"config": cfg, "output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "state_dir" in output
        assert "agents" in output
