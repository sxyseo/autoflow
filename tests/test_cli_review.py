"""
Unit Tests for Autoflow CLI Review Commands

Tests the review command functionality including running multi-agent
code review with different agents and strategies.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.review import review


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


# ============================================================================
# Review Command Tests - Basic Functionality
# ============================================================================


class TestReviewBasic:
    """Tests for basic review command functionality."""

    def test_review_run_displays_header(self, runner: CliRunner) -> None:
        """Test review run displays proper header."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Code Review" in result.output
        assert "=" * 60 in result.output

    def test_review_run_shows_default_agents(self, runner: CliRunner) -> None:
        """Test review run shows default agents."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "codex" in result.output

    def test_review_run_shows_default_strategy(self, runner: CliRunner) -> None:
        """Test review run shows default strategy."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: majority" in result.output

    def test_review_run_shows_placeholder_message(self, runner: CliRunner) -> None:
        """Test review run shows placeholder message."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "placeholder" in result.output.lower()
        assert "async runtime" in result.output.lower()


# ============================================================================
# Review Command Tests - Agent Options
# ============================================================================


class TestReviewAgents:
    """Tests for review command agent options."""

    def test_review_run_with_single_agent(self, runner: CliRunner) -> None:
        """Test review run with single agent."""
        result = runner.invoke(
            review,
            ["run", "--agent", "claude-code"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output

    def test_review_run_with_multiple_agents(self, runner: CliRunner) -> None:
        """Test review run with multiple agents."""
        result = runner.invoke(
            review,
            ["run", "--agent", "claude-code", "--agent", "openclaw"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "openclaw" in result.output

    def test_review_run_with_all_agents(self, runner: CliRunner) -> None:
        """Test review run with all available agents."""
        result = runner.invoke(
            review,
            [
                "run",
                "--agent", "claude-code",
                "--agent", "codex",
                "--agent", "openclaw",
            ],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "codex" in result.output
        assert "openclaw" in result.output

    def test_review_run_agent_short_flag(self, runner: CliRunner) -> None:
        """Test review run with -a short flag."""
        result = runner.invoke(
            review,
            ["run", "-a", "codex"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "codex" in result.output

    def test_review_run_invalid_agent(self, runner: CliRunner) -> None:
        """Test review run rejects invalid agent."""
        result = runner.invoke(
            review,
            ["run", "--agent", "invalid-agent"],
            obj={"output_json": False},
        )

        # Should fail with invalid choice error
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()


# ============================================================================
# Review Command Tests - Strategy Options
# ============================================================================


class TestReviewStrategy:
    """Tests for review command strategy options."""

    def test_review_run_strategy_consensus(self, runner: CliRunner) -> None:
        """Test review run with consensus strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "consensus"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: consensus" in result.output

    def test_review_run_strategy_majority(self, runner: CliRunner) -> None:
        """Test review run with majority strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "majority"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: majority" in result.output

    def test_review_run_strategy_single(self, runner: CliRunner) -> None:
        """Test review run with single strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "single"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: single" in result.output

    def test_review_run_strategy_weighted(self, runner: CliRunner) -> None:
        """Test review run with weighted strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "weighted"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: weighted" in result.output

    def test_review_run_strategy_short_flag(self, runner: CliRunner) -> None:
        """Test review run with -s short flag."""
        result = runner.invoke(
            review,
            ["run", "-s", "consensus"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Strategy: consensus" in result.output

    def test_review_run_invalid_strategy(self, runner: CliRunner) -> None:
        """Test review run rejects invalid strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "invalid-strategy"],
            obj={"output_json": False},
        )

        # Should fail with invalid choice error
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()


# ============================================================================
# Review Command Tests - Combined Options
# ============================================================================


class TestReviewCombinedOptions:
    """Tests for review command with combined options."""

    def test_review_run_agents_and_strategy(self, runner: CliRunner) -> None:
        """Test review run with both agents and strategy options."""
        result = runner.invoke(
            review,
            [
                "run",
                "--agent", "claude-code",
                "--agent", "codex",
                "--strategy", "consensus",
            ],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code" in result.output
        assert "codex" in result.output
        assert "Strategy: consensus" in result.output

    def test_review_run_short_flags(self, runner: CliRunner) -> None:
        """Test review run with short flags."""
        result = runner.invoke(
            review,
            ["run", "-a", "openclaw", "-s", "weighted"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "openclaw" in result.output
        assert "Strategy: weighted" in result.output

    def test_review_run_multiple_agents_with_strategy(self, runner: CliRunner) -> None:
        """Test review run with multiple agents and custom strategy."""
        result = runner.invoke(
            review,
            [
                "run",
                "-a", "claude-code",
                "-a", "codex",
                "-a", "openclaw",
                "-s", "single",
            ],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "claude-code, codex, openclaw" in result.output
        assert "Strategy: single" in result.output


# ============================================================================
# Review Command Tests - JSON Output
# ============================================================================


class TestReviewJSON:
    """Tests for review command JSON output."""

    def test_review_run_json_output(self, runner: CliRunner) -> None:
        """Test review run returns valid JSON."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        # Parse JSON
        import json

        output = json.loads(result.output)
        assert "status" in output
        assert "agents" in output
        assert "strategy" in output
        assert "message" in output

    def test_review_run_json_with_custom_agents(self, runner: CliRunner) -> None:
        """Test review run JSON includes custom agents."""
        result = runner.invoke(
            review,
            ["run", "--agent", "openclaw"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["agents"] == ["openclaw"]

    def test_review_run_json_with_custom_strategy(self, runner: CliRunner) -> None:
        """Test review run JSON includes custom strategy."""
        result = runner.invoke(
            review,
            ["run", "--strategy", "consensus"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["strategy"] == "consensus"

    def test_review_run_json_with_multiple_agents(self, runner: CliRunner) -> None:
        """Test review run JSON includes all agents."""
        result = runner.invoke(
            review,
            [
                "run",
                "--agent", "claude-code",
                "--agent", "codex",
                "--agent", "openclaw",
            ],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert len(output["agents"]) == 3
        assert "claude-code" in output["agents"]
        assert "codex" in output["agents"]
        assert "openclaw" in output["agents"]

    def test_review_run_json_placeholder_status(self, runner: CliRunner) -> None:
        """Test review run JSON has placeholder status."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["status"] == "placeholder"
        assert "async" in output["message"].lower()


# ============================================================================
# Review Command Tests - Edge Cases
# ============================================================================


class TestReviewEdgeCases:
    """Tests for review command edge cases."""

    def test_review_run_no_options(self, runner: CliRunner) -> None:
        """Test review run with no options uses defaults."""
        result = runner.invoke(
            review,
            ["run"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # Should have default agents
        assert "Agents:" in result.output

    def test_review_run_consistency(self, runner: CliRunner) -> None:
        """Test review run output is consistent across calls."""
        result1 = runner.invoke(
            review,
            ["run", "--agent", "claude-code", "--strategy", "consensus"],
            obj={"output_json": False},
        )
        result2 = runner.invoke(
            review,
            ["run", "--agent", "claude-code", "--strategy", "consensus"],
            obj={"output_json": False},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_review_run_json_consistency(self, runner: CliRunner) -> None:
        """Test review run JSON output is consistent."""
        result1 = runner.invoke(
            review,
            ["run"],
            obj={"output_json": True},
        )
        result2 = runner.invoke(
            review,
            ["run"],
            obj={"output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        import json

        output1 = json.loads(result1.output)
        output2 = json.loads(result2.output)
        assert output1 == output2
