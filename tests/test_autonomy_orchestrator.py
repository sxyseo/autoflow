"""
Unit Tests for CLI Healthcheck and Autonomy Orchestrator

Tests the CLI healthcheck functionality for probing binary capabilities
and the Autonomy Orchestrator for coordinating agent dispatch and taskmaster sync.

These tests use mocks and module loading utilities to test scripts
without requiring actual agent installations or external services.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class CliHealthcheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.module = load_module(self.repo_root / "scripts" / "cli_healthcheck.py", "cli_healthcheck_test")

    def test_probe_binary_reports_resume_and_model_capabilities(self) -> None:
        with (
            patch.object(self.module.shutil, "which", return_value="/usr/bin/codex"),
            patch.object(
                self.module,
                "run",
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
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        scripts_dir = str(self.repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        self.module = load_module(
            self.repo_root / "scripts" / "autonomy_orchestrator.py",
            "autonomy_orchestrator_test",
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_coordination_brief_uses_strategy_and_fallback_agent(self) -> None:
        with (
            patch.object(self.module, "load_config", return_value={"role_agents": {"reviewer": "claude-review"}}),
            patch.object(
                self.module,
                "autoflow_json",
                side_effect=[
                    {
                        "recommended_next_action": {
                            "id": "T4",
                            "owner_role": "reviewer",
                        }
                    },
                    {"playbook": [{"category": "tests", "rule": "write tests", "evidence_count": 2}]},
                ],
            ),
            patch.object(
                self.module,
                "health_report",
                return_value={"binaries": [{"name": "codex", "available": True}]},
            ),
            patch.object(
                self.module,
                "load_json",
                side_effect=[
                    {"agents": {"claude": {"command": "claude"}}},
                    {"agents": [{"name": "claude", "protocol": "cli"}]},
                ],
            ),
            patch.object(
                self.module.continuous_iteration,
                "select_agent_for_role",
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
        export_path = self.root / "taskmaster.json"
        with (
            patch.object(self.module, "ROOT", self.root),
            patch.object(self.module, "run", return_value=SimpleNamespace(stdout="", stderr="", returncode=0)),
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
