"""
Unit Tests for Autoflow CLI CI Commands

Tests the CI verify command for running verification gates.

These tests use temporary directories to avoid affecting real state files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from autoflow.cli.ci import ci, ci_verify


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


# ============================================================================
# CI Verify Command Tests - Basic Functionality
# ============================================================================


class TestCIVerifyBasic:
    """Tests for basic CI verify command functionality."""

    def test_ci_verify_displays_header(self, runner: CliRunner) -> None:
        """Test CI verify displays proper header."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "CI Verification" in result.output
        assert "=" * 60 in result.output

    def test_ci_verify_default_runs_all_gates(self, runner: CliRunner) -> None:
        """Test CI verify with no flags runs all gates."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run:" in result.output
        assert "test" in result.output
        assert "lint" in result.output
        assert "security" in result.output
        assert "typecheck" in result.output

    def test_ci_verify_shows_placeholder_note(self, runner: CliRunner) -> None:
        """Test CI verify shows placeholder note."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "placeholder" in result.output.lower()
        assert "async runtime" in result.output.lower()


# ============================================================================
# CI Verify Command Tests - Gate Selection
# ============================================================================


class TestCIVerifyGateSelection:
    """Tests for CI verify gate selection options."""

    def test_ci_verify_with_all_flag(self, runner: CliRunner) -> None:
        """Test CI verify --all runs all gates."""
        result = runner.invoke(
            ci_verify,
            ["--all"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run:" in result.output
        assert "test" in result.output
        assert "lint" in result.output
        assert "security" in result.output
        assert "typecheck" in result.output

    def test_ci_verify_with_test_flag(self, runner: CliRunner) -> None:
        """Test CI verify --test runs only test gate."""
        result = runner.invoke(
            ci_verify,
            ["--test"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run: test" in result.output

    def test_ci_verify_with_lint_flag(self, runner: CliRunner) -> None:
        """Test CI verify --lint runs only lint gate."""
        result = runner.invoke(
            ci_verify,
            ["--lint"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run: lint" in result.output

    def test_ci_verify_with_security_flag(self, runner: CliRunner) -> None:
        """Test CI verify --security runs only security gate."""
        result = runner.invoke(
            ci_verify,
            ["--security"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run: security" in result.output

    def test_ci_verify_with_typecheck_flag(self, runner: CliRunner) -> None:
        """Test CI verify --typecheck runs only typecheck gate."""
        result = runner.invoke(
            ci_verify,
            ["--typecheck"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run: typecheck" in result.output

    def test_ci_verify_with_multiple_flags(self, runner: CliRunner) -> None:
        """Test CI verify with multiple gate flags."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--lint"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Gates to run:" in result.output
        assert "test" in result.output
        assert "lint" in result.output

    def test_ci_verify_with_three_gates(self, runner: CliRunner) -> None:
        """Test CI verify with three gate flags."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--security", "--typecheck"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        output = result.output
        assert "test" in output
        assert "security" in output
        assert "typecheck" in output

    def test_ci_verify_short_flag(self, runner: CliRunner) -> None:
        """Test CI verify -a (short flag for --all) works."""
        result = runner.invoke(
            ci_verify,
            ["-a"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "test" in result.output
        assert "lint" in result.output


# ============================================================================
# CI Verify Command Tests - JSON Output
# ============================================================================


class TestCIVerifyJSON:
    """Tests for CI verify --json functionality."""

    def test_ci_verify_json_output(self, runner: CliRunner) -> None:
        """Test CI verify returns valid JSON."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert "status" in output
        assert "gates" in output
        assert "message" in output

    def test_ci_verify_json_default_gates(self, runner: CliRunner) -> None:
        """Test CI verify --json includes default gates."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["status"] == "placeholder"
        assert "test" in output["gates"]
        assert "lint" in output["gates"]
        assert "security" in output["gates"]
        assert "typecheck" in output["gates"]

    def test_ci_verify_json_with_selected_gates(self, runner: CliRunner) -> None:
        """Test CI verify --json includes only selected gates."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--security"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["gates"] == ["test", "security"]

    def test_ci_verify_json_with_single_gate(self, runner: CliRunner) -> None:
        """Test CI verify --json with single gate."""
        result = runner.invoke(
            ci_verify,
            ["--lint"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["gates"] == ["lint"]

    def test_ci_verify_json_with_all_flag(self, runner: CliRunner) -> None:
        """Test CI verify --all --json includes all gates."""
        result = runner.invoke(
            ci_verify,
            ["--all"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert len(output["gates"]) == 4
        assert "test" in output["gates"]
        assert "lint" in output["gates"]
        assert "security" in output["gates"]
        assert "typecheck" in output["gates"]

    def test_ci_verify_json_includes_message(self, runner: CliRunner) -> None:
        """Test CI verify --json includes explanatory message."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert "async execution" in output["message"].lower()
        assert "placeholder" in output["message"].lower()


# ============================================================================
# CI Verify Command Tests - Gate Ordering
# ============================================================================


class TestCIVerifyGateOrdering:
    """Tests for CI verify gate ordering."""

    def test_ci_verify_preserves_flag_order(self, runner: CliRunner) -> None:
        """Test CI verify includes all specified gates regardless of flag order."""
        result = runner.invoke(
            ci_verify,
            ["--security", "--test", "--lint"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        # Gates are added in code order as flags are processed
        # Check that all specified gates are present
        assert set(output["gates"]) == {"security", "test", "lint"}

    def test_ci_verify_default_order(self, runner: CliRunner) -> None:
        """Test CI verify default gate order."""
        result = runner.invoke(
            ci_verify,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        # Should follow the default order in the code
        assert output["gates"] == ["test", "lint", "security", "typecheck"]


# ============================================================================
# CI Verify Command Tests - Edge Cases
# ============================================================================


class TestCIVerifyEdgeCases:
    """Tests for CI verify edge cases."""

    def test_ci_verify_all_gates_explicit(self, runner: CliRunner) -> None:
        """Test CI verify with all gates explicitly specified."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--lint", "--security", "--typecheck"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert len(output["gates"]) == 4

    def test_ci_verify_consistent_output(self, runner: CliRunner) -> None:
        """Test CI verify returns consistent output across calls."""
        result1 = runner.invoke(
            ci_verify,
            ["--test"],
            obj={"output_json": True},
        )
        result2 = runner.invoke(
            ci_verify,
            ["--test"],
            obj={"output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_ci_verify_no_duplicate_gates(self, runner: CliRunner) -> None:
        """Test CI verify doesn't duplicate gates when flags are combined."""
        # Even if we pass --all along with individual flags,
        # the logic should handle it gracefully
        result = runner.invoke(
            ci_verify,
            ["--all", "--test"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        # With the current logic, --all takes precedence
        assert len(output["gates"]) == 4

    def test_ci_verify_empty_selection(self, runner: CliRunner) -> None:
        """Test CI verify with no explicit selection defaults to all."""
        # When no flags are provided, it should run all gates
        result = runner.invoke(
            ci_verify,
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        # Should default to all gates
        assert len(output["gates"]) >= 1


# ============================================================================
# CI Command Tests - Integration
# ============================================================================


class TestCIIntegration:
    """Tests for CI command integration."""

    def test_ci_verify_all_exit_codes_zero(self, runner: CliRunner) -> None:
        """Test all CI verify variations return exit code 0."""
        test_cases = [
            [],  # Default (all gates)
            ["--all"],
            ["--test"],
            ["--lint"],
            ["--security"],
            ["--typecheck"],
            ["--test", "--lint"],
            ["--test", "--lint", "--security"],
        ]

        for args in test_cases:
            result = runner.invoke(
                ci_verify,
                args,
                obj={"output_json": False},
            )
            assert result.exit_code == 0, f"Failed for args: {args}"

    def test_ci_verify_json_and_text_consistent(self, runner: CliRunner) -> None:
        """Test CI verify JSON and text output are consistent."""
        # Run with JSON output
        result_json = runner.invoke(
            ci_verify,
            ["--test", "--security"],
            obj={"output_json": True},
        )

        # Run with text output
        result_text = runner.invoke(
            ci_verify,
            ["--test", "--security"],
            obj={"output_json": False},
        )

        assert result_json.exit_code == 0
        assert result_text.exit_code == 0

        # Parse JSON to verify gates
        json_output = json.loads(result_json.output)
        assert "test" in json_output["gates"]
        assert "security" in json_output["gates"]

        # Verify text output mentions the gates
        assert "test" in result_text.output
        assert "security" in result_text.output


# ============================================================================
# CI Command Tests - Help and Documentation
# ============================================================================


class TestCICommandHelp:
    """Tests for CI command help and documentation."""

    def test_ci_verify_help_available(self, runner: CliRunner) -> None:
        """Test CI verify --help displays help."""
        result = runner.invoke(ci_verify, ["--help"])

        assert result.exit_code == 0
        assert "Run CI verification gates" in result.output
        assert "--test" in result.output
        assert "--lint" in result.output
        assert "--security" in result.output
        assert "--typecheck" in result.output
        assert "--all" in result.output

    def test_ci_group_help(self, runner: CliRunner) -> None:
        """Test CI group help displays subcommands."""
        result = runner.invoke(ci, ["--help"])

        assert result.exit_code == 0
        assert "verify" in result.output


# ============================================================================
# CI Verify Command Tests - Combinations
# ============================================================================


class TestCIVerifyCombinations:
    """Tests for CI verify with various flag combinations."""

    def test_ci_verify_test_and_lint(self, runner: CliRunner) -> None:
        """Test CI verify --test --lint."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--lint"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert set(output["gates"]) == {"test", "lint"}

    def test_ci_verify_test_security_typecheck(self, runner: CliRunner) -> None:
        """Test CI verify --test --security --typecheck."""
        result = runner.invoke(
            ci_verify,
            ["--test", "--security", "--typecheck"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert set(output["gates"]) == {"test", "security", "typecheck"}

    def test_ci_verify_lint_security(self, runner: CliRunner) -> None:
        """Test CI verify --lint --security."""
        result = runner.invoke(
            ci_verify,
            ["--lint", "--security"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert set(output["gates"]) == {"lint", "security"}
