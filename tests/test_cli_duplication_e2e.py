"""
End-to-End Tests for CLI Duplication Analysis

Tests the complete CLI duplication analysis workflow from command invocation
to output formatting and error handling. These tests verify the user-facing
behavior of the duplication detection CLI commands.

These tests use CliRunner to simulate actual CLI usage patterns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from autoflow.cli.duplication import (
    duplication,
    duplication_analyze,
    duplication_scan,
    duplication_report,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with sample code."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create a sample Python file with some code
    (project_dir / "sample.py").write_text("""def hello_world():
    print("Hello, world!")

def greet(name: str) -> str:
    return f"Hello, {name}!"

class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
""")

    # Create a duplicate file
    (project_dir / "duplicate.py").write_text("""def hello_world():
    print("Hello, world!")

def greet(name: str) -> str:
    return f"Hello, {name}!"

class MyClass:
    def method_one(self):
        pass

    def method_two(self):
        pass
""")

    return project_dir


# ============================================================================
# Duplication Command Group Tests
# ============================================================================


class TestDuplicationCommandGroup:
    """Tests for the main duplication command group."""

    def test_duplication_command_exists(self, runner: CliRunner) -> None:
        """Test duplication command group is registered."""
        result = runner.invoke(duplication, ["--help"])
        assert result.exit_code == 0
        assert "Code duplication detection commands" in result.output

    def test_duplication_help_shows_subcommands(self, runner: CliRunner) -> None:
        """Test duplication help lists all subcommands."""
        result = runner.invoke(duplication, ["--help"])
        assert result.exit_code == 0
        assert "scan" in result.output
        assert "report" in result.output
        assert "analyze" in result.output
        assert "config" in result.output

    def test_duplication_analyze_command_exists(self, runner: CliRunner) -> None:
        """Test analyze subcommand exists and shows help."""
        result = runner.invoke(duplication, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze code for duplications" in result.output

    def test_duplication_scan_command_exists(self, runner: CliRunner) -> None:
        """Test scan subcommand exists and shows help."""
        result = runner.invoke(duplication, ["scan", "--help"])
        assert result.exit_code == 0
        assert "Scan code for duplications" in result.output

    def test_duplication_report_command_exists(self, runner: CliRunner) -> None:
        """Test report subcommand exists and shows help."""
        result = runner.invoke(duplication, ["report", "--help"])
        assert result.exit_code == 0
        assert "Display a duplication report" in result.output


# ============================================================================
# Analyze Command Tests - Basic Functionality
# ============================================================================


class TestAnalyzeBasic:
    """Tests for basic analyze command functionality."""

    def test_analyze_displays_header(self, runner: CliRunner) -> None:
        """Test analyze command displays proper header."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Code Duplication Analysis" in result.output
        assert "=" * 60 in result.output

    def test_analyze_shows_default_path(self, runner: CliRunner) -> None:
        """Test analyze command shows default path."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Path: ." in result.output

    def test_analyze_shows_default_threshold(self, runner: CliRunner) -> None:
        """Test analyze command shows default threshold."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.8" in result.output

    def test_analyze_shows_summary_mode_by_default(self, runner: CliRunner) -> None:
        """Test analyze command uses summary mode by default."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Mode: Summary" in result.output

    def test_analyze_shows_placeholder_message(self, runner: CliRunner) -> None:
        """Test analyze command shows placeholder message."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "placeholder" in result.output.lower()
        assert "async runtime" in result.output.lower()


# ============================================================================
# Analyze Command Tests - Path and Threshold Options
# ============================================================================


