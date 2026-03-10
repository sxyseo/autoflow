"""
Unit Tests for Autoflow Autonomy Orchestration

Tests the autonomy orchestration functionality including binary probing,
coordination brief generation, and taskmaster synchronization.

These tests use proper imports from autoflow.orchestration.autonomy
instead of dynamic module loading.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from autoflow.orchestration.autonomy import (
    coordination_brief,
    probe_binary,
    taskmaster_sync,
)

# ============================================================================
# Binary Probe Tests
# ============================================================================


class TestProbeBinary(unittest.TestCase):
    """Tests for probe_binary function."""

    def test_probe_binary_reports_resume_and_model_capabilities(self) -> None:
        """Test that probe_binary detects resume and model capabilities."""
        with (
            patch(
                "autoflow.orchestration.autonomy.shutil.which",
                return_value="/usr/bin/codex",
            ),
            patch(
                "autoflow.orchestration.autonomy.subprocess.run",
                side_effect=[
                    SimpleNamespace(stdout="codex 1.0.0", stderr="", returncode=0),
                    SimpleNamespace(stdout="resume --model", stderr="", returncode=0),
                ],
            ),
        ):
            result = probe_binary("codex")

        self.assertTrue(result["available"])
        self.assertTrue(result["capabilities"]["resume"])
        self.assertTrue(result["capabilities"]["model_flag"])


# ============================================================================
# Coordination Brief Tests
# ============================================================================


class TestCoordinationBrief(unittest.TestCase):
    """Tests for coordination_brief function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_dir = self.root / ".autoflow"
        self.state_dir.mkdir()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_coordination_brief_uses_strategy_and_fallback_agent(self) -> None:
        """Test that coordination_brief uses strategy and fallback agent."""
        # Create mock for continuous_iteration module
        mock_ci = unittest.mock.MagicMock()
        mock_ci.select_agent_for_role.return_value = ("claude", "fallback")

        with (
            patch(
                "autoflow.orchestration.autonomy.load_config_from_path"
            ) as mock_load_config,
            patch(
                "autoflow.orchestration.autonomy.health_report"
            ) as mock_health_report,
            patch("autoflow.orchestration.autonomy.load_json") as mock_load_json,
            patch(
                "autoflow.orchestration.autonomy.autoflow_json"
            ) as mock_autoflow_json,
            patch.dict("sys.modules", {"continuous_iteration": mock_ci}),
        ):
            # Setup mocks
            mock_load_config.return_value = {
                "role_agents": {"reviewer": "claude-review"}
            }
            mock_health_report.return_value = {
                "binaries": [{"name": "codex", "available": True}]
            }
            mock_load_json.side_effect = [
                {"agents": {"claude": {"command": "claude"}}},
                {"agents": [{"name": "claude", "protocol": "cli"}]},
            ]
            mock_autoflow_json.side_effect = [
                {
                    "recommended_next_action": {
                        "id": "T4",
                        "owner_role": "reviewer",
                    }
                },
                {
                    "playbook": [
                        {
                            "category": "tests",
                            "rule": "write tests",
                            "evidence_count": 2,
                        }
                    ]
                },
            ]

            brief = coordination_brief(
                self.root,
                self.state_dir,
                "spec-a",
                "config/continuous-iteration.example.json",
                {"monitoring": {}, "openclaw": {"workflow_contract": "x"}},
            )

        self.assertEqual(brief["proposed_dispatch"]["agent"], "claude")
        self.assertEqual(brief["proposed_dispatch"]["agent_selection"], "fallback")
        self.assertEqual(brief["strategy"]["playbook"][0]["category"], "tests")


# ============================================================================
# Taskmaster Sync Tests
# ============================================================================


class TestTaskmasterSync(unittest.TestCase):
    """Tests for taskmaster_sync function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.temp_dir.cleanup()

    def test_taskmaster_sync_exports_when_enabled(self) -> None:
        """Test that taskmaster_sync exports data when enabled."""
        export_path = self.root / "taskmaster.json"

        with patch(
            "autoflow.orchestration.autonomy.subprocess.run",
            return_value=SimpleNamespace(stdout="", stderr="", returncode=0),
        ):
            result = taskmaster_sync(
                self.root,
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
