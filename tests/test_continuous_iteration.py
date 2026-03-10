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
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Import functions from continuous_iteration.py
# Note: We need to add the scripts directory to the path
import sys
scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from continuous_iteration import (
    auto_commit,
    default_role_preferences,
    dispatch_gate,
    dispatch_next,
    git_branch,
    git_dirty,
    load_agent_catalog,
    load_config,
    load_json,
    run,
    run_verify_commands,
    select_agent_for_role,
    sync_agents,
    task_history,
    workflow_state,
    ROOT,
    STATE_DIR,
    AGENTS_FILE,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_workdir(tmp_path: Path) -> Path:
    """Create a temporary working directory for testing."""
    workdir = tmp_path / "project"
    workdir.mkdir()
    return workdir


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "config.json"
    config_data = {
        "role_agents": {
            "implementation-runner": "codex-impl",
            "reviewer": "claude-review",
        },
        "agent_selection": {
            "sync_before_dispatch": False,  # Disable for tests
            "role_preferences": {
                "implementation-runner": ["custom-impl", "codex-impl"],
            },
        },
        "verify_commands": [],
        "commit": {
            "message_prefix": "autoflow",
            "push": False,
        },
        "retry_policy": {
            "max_automatic_attempts": 3,
            "require_fix_request_for_retry": True,
        },
    }
    config_file.write_text(json.dumps(config_data), encoding="utf-8")
    return config_file


@pytest.fixture
def mock_subprocess_success() -> MagicMock:
    """Mock subprocess that returns success."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = "Success output"
    mock.stderr = ""
    return mock


@pytest.fixture
def mock_subprocess_failure() -> MagicMock:
    """Mock subprocess that returns failure."""
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = ""
    mock.stderr = "Error output"
    return mock


@pytest.fixture
def mock_subprocess_timeout() -> MagicMock:
    """Mock subprocess that times out."""
    mock = MagicMock()
    mock.returncode = None
    mock.stdout = ""
    mock.stderr = "Timeout error"
    return mock


@pytest.fixture
def mock_subprocess_empty() -> MagicMock:
    """Mock subprocess that returns empty output."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = ""
    mock.stderr = ""
    return mock


@pytest.fixture
def mock_git_clean_repo() -> MagicMock:
    """Mock git status for a clean repository."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = ""
    mock.stderr = ""
    return mock


@pytest.fixture
def mock_git_dirty_repo() -> MagicMock:
    """Mock git status for a dirty repository."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = "M scripts/test.py\nA src/new_file.py"
    mock.stderr = ""
    return mock


@pytest.fixture
def sample_config() -> dict:
    """Sample configuration for testing."""
    return {
        "role_agents": {
            "implementation-runner": "codex-impl",
        },
        "agent_selection": {
            "sync_before_dispatch": False,
        },
        "verify_commands": [],
        "commit": {
            "message_prefix": "autoflow",
            "push": False,
            "allow_during_active_runs": False,
        },
        "retry_policy": {
            "max_automatic_attempts": 3,
            "require_fix_request_for_retry": True,
        },
    }


@pytest.fixture
def sample_workflow_state() -> dict:
    """Sample workflow state for testing."""
    return {
        "spec": "test-spec",
        "active_runs": [],
        "blocking_reason": None,
        "fix_request_present": False,
        "recommended_next_action": {
            "id": "T1",
            "owner_role": "implementation-runner",
            "status": "todo",
        },
    }


@pytest.fixture
def sample_task_history() -> list[dict]:
    """Sample task history for testing."""
    return [
        {
            "run_id": "run-1",
            "result": "success",
            "timestamp": "2024-01-01T00:00:00Z",
        },
        {
            "run_id": "run-2",
            "result": "needs_changes",
            "timestamp": "2024-01-02T00:00:00Z",
        },
    ]


# ============================================================================
# Utility Function Tests
# ============================================================================


class TestLoadJson:
    """Tests for load_json function."""

    def test_load_json_existing_file(self, tmp_path: Path) -> None:
        """Test loading an existing JSON file."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")

        result = load_json(json_file)

        assert result == {"key": "value"}

    def test_load_json_nonexistent_file_with_default(self, tmp_path: Path) -> None:
        """Test loading a non-existent file with default value."""
        json_file = tmp_path / "nonexistent.json"

        result = load_json(json_file, default={"default": True})

        assert result == {"default": True}

    def test_load_json_nonexistent_file_no_default(self, tmp_path: Path) -> None:
        """Test loading a non-existent file without default value."""
        json_file = tmp_path / "nonexistent.json"

        result = load_json(json_file)

        assert result == {}


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_valid_json(self, tmp_path: Path) -> None:
        """Test loading a valid config file."""
        config_file = tmp_path / "config.json"
        config_data = {"key": "value", "nested": {"item": 1}}
        config_file.write_text(json.dumps(config_data), encoding="utf-8")

        # Patch ROOT to point to tmp_path
        with patch("continuous_iteration.ROOT", tmp_path):
            result = load_config(str(config_file.relative_to(tmp_path)))

        assert result == config_data


# ============================================================================
# Git Function Tests
# ============================================================================


class TestGitDirty:
    """Tests for git_dirty function."""

    def test_git_dirty_clean(self, mock_subprocess_success: MagicMock) -> None:
        """Test git_dirty when working tree is clean."""
        mock_subprocess_success.stdout = ""

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = git_dirty()

        assert result is False

    def test_git_dirty_dirty(self, mock_subprocess_success: MagicMock) -> None:
        """Test git_dirty when working tree is dirty."""
        mock_subprocess_success.stdout = "M scripts/test.py"

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = git_dirty()

        assert result is True


class TestGitBranch:
    """Tests for git_branch function."""

    def test_git_branch_success(self, mock_subprocess_success: MagicMock) -> None:
        """Test git_branch returns current branch."""
        mock_subprocess_success.stdout = "main"

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = git_branch()

        assert result == "main"


# ============================================================================
# Verify Commands Tests (VULNERABILITY HERE)
# ============================================================================


class TestRunVerifyCommands:
    """Tests for run_verify_commands function."""

    def test_run_verify_commands_empty_list(self) -> None:
        """Test running with empty command list."""
        result = run_verify_commands([], "test-spec")

        assert result == []

    def test_run_verify_commands_single_success(self) -> None:
        """Test running a single successful verification command."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "test output"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = run_verify_commands(["echo {spec}"], "test-spec")

        assert len(result) == 1
        assert result[0]["returncode"] == 0
        assert result[0]["stdout"] == "test output"
        # Command should have spec placeholder replaced
        assert "{spec}" not in result[0]["command"]
        assert "test-spec" in result[0]["command"]

    def test_run_verify_commands_multiple_commands(self) -> None:
        """Test running multiple verification commands."""
        mock_proc1 = MagicMock()
        mock_proc1.returncode = 0
        mock_proc1.stdout = "output1"
        mock_proc1.stderr = ""

        mock_proc2 = MagicMock()
        mock_proc2.returncode = 0
        mock_proc2.stdout = "output2"
        mock_proc2.stderr = ""

        with patch("subprocess.run", side_effect=[mock_proc1, mock_proc2]):
            result = run_verify_commands(["echo test1", "echo test2"], "test-spec")

        assert len(result) == 2
        assert result[0]["stdout"] == "output1"
        assert result[1]["stdout"] == "output2"

    def test_run_verify_commands_failure_stops_execution(self) -> None:
        """Test that command execution stops on first failure."""
        mock_proc1 = MagicMock()
        mock_proc1.returncode = 0
        mock_proc1.stdout = "output1"
        mock_proc1.stderr = ""

        mock_proc2 = MagicMock()
        mock_proc2.returncode = 1
        mock_proc2.stdout = ""
        mock_proc2.stderr = "error"

        mock_proc3 = MagicMock()
        mock_proc3.returncode = 0
        mock_proc3.stdout = "output3"
        mock_proc3.stderr = ""

        with patch("subprocess.run", side_effect=[mock_proc1, mock_proc2, mock_proc3]):
            result = run_verify_commands(["cmd1", "cmd2", "cmd3"], "test-spec")

        # Should only have results for first two commands
        assert len(result) == 2
        assert result[0]["returncode"] == 0
        assert result[1]["returncode"] == 1

    def test_run_verify_commands_spec_placeholder_replacement(self) -> None:
        """Test that {spec} placeholder is replaced in commands."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = run_verify_commands(["test command for {spec}"], "my-spec")

        assert len(result) == 1
        assert result[0]["command"] == "test command for my-spec"

    def test_run_verify_commands_shell_injection_risk(self) -> None:
        """
        TEST: Demonstrates command injection vulnerability via shell=True.

        This test documents the vulnerability where user-provided commands
        are executed with shell=True, allowing command injection.

        The spec parameter could contain malicious shell metacharacters
        that would be executed when the command is run.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output"
        mock_proc.stderr = ""

        # Simulate a malicious spec with shell injection
        malicious_spec = 'test-spec; echo "PWNED"'

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = run_verify_commands(["echo {spec}"], malicious_spec)

            # Verify that the command was executed with shell=True
            assert mock_run.called
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("shell") is True

            # The malicious command is present in the rendered command
            assert "; echo" in result[0]["command"]


# ============================================================================
# Auto Commit Tests
# ============================================================================


class TestAutoCommit:
    """Tests for auto_commit function."""

    def test_auto_commit_blocked_by_active_run(self, sample_config: dict) -> None:
        """Test that commit is blocked when active runs exist."""
        state = {"active_runs": ["run-1"]}

        result = auto_commit(sample_config, "test-spec", False, state)

        assert result["committed"] is False
        assert result["reason"] == "active_run_exists"

    def test_auto_commit_verification_fails(self, sample_config: dict) -> None:
        """Test that commit is blocked when verification fails."""
        state = {"active_runs": []}

        # Add verify_commands to config for this test
        config_with_verify = {
            **sample_config,
            "verify_commands": ["pytest"],
        }

        # Mock run_verify_commands to return a failure
        verify_results = [
            {"command": "pytest", "returncode": 1, "stdout": "", "stderr": "error"}
        ]

        with patch("continuous_iteration.run_verify_commands", return_value=verify_results):
            result = auto_commit(config_with_verify, "test-spec", False, state)

        assert result["committed"] is False
        assert result["reason"] == "verification_failed"
        assert result["verification"] == verify_results

    def test_auto_commit_clean_worktree(self, sample_config: dict) -> None:
        """Test that no commit is made when worktree is clean."""
        state = {"active_runs": []}

        with patch("continuous_iteration.run_verify_commands", return_value=[]):
            with patch("continuous_iteration.git_dirty", return_value=False):
                result = auto_commit(sample_config, "test-spec", False, state)

        assert result["committed"] is False
        assert result["reason"] == "clean_worktree"

    def test_auto_commit_success_no_push(self, sample_config: dict) -> None:
        """Test successful commit without push."""
        state = {"active_runs": []}

        with patch("continuous_iteration.run_verify_commands", return_value=[]):
            with patch("continuous_iteration.git_dirty", return_value=True):
                with patch("continuous_iteration.run") as mock_run:
                    result = auto_commit(sample_config, "test-spec", False, state)

        assert result["committed"] is True
        assert result["pushed"] is False
        assert "message" in result
        assert mock_run.call_count == 2  # git add and git commit

    def test_auto_commit_success_with_push(self, sample_config: dict) -> None:
        """Test successful commit with push."""
        state = {"active_runs": []}

        with patch("continuous_iteration.run_verify_commands", return_value=[]):
            with patch("continuous_iteration.git_dirty", return_value=True):
                with patch("continuous_iteration.git_branch", return_value="main"):
                    with patch("continuous_iteration.run") as mock_run:
                        result = auto_commit(sample_config, "test-spec", True, state)

        assert result["committed"] is True
        assert result["pushed"] is True
        assert mock_run.call_count == 3  # git add, commit, and push


# ============================================================================
# Workflow State Tests
# ============================================================================


class TestWorkflowState:
    """Tests for workflow_state function."""

    def test_workflow_state_success(self, mock_subprocess_success: MagicMock) -> None:
        """Test getting workflow state."""
        mock_state = {"spec": "test", "tasks": []}
        mock_subprocess_success.stdout = json.dumps(mock_state)

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = workflow_state("test-spec")

        assert result == mock_state


class TestTaskHistory:
    """Tests for task_history function."""

    def test_task_history_success(self, mock_subprocess_success: MagicMock) -> None:
        """Test getting task history."""
        mock_history = [
            {"run_id": "run-1", "result": "success"},
            {"run_id": "run-2", "result": "needs_changes"},
        ]
        mock_subprocess_success.stdout = json.dumps(mock_history)

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = task_history("test-spec", "T1")

        assert result == mock_history


# ============================================================================
# Agent Selection Tests
# ============================================================================


class TestDefaultRolePreferences:
    """Tests for default_role_preferences function."""

    def test_default_role_preferences_implementation_runner(self) -> None:
        """Test default preferences for implementation-runner role."""
        result = default_role_preferences("implementation-runner")

        assert isinstance(result, list)
        assert len(result) > 0
        assert "codex-impl" in result or "codex" in result

    def test_default_role_preferences_reviewer(self) -> None:
        """Test default preferences for reviewer role."""
        result = default_role_preferences("reviewer")

        assert isinstance(result, list)
        assert len(result) > 0
        assert "claude-review" in result or "claude" in result

    def test_default_role_preferences_unknown_role(self) -> None:
        """Test default preferences for unknown role."""
        result = default_role_preferences("unknown-role")

        assert result == []


class TestSelectAgentForRole:
    """Tests for select_agent_for_role function."""

    def test_select_agent_explicit_config(self) -> None:
        """Test selecting explicitly configured agent."""
        config = {
            "role_agents": {
                "implementation-runner": "custom-agent",
            },
            "agent_selection": {},
        }
        catalog = {
            "custom-agent": {"command": "custom"},
        }

        agent, source = select_agent_for_role(config, "implementation-runner", catalog)

        assert agent == "custom-agent"
        assert source == "configured"

    def test_select_agent_fallback_preferences(self) -> None:
        """Test selecting agent from fallback preferences."""
        config = {
            "role_agents": {},
            "agent_selection": {
                "role_preferences": {
                    "implementation-runner": ["fallback-agent"],
                },
            },
        }
        catalog = {
            "fallback-agent": {"command": "fallback"},
        }

        agent, source = select_agent_for_role(config, "implementation-runner", catalog)

        assert agent == "fallback-agent"
        assert source == "fallback"

    def test_select_agent_default_preferences(self) -> None:
        """Test selecting agent from default preferences."""
        config = {
            "role_agents": {},
            "agent_selection": {},
        }
        catalog = {
            "codex-impl": {"command": "codex"},
        }

        agent, source = select_agent_for_role(config, "implementation-runner", catalog)

        assert agent is not None
        assert source == "fallback"

    def test_select_agent_not_found(self) -> None:
        """Test when no suitable agent is found."""
        config = {
            "role_agents": {},
            "agent_selection": {},
        }
        catalog = {}

        agent, source = select_agent_for_role(config, "implementation-runner", catalog)

        assert agent is None
        assert source == "missing"

    def test_select_agent_deduplication(self) -> None:
        """Test that duplicate agent preferences are deduplicated."""
        config = {
            "role_agents": {
                "implementation-runner": "agent-a",
            },
            "agent_selection": {
                "role_preferences": {
                    "implementation-runner": ["agent-a", "agent-b"],
                },
            },
        }
        catalog = {
            "agent-a": {"command": "a"},
            "agent-b": {"command": "b"},
        }

        agent, source = select_agent_for_role(config, "implementation-runner", catalog)

        # Should return agent-a only once (from explicit config)
        assert agent == "agent-a"


# ============================================================================
# Dispatch Gate Tests
# ============================================================================


class TestDispatchGate:
    """Tests for dispatch_gate function."""

    def test_gate_blocked_by_active_runs(self, sample_config: dict) -> None:
        """Test that dispatch is blocked when active runs exist."""
        state = {"active_runs": ["run-1"], "blocking_reason": None}

        result = dispatch_gate(sample_config, state, {})

        assert result is not None
        assert result["blocked"] is True
        assert result["reason"] == "active_run_exists"

    def test_gate_blocked_by_blocking_reason(self, sample_config: dict) -> None:
        """Test that dispatch is blocked when there's a blocking reason."""
        state = {
            "active_runs": [],
            "blocking_reason": "missing_dependencies",
        }

        result = dispatch_gate(sample_config, state, {})

        assert result is not None
        assert result["blocked"] is True
        assert result["reason"] == "missing_dependencies"

    def test_gate_blocked_no_ready_task(self, sample_config: dict) -> None:
        """Test that dispatch is blocked when no ready task."""
        state = {
            "active_runs": [],
            "blocking_reason": None,
        }

        result = dispatch_gate(sample_config, state, None)

        assert result is not None
        assert result["blocked"] is True
        assert result["reason"] == "no_ready_task"

    def test_gate_max_attempts_reached(self, sample_config: dict) -> None:
        """Test that dispatch is blocked after max automatic attempts."""
        state = {
            "active_runs": [],
            "blocking_reason": None,
            "spec": "test-spec",
            "fix_request_present": False,
        }

        next_action = {
            "id": "T1",
            "status": "needs_changes",
        }

        # Mock task_history to return 3 unsuccessful attempts
        history = [
            {"result": "needs_changes"},
            {"result": "needs_changes"},
            {"result": "blocked"},
        ]

        with patch("continuous_iteration.task_history", return_value=history):
            result = dispatch_gate(sample_config, state, next_action)

        assert result is not None
        assert result["blocked"] is True
        assert result["reason"] == "max_automatic_attempts_reached"
        assert result["attempts"] == 3

    def test_gate_missing_fix_request(self, sample_config: dict) -> None:
        """Test that dispatch is blocked when fix request is required but missing."""
        state = {
            "active_runs": [],
            "blocking_reason": None,
            "spec": "test-spec",
            "fix_request_present": False,
        }

        next_action = {
            "id": "T1",
            "status": "needs_changes",
        }

        # Mock task_history to return less than max attempts
        history = [{"result": "needs_changes"}]

        with patch("continuous_iteration.task_history", return_value=history):
            result = dispatch_gate(sample_config, state, next_action)

        assert result is not None
        assert result["blocked"] is True
        assert result["reason"] == "missing_fix_request"

    def test_gate_passes_all_checks(self, sample_config: dict) -> None:
        """Test that dispatch gate passes when all checks are met."""
        state = {
            "active_runs": [],
            "blocking_reason": None,
            "spec": "test-spec",
            "fix_request_present": False,
        }

        next_action = {
            "id": "T1",
            "status": "todo",
        }

        # Mock task_history to return empty history
        with patch("continuous_iteration.task_history", return_value=[]):
            result = dispatch_gate(sample_config, state, next_action)

        assert result is None


# ============================================================================
# Dispatch Next Tests
# ============================================================================


class TestDispatchNext:
    """Tests for dispatch_next function."""

    def test_dispatch_blocked_by_gate(self, sample_config: dict) -> None:
        """Test that dispatch is blocked when gate returns a block."""
        state = {
            "active_runs": ["run-1"],
            "blocking_reason": None,
        }

        with patch("continuous_iteration.workflow_state", return_value=state):
            result = dispatch_next(sample_config, "test-spec", False)

        assert result["dispatched"] is False
        assert result["reason"] == "active_run_exists"
        assert "state" in result

    def test_dispatch_no_agent_for_role(self, sample_config: dict) -> None:
        """Test dispatch when no agent is available for the role."""
        state = {
            "spec": "test-spec",
            "active_runs": [],
            "blocking_reason": None,
            "recommended_next_action": {
                "id": "T1",
                "owner_role": "implementation-runner",
            },
        }

        with patch("continuous_iteration.workflow_state", return_value=state):
            with patch("continuous_iteration.load_agent_catalog", return_value={}):
                with patch("continuous_iteration.select_agent_for_role", return_value=(None, "missing")):
                    result = dispatch_next(sample_config, "test-spec", False)

        assert result["dispatched"] is False
        assert "no_agent_for_role" in result["reason"]

    def test_dispatch_dry_run(self, sample_config: dict) -> None:
        """Test dispatch in dry run mode (dispatch=False)."""
        state = {
            "spec": "test-spec",
            "active_runs": [],
            "blocking_reason": None,
            "recommended_next_action": {
                "id": "T1",
                "owner_role": "implementation-runner",
            },
        }

        with patch("continuous_iteration.workflow_state", return_value=state):
            with patch("continuous_iteration.load_agent_catalog", return_value={"agent-a": {}}):
                with patch("continuous_iteration.select_agent_for_role", return_value=("agent-a", "fallback")):
                    result = dispatch_next(sample_config, "test-spec", False)

        assert result["dispatched"] is False
        assert "payload" in result
        assert result["payload"]["agent"] == "agent-a"

    def test_dispatch_with_sync(self, sample_config: dict) -> None:
        """Test dispatch with agent sync enabled."""
        config_with_sync = {
            **sample_config,
            "agent_selection": {
                "sync_before_dispatch": True,
                "overwrite_discovered": False,
            },
        }

        state = {
            "spec": "test-spec",
            "active_runs": [],
            "blocking_reason": None,
            "recommended_next_action": {
                "id": "T1",
                "owner_role": "implementation-runner",
            },
        }

        sync_result = {"synced": ["agent-a"]}

        with patch("continuous_iteration.workflow_state", return_value=state):
            with patch("continuous_iteration.sync_agents", return_value=sync_result):
                with patch("continuous_iteration.load_agent_catalog", return_value={"agent-a": {}}):
                    with patch("continuous_iteration.select_agent_for_role", return_value=("agent-a", "fallback")):
                        result = dispatch_next(config_with_sync, "test-spec", False)

        assert "agent_sync" in result
        assert result["agent_sync"] == sync_result


# ============================================================================
# Sync Agents Tests
# ============================================================================


class TestSyncAgents:
    """Tests for sync_agents function."""

    def test_sync_agents_basic(self, mock_subprocess_success: MagicMock) -> None:
        """Test basic agent sync."""
        mock_subprocess_success.stdout = json.dumps({"synced": ["agent-a"]})

        with patch("continuous_iteration.run", return_value=mock_subprocess_success):
            result = sync_agents()

        assert "synced" in result

    def test_sync_agents_with_overwrite(self, mock_subprocess_success: MagicMock) -> None:
        """Test agent sync with overwrite flag."""
        mock_subprocess_success.stdout = json.dumps({"synced": ["agent-a"]})

        with patch("continuous_iteration.run", return_value=mock_subprocess_success) as mock_run:
            result = sync_agents(overwrite=True)

        # Verify that --overwrite flag was passed
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "--overwrite" in call_args


# ============================================================================
# Load Agent Catalog Tests
# ============================================================================


class TestLoadAgentCatalog:
    """Tests for load_agent_catalog function."""

    def test_load_agent_catalog_empty(self, tmp_path: Path) -> None:
        """Test loading agent catalog when agents file doesn't exist."""
        with patch("continuous_iteration.AGENTS_FILE", tmp_path / "nonexistent.json"):
            result = load_agent_catalog()

        assert result == {}

    def test_load_agent_catalog_with_agents(self, tmp_path: Path) -> None:
        """Test loading agent catalog with agents defined."""
        agents_file = tmp_path / "agents.json"
        agents_data = {
            "agents": {
                "agent-a": {"command": "a"},
                "agent-b": {"command": "b"},
            },
        }
        agents_file.write_text(json.dumps(agents_data), encoding="utf-8")

        with patch("continuous_iteration.AGENTS_FILE", agents_file):
            result = load_agent_catalog()

        assert len(result) == 2
        assert "agent-a" in result
        assert "agent-b" in result