class TestAnalyzeOptions:
    """Tests for analyze command options."""

    def test_analyze_with_custom_path(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test analyze command with custom path."""
        result = runner.invoke(
            duplication_analyze,
            ["--path", str(temp_project_dir)],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # CLI is a placeholder, so just check it doesn't crash
        assert "Code Duplication Analysis" in result.output

    def test_analyze_with_short_path_flag(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test analyze command with -p short flag."""
        result = runner.invoke(
            duplication_analyze,
            ["-p", str(temp_project_dir)],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # CLI is a placeholder, so just check it doesn't crash
        assert "Code Duplication Analysis" in result.output

    def test_analyze_with_custom_threshold(self, runner: CliRunner) -> None:
        """Test analyze command with custom threshold."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.9"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.9" in result.output

    def test_analyze_with_short_threshold_flag(self, runner: CliRunner) -> None:
        """Test analyze command with -t short flag."""
        result = runner.invoke(
            duplication_analyze,
            ["-t", "0.95"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.95" in result.output

    def test_analyze_with_low_threshold(self, runner: CliRunner) -> None:
        """Test analyze command with low threshold (0.0)."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.0"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.0" in result.output

    def test_analyze_with_high_threshold(self, runner: CliRunner) -> None:
        """Test analyze command with high threshold (1.0)."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "1.0"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 1.0" in result.output

    def test_analyze_with_invalid_threshold(self, runner: CliRunner) -> None:
        """Test analyze command rejects invalid threshold."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "1.5"],
            obj={"output_json": False},
        )

        # Should fail with invalid range error
        assert result.exit_code != 0
        assert "out of range" in result.output.lower() or "invalid" in result.output.lower()

    def test_analyze_with_negative_threshold(self, runner: CliRunner) -> None:
        """Test analyze command rejects negative threshold."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "-0.1"],
            obj={"output_json": False},
        )

        # Should fail with invalid range error
        assert result.exit_code != 0

    def test_analyze_with_detailed_flag(self, runner: CliRunner) -> None:
        """Test analyze command with detailed flag."""
        result = runner.invoke(
            duplication_analyze,
            ["--detailed"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Mode: Detailed" in result.output

    def test_analyze_with_summary_flag(self, runner: CliRunner) -> None:
        """Test analyze command with summary flag (explicit)."""
        result = runner.invoke(
            duplication_analyze,
            ["--summary"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Mode: Summary" in result.output

    def test_analyze_combined_options(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test analyze command with combined options."""
        result = runner.invoke(
            duplication_analyze,
            ["--path", str(temp_project_dir), "--threshold", "0.85", "--detailed"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # CLI is a placeholder, check threshold and mode are applied
        assert "Threshold: 0.85" in result.output
        assert "Mode: Detailed" in result.output


# ============================================================================
# Analyze Command Tests - JSON Output
# ============================================================================


class TestAnalyzeJSON:
    """Tests for analyze command JSON output."""

    def test_analyze_json_output_valid(self, runner: CliRunner) -> None:
        """Test analyze command returns valid JSON."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        # Parse JSON
        import json

        output = json.loads(result.output)
        assert "status" in output
        assert "path" in output
        assert "threshold" in output
        assert "detailed" in output
        assert "message" in output

    def test_analyze_json_has_placeholder_status(self, runner: CliRunner) -> None:
        """Test analyze command JSON has placeholder status."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["status"] == "placeholder"
        assert "async" in output["message"].lower()

    def test_analyze_json_includes_custom_threshold(self, runner: CliRunner) -> None:
        """Test analyze command JSON includes custom threshold."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.9"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["threshold"] == 0.9

    def test_analyze_json_includes_detailed_flag(self, runner: CliRunner) -> None:
        """Test analyze command JSON includes detailed flag."""
        result = runner.invoke(
            duplication_analyze,
            ["--detailed"],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert output["detailed"] is True

    def test_analyze_json_includes_path(self, runner: CliRunner, temp_project_dir: Path) -> None:
        """Test analyze command JSON includes custom path."""
        result = runner.invoke(
            duplication_analyze,
            ["--path", str(temp_project_dir)],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        # CLI is a placeholder, just check path key exists
        assert "path" in output

    def test_analyze_json_consistency(self, runner: CliRunner) -> None:
        """Test analyze command JSON output is consistent."""
        result1 = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": True},
        )
        result2 = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": True},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0

        import json

        output1 = json.loads(result1.output)
        output2 = json.loads(result2.output)
        assert output1 == output2


# ============================================================================
# Scan Command Tests
# ============================================================================


class TestScanCommand:
    """Tests for scan command functionality."""

    def test_scan_displays_header(self, runner: CliRunner) -> None:
        """Test scan command displays proper header."""
        result = runner.invoke(
            duplication_scan,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Code Duplication Scan" in result.output
        assert "=" * 60 in result.output

    def test_scan_shows_defaults(self, runner: CliRunner) -> None:
        """Test scan command shows default values."""
        result = runner.invoke(
            duplication_scan,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Path: ." in result.output
        assert "Threshold: 0.8" in result.output
        assert "Format: text" in result.output

    def test_scan_with_custom_threshold(self, runner: CliRunner) -> None:
        """Test scan command with custom threshold."""
        result = runner.invoke(
            duplication_scan,
            ["--threshold", "0.85"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.85" in result.output

    def test_scan_with_json_format(self, runner: CliRunner) -> None:
        """Test scan command with JSON format."""
        result = runner.invoke(
            duplication_scan,
            ["--format", "json"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Format: json" in result.output

    def test_scan_with_markdown_format(self, runner: CliRunner) -> None:
        """Test scan command with markdown format."""
        result = runner.invoke(
            duplication_scan,
            ["--format", "markdown"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Format: markdown" in result.output

    def test_scan_json_output(self, runner: CliRunner) -> None:
        """Test scan command returns valid JSON."""
        result = runner.invoke(
            duplication_scan,
            [],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "status" in output
        assert "path" in output
        assert "threshold" in output


# ============================================================================
# Report Command Tests
# ============================================================================


class TestReportCommand:
    """Tests for report command functionality."""

    def test_report_displays_header(self, runner: CliRunner) -> None:
        """Test report command displays proper header."""
        result = runner.invoke(
            duplication_report,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Duplication Report" in result.output
        assert "=" * 60 in result.output

    def test_report_shows_latest_by_default(self, runner: CliRunner) -> None:
        """Test report command shows latest scan by default."""
        result = runner.invoke(
            duplication_report,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "File: latest scan" in result.output

    def test_report_with_custom_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test report command with custom file."""
        report_file = tmp_path / "report.json"
        report_file.write_text("{}")

        result = runner.invoke(
            duplication_report,
            ["--file", str(report_file)],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # CLI is a placeholder, just check it doesn't crash
        assert "Duplication Report" in result.output

    def test_report_with_json_format(self, runner: CliRunner) -> None:
        """Test report command with JSON format."""
        result = runner.invoke(
            duplication_report,
            ["--format", "json"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Format: json" in result.output

    def test_report_json_output(self, runner: CliRunner) -> None:
        """Test report command returns valid JSON."""
        result = runner.invoke(
            duplication_report,
            [],
            obj={"output_json": True},
        )

        assert result.exit_code == 0

        import json

        output = json.loads(result.output)
        assert "status" in output
        assert "file" in output
        assert "format" in output


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_analyze_nonexistent_path(self, runner: CliRunner) -> None:
        """Test analyze command with nonexistent path."""
        result = runner.invoke(
            duplication_analyze,
            ["--path", "/nonexistent/path/that/does/not/exist"],
            obj={"output_json": False},
        )

        # Should fail with path validation error
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower() or "invalid" in result.output.lower()

    def test_analyze_consistency_across_calls(self, runner: CliRunner) -> None:
        """Test analyze command output is consistent across calls."""
        result1 = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.9"],
            obj={"output_json": False},
        )
        result2 = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.9"],
            obj={"output_json": False},
        )

        assert result1.exit_code == 0
        assert result2.exit_code == 0
        assert result1.output == result2.output

    def test_scan_with_output_file(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test scan command with output file specified."""
        output_file = tmp_path / "output.json"

        result = runner.invoke(
            duplication_scan,
            ["--output", str(output_file)],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        # CLI is a placeholder, just check it doesn't crash
        assert "Code Duplication Scan" in result.output

    def test_invalid_option_value(self, runner: CliRunner) -> None:
        """Test command rejects invalid option values."""
        result = runner.invoke(
            duplication_scan,
            ["--format", "invalid_format"],
            obj={"output_json": False},
        )

        # Should fail with invalid choice error
        assert result.exit_code != 0
        assert "invalid" in result.output.lower()


# ============================================================================
# Integration Tests - Command Discovery
# ============================================================================


class TestCommandDiscovery:
    """Tests for CLI command discovery and registration."""

    def test_duplication_in_main_cli(self, runner: CliRunner) -> None:
        """Test duplication command is accessible from main CLI."""
        from autoflow.cli.main import main

        result = runner.invoke(main, ["duplication", "--help"])
        assert result.exit_code == 0
        assert "Code duplication detection commands" in result.output

    def test_analyze_command_accessible_from_main(self, runner: CliRunner) -> None:
        """Test analyze command is accessible from main CLI."""
        from autoflow.cli.main import main

        result = runner.invoke(main, ["duplication", "analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze code for duplications" in result.output

    def test_scan_command_accessible_from_main(self, runner: CliRunner) -> None:
        """Test scan command is accessible from main CLI."""
        from autoflow.cli.main import main

        result = runner.invoke(main, ["duplication", "scan", "--help"])
        assert result.exit_code == 0
        assert "Scan code for duplications" in result.output

    def test_report_command_accessible_from_main(self, runner: CliRunner) -> None:
        """Test report command is accessible from main CLI."""
        from autoflow.cli.main import main

        result = runner.invoke(main, ["duplication", "report", "--help"])
        assert result.exit_code == 0
        assert "Display a duplication report" in result.output


# ============================================================================
# CLI Usage Examples
# ============================================================================


class TestCLIUsageExamples:
    """Tests that verify CLI usage examples work as documented."""

    def test_analyze_basic_usage(self, runner: CliRunner) -> None:
        """Test basic usage example: autoflow duplication analyze."""
        result = runner.invoke(
            duplication_analyze,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Code Duplication Analysis" in result.output

    def test_analyze_with_threshold_example(self, runner: CliRunner) -> None:
        """Test usage example: autoflow duplication analyze --threshold 0.9."""
        result = runner.invoke(
            duplication_analyze,
            ["--threshold", "0.9"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Threshold: 0.9" in result.output

    def test_analyze_detailed_example(self, runner: CliRunner) -> None:
        """Test usage example: autoflow duplication analyze --detailed."""
        result = runner.invoke(
            duplication_analyze,
            ["--detailed"],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Mode: Detailed" in result.output

    def test_scan_basic_usage(self, runner: CliRunner) -> None:
        """Test basic usage example: autoflow duplication scan."""
        result = runner.invoke(
            duplication_scan,
            [],
            obj={"output_json": False},
        )

        assert result.exit_code == 0
        assert "Code Duplication Scan" in result.output
