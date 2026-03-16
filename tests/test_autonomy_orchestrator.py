"""
Unit Tests for CLI Healthcheck and Autonomy Orchestrator

Tests the CLI healthcheck functionality for probing binary capabilities
and the Autonomy Orchestrator for coordinating agent dispatch and taskmaster sync.

These tests use mocks to test scripts without requiring actual agent
installations or external services.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Add the project root to the path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class CliHealthcheckTests(unittest.TestCase):
    """Tests for cli_healthcheck.py module."""

    def setUp(self) -> None:
        """Import the module for each test to ensure clean state."""
        # Import here to avoid module-level code execution issues
        import scripts.cli_healthcheck as cli_healthcheck

        self.module = cli_healthcheck

    def test_probe_binary_reports_resume_and_model_capabilities(self) -> None:
        """Test that probe_binary correctly detects resume and model capabilities."""
        with (
            patch("scripts.cli_healthcheck.shutil.which", return_value="/usr/bin/codex"),
            patch(
                "scripts.cli_healthcheck.run",
                side_effect=[
                    SimpleNamespace(stdout="codex 1.0.0", stderr="", returncode=0),
                    SimpleNamespace(stdout="resume --model", stderr="", returncode=0),
                ],
            ),
        ):
            result = self.module.probe_binary("codex")
        self.assertTrue(result["available"])
        self.assertTrue(result["capabilities"]["resume"])
        self.assertTrue(result["capabilities"]["model_flag"])


class AutonomyOrchestratorTests(unittest.TestCase):
    """Tests for autonomy_orchestrator.py module."""

    def setUp(self) -> None:
        """Set up test fixtures and import the module."""
        # Add scripts directory to sys.path for relative imports within scripts
        repo_root = Path(__file__).resolve().parents[1]
        scripts_dir = str(repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        # Import here to avoid module-level code execution issues
        import scripts.autonomy_orchestrator as autonomy_orchestrator

        self.module = autonomy_orchestrator
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Clean up temporary directory."""
        self.temp_dir.cleanup()

    def test_coordination_brief_uses_strategy_and_fallback_agent(self) -> None:
        """Test that coordination_brief correctly uses strategy and fallback agent."""
        with (
            patch("scripts.autonomy_orchestrator.load_config", return_value={"role_agents": {"reviewer": "claude-review"}}),
            patch(
                "scripts.autonomy_orchestrator.get_workflow_state",
                return_value={
                    "recommended_next_action": {
                        "id": "T4",
                        "owner_role": "reviewer",
                    }
                },
            ),
            patch(
                "scripts.autonomy_orchestrator.get_strategy_summary",
                return_value={"playbook": [{"category": "tests", "rule": "write tests", "evidence_count": 2}]},
            ),
            patch(
                "scripts.autonomy_orchestrator.health_report",
                return_value={"binaries": [{"name": "codex", "available": True}]},
            ),
            patch(
                "scripts.autonomy_orchestrator.load_json",
                side_effect=[
                    {"agents": {"claude": {"command": "claude"}}},
                    {"agents": [{"name": "claude", "protocol": "cli"}]},
                ],
            ),
            patch(
                "scripts.continuous_iteration.select_agent_for_role",
                return_value=("claude", "fallback"),
            ),
        ):
            brief = self.module.coordination_brief(
                "spec-a",
                "config/continuous-iteration.example.json",
                {"monitoring": {}, "openclaw": {"workflow_contract": "x"}},
            )
        self.assertEqual(brief["proposed_dispatch"]["agent"], "claude")
        self.assertEqual(brief["proposed_dispatch"]["agent_selection"], "fallback")
        self.assertEqual(brief["strategy"]["playbook"][0]["category"], "tests")

    def test_taskmaster_sync_exports_when_enabled(self) -> None:
        """Test that taskmaster_sync correctly exports when enabled."""
        export_path = self.root / "taskmaster.json"
        with (
            patch("scripts.autonomy_orchestrator.ROOT", self.root),
            patch("scripts.autonomy_orchestrator.taskmaster_export"),
        ):
            result = self.module.taskmaster_sync(
                "spec-a",
                {
                    "taskmaster": {
                        "enabled": True,
                        "export_file": str(export_path),
                    }
                },
            )
        self.assertTrue(result["enabled"])
        self.assertEqual(result["export_file"], str(export_path))


if __name__ == "__main__":
    unittest.main()
