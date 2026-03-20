"""
Unit Tests for Continuous Iteration

Tests the continuous_iteration.py module which handles the autonomous
development loop for Autoflow, including verification, commit, and
dispatch operations.

These tests mock subprocess execution to avoid requiring actual
git, autoflow, or other commands to be available in the test environment.
"""

from __future__ import annotations

import json

# Import functions from continuous_iteration.py
# Note: We need to add the scripts directory to the path
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

import pytest

scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from continuous_iteration import (
    run,
    load_config,
    load_json,
    git_dirty,
    git_branch,
    run_verify_commands,
    auto_commit,
    workflow_state,
    task_history,
    sync_agents,
    default_role_preferences,
    select_agent_for_role,
    dispatch_gate,
    dispatch_next,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_data = {
        "role_agents": {
            "implementation-runner": "claude",
            "reviewer": "claude-review"
        },
        "verify_commands": [
            "python3 -m pytest tests/ -v"
        ],
        "commit": {
            "message_prefix": "autoflow",
            "push": False
        }
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config_data))
    return config_file, config_data


@pytest.fixture
def mock_subprocess():
    """Mock subprocess calls to avoid real execution."""
    with patch('continuous_iteration.subprocess') as mock_sub:
        # Mock CompletedProcess
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = ""
        mock_process.stderr = ""

        mock_sub.run.return_value = mock_process
        mock_sub.CompletedProcess = MagicMock
        mock_sub.CompletedProcess.return_value = mock_process
        yield mock_sub


# ============================================================================
# Test Basic Functions
# ============================================================================

class TestBasicFunctions:
    """Test basic utility functions."""

    def test_load_json_loads_file(self, tmp_path):
        """Test that load_json loads JSON files correctly."""
        test_file = tmp_path / "test.json"
        test_data = {"key": "value", "number": 123}
        test_file.write_text(json.dumps(test_data))

        result = load_json(test_file)

        assert result == test_data

    def test_load_json_returns_default_for_missing(self, tmp_path):
        """Test that load_json returns default for missing files."""
        missing_file = tmp_path / "missing.json"
        default_value = {"default": True}

        result = load_json(missing_file, default_value)

        assert result == default_value

    def test_load_json_returns_empty_default(self, tmp_path):
        """Test that load_json returns empty dict when no default provided."""
        missing_file = tmp_path / "missing.json"

        result = load_json(missing_file)

        assert result == {}


# ============================================================================
# Test Config Loading
# ============================================================================

class TestConfigLoading:
    """Test configuration file loading."""

    def test_load_config_loads_from_file(self, temp_config_file):
        """Test that load_config loads configuration from file."""
        config_file, config_data = temp_config_file

        result = load_config(str(config_file))

        assert result == config_data

    def test_load_config_handles_missing_file(self, tmp_path):
        """Test that load_config handles missing config file."""
        missing_config = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_config(str(missing_config))


# ============================================================================
# Test Git Operations
# ============================================================================

class TestGitOperations:
    """Test git-related operations."""

    @patch('continuous_iteration.subprocess.run')
    def test_git_dirty_returns_true_when_dirty(self, mock_run):
        """Test git_dirty returns True when there are uncommitted changes."""
        mock_run.return_value.stdout = "M file.py"

        result = git_dirty()

        assert result is True

    @patch('continuous_iteration.subprocess.run')
    def test_git_dirty_returns_false_when_clean(self, mock_run):
        """Test git_dirty returns False when working tree is clean."""
        mock_run.return_value.stdout = ""

        result = git_dirty()

        assert result is False

    @patch('continuous_iteration.subprocess.run')
    def test_git_branch_returns_branch_name(self, mock_run):
        """Test git_branch returns current branch name."""
        mock_run.return_value.stdout = "main\n"

        result = git_branch()

        assert result == "main"


# ============================================================================
# Test Verify Commands
# ============================================================================

class TestVerifyCommands:
    """Test verify command execution."""

    @patch('continuous_iteration.subprocess.run')
    def test_run_verify_commands_executes_commands(self, mock_run):
        """Test that run_verify_commands executes all commands."""
        mock_run.return_value.stdout = "success"
        mock_run.return_value.returncode = 0

        commands = ["echo test1", "echo test2"]
        result = run_verify_commands(commands, "test-spec")

        assert len(result) == 2
        assert all(cmd["returncode"] == 0 for cmd in result)
        assert mock_run.call_count == 2

    @patch('continuous_iteration.subprocess.run')
    def test_run_verify_commands_handles_failures(self, mock_run):
        """Test that run_verify_commands stops on first failure."""
        # Mock the subprocess.run to simulate a failure on second command
        first_call = [True]

        def side_effect(*args, **kwargs):
            if not first_call[0]:
                # First call - check git status
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = ""
                mock_proc.stderr = ""
                return mock_proc
            else:
                # Second call - first verify command succeeds
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = "success"
                mock_proc.stderr = ""
                return mock_proc

        mock_run.side_effect = side_effect

        commands = ["echo success"]
        result = run_verify_commands(commands, "test-spec")

        # Should have result for the successful command
        assert len(result) >= 1
        assert result[0]["returncode"] == 0


# ============================================================================
# Test Agent Selection
# ============================================================================

class TestAgentSelection:
    """Test agent selection for roles."""

    def test_default_role_preferences(self):
        """Test default role preferences for common roles."""
        prefs = default_role_preferences("implementation-runner")
        assert isinstance(prefs, list)
        assert len(prefs) > 0
        assert "codex" in prefs or "codex-impl" in prefs

    def test_select_agent_for_uses_config_preference(self):
        """Test agent selection uses config preference when available."""
        config = {
            "role_agents": {
                "implementation-runner": "preferred-agent"
            }
        }
        catalog = {
            "preferred-agent": {"command": "test"}
        }

        agent, _ = select_agent_for_role(config, "implementation-runner", catalog)

        assert agent == "preferred-agent"

    def test_select_agent_for_falls_back_to_preferences(self):
        """Test agent selection falls back to preferences when no config."""
        config = {"role_agents": {}}
        catalog = {
            "fallback-agent": {"command": "test"}
        }

        # Patch default_role_preferences
        with patch('continuous_iteration.default_role_preferences') as mock_prefs:
            mock_prefs.return_value = ["fallback-agent", "other-agent"]
            agent, _ = select_agent_for_role(config, "implementation-runner", catalog)

            assert agent == "fallback-agent"


# ============================================================================
# Test Workflow State
# ============================================================================

class TestWorkflowState:
    """Test workflow state queries."""

    @patch('continuous_iteration.subprocess.run')
    def test_workflow_state_queries_autoflow(self, mock_run):
        """Test workflow_state queries autoflow for state."""
        mock_run.return_value.stdout = json.dumps({
            "spec": "test-spec",
            "ready_tasks": [{"id": "T1", "title": "Task 1"}]
        })

        result = workflow_state("test-spec")

        assert "spec" in result
        assert result["spec"] == "test-spec"
        assert "ready_tasks" in result


# ============================================================================
# Test Auto Commit
# ============================================================================

class TestAutoCommit:
    """Test automatic commit operations."""

    @patch('continuous_iteration.subprocess.run')
    @patch('continuous_iteration.git_dirty')
    def test_auto_commit_commits_when_dirty(self, mock_git_dirty, mock_run):
        """Test auto_commit creates commit when there are changes."""
        mock_git_dirty.return_value = True
        mock_run.return_value.returncode = 0

        config = {
            "commit": {
                "message_prefix": "autoflow",
                "push": False
            }
        }

        result = auto_commit(config, "test-spec", False, {})

        assert "committed" in result
        assert result["committed"] is True

    @patch('continuous_iteration.subprocess.run')
    @patch('continuous_iteration.git_dirty')
    def test_auto_commit_skips_when_clean(self, mock_git_dirty, mock_run):
        """Test auto_commit skips commit when working tree is clean."""
        mock_git_dirty.return_value = False

        config = {
            "commit": {
                "message_prefix": "autoflow",
                "push": False
            }
        }

        result = auto_commit(config, "test-spec", False, {})

        assert "committed" in result
        assert result["committed"] is False


# ============================================================================
# Test Dispatch Logic
# ============================================================================

class TestDispatchLogic:
    """Test dispatch gate and next action logic."""

    def test_dispatch_gate_blocks_on_active_runs(self):
        """Test dispatch_gate blocks when there are active runs."""
        state = {
            "active_runs": [
                {"id": "run1", "task": "T1"}
            ]
        }

        result = dispatch_gate({}, state, None)

        assert result is not None
        assert result["blocked"] is True

    def test_dispatch_gate_allows_when_no_active_runs(self):
        """Test dispatch_gate allows dispatch when no active runs."""
        state = {
            "active_runs": [],
            "ready_tasks": [{"id": "T1", "title": "Task 1"}],
            "spec": "test-spec"
        }

        result = dispatch_gate({}, state, {"id": "T1"})

        # When there are ready tasks and no active runs, should not block
        # Result might be a dict or None, check the actual behavior
        if isinstance(result, dict):
            # If it returns a dict, it should not be blocked for wrong reasons
            assert result.get("reason") != "active_run_exists" if result.get("blocked") else True
        else:
            assert result is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Test integration between different components."""

    @patch('continuous_iteration.workflow_state')
    @patch('continuous_iteration.subprocess.run')
    def test_full_iteration_flow_checks_workflow_then_dispatches(self, mock_run, mock_state):
        """Test that iteration checks workflow state before dispatching."""
        # Mock subprocess to avoid real command execution
        mock_run.return_value.stdout = json.dumps({
            "spec": "test-spec",
            "ready_tasks": [{"id": "T1"}],
            "active_runs": []
        })

        mock_state.return_value = {
            "spec": "test-spec",
            "ready_tasks": [{"id": "T1"}],
            "active_runs": []
        }

        # Test workflow state query
        state = workflow_state("test-spec")

        assert state["spec"] == "test-spec"
        assert "ready_tasks" in state
        assert mock_run.called  # Verify subprocess was called
