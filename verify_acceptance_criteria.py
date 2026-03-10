#!/usr/bin/env python3
"""
Verification script for Taskmaster AI Integration acceptance criteria.

This script verifies that all acceptance criteria from the spec are met:
1. Taskmaster tasks sync to Autoflow as specs/tasks
2. Autoflow execution state syncs back to Taskmaster
3. Task priorities are preserved across sync
4. Conflict resolution handles concurrent updates
5. Integration works with Taskmaster API authentication
"""

import sys
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

# Add current directory to path
sys.path.insert(0, '.')

from autoflow.agents.taskmaster import (
    TaskmasterAdapter,
    TaskmasterConfig,
    TaskmasterAPIClient,
    TaskmasterTask,
    TaskmasterTaskStatus,
    ConflictResolver,
    ConflictResolutionStrategy,
    ConflictType,
)
from autoflow.core.state import Task, TaskStatus


# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_success(message: str) -> None:
    print(f"{GREEN}✓ {message}{RESET}")


def print_error(message: str) -> None:
    print(f"{RED}✗ {message}{RESET}")


def print_info(message: str) -> None:
    print(f"{YELLOW}→ {message}{RESET}")


def verify_criterion_1() -> bool:
    """Verify: Taskmaster tasks sync to Autoflow as specs/tasks"""
    print_info("Criterion 1: Taskmaster tasks sync to Autoflow as specs/tasks")

    try:
        # Create adapter
        config = TaskmasterConfig(
            api_base_url="https://api.taskmaster.ai",
            api_key="test-key",
        )
        adapter = TaskmasterAdapter(config)

        # Create mock Taskmaster tasks
        taskmaster_tasks = [
            TaskmasterTask(
                id="tm-001",
                taskmaster_id="tm-001",
                title="Implement feature A",
                description="Feature A description",
                status=TaskmasterTaskStatus.TODO,
                priority=5,
            ),
            TaskmasterTask(
                id="tm-002",
                taskmaster_id="tm-002",
                title="Fix bug B",
                description="Bug B description",
                status=TaskmasterTaskStatus.IN_PROGRESS,
                priority=8,
            ),
        ]

        # Mock the API client
        mock_client = AsyncMock()
        mock_client.fetch_tasks.return_value = taskmaster_tasks

        async def test_sync():
            with patch(
                "autoflow.agents.taskmaster.TaskmasterAPIClient",
                return_value=mock_client,
            ) as mock_api:
                mock_api.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_api.return_value.__aexit__ = AsyncMock()

                # Sync from Taskmaster
                autoflow_tasks = await adapter.sync_from_taskmaster()

                # Verify
                assert len(autoflow_tasks) == 2, "Should import 2 tasks"
                assert autoflow_tasks[0].title == "Implement feature A"
                assert autoflow_tasks[0].status == TaskStatus.PENDING
                assert autoflow_tasks[1].title == "Fix bug B"
                assert autoflow_tasks[1].status == TaskStatus.IN_PROGRESS
                assert autoflow_tasks[0].priority == 5
                assert autoflow_tasks[1].priority == 8

        asyncio.run(test_sync())
        print_success("Taskmaster tasks sync to Autoflow as specs/tasks")
        return True

    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def verify_criterion_2() -> bool:
    """Verify: Autoflow execution state syncs back to Taskmaster"""
    print_info("Criterion 2: Autoflow execution state syncs back to Taskmaster")

    try:
        # Create adapter
        config = TaskmasterConfig(
            api_base_url="https://api.taskmaster.ai",
            api_key="test-key",
        )
        adapter = TaskmasterAdapter(config)

        # Create Autoflow tasks with various states
        autoflow_tasks = [
            Task(
                id="af-001",
                title="Implement feature A",
                description="Feature A description",
                status=TaskStatus.PENDING,
                priority=5,
            ),
            Task(
                id="af-002",
                title="Fix bug B",
                description="Bug B description",
                status=TaskStatus.IN_PROGRESS,
                priority=8,
            ),
            Task(
                id="af-003",
                title="Complete feature C",
                description="Feature C description",
                status=TaskStatus.COMPLETED,
                priority=3,
            ),
        ]

        # Mock the API client
        created_taskmaster_tasks = [
            TaskmasterTask(
                id="tm-001",
                taskmaster_id="tm-001",
                title="Implement feature A",
                description="Feature A description",
                status=TaskmasterTaskStatus.TODO,
                priority=5,
            ),
            TaskmasterTask(
                id="tm-002",
                taskmaster_id="tm-002",
                title="Fix bug B",
                description="Bug B description",
                status=TaskmasterTaskStatus.IN_PROGRESS,
                priority=8,
            ),
            TaskmasterTask(
                id="tm-003",
                taskmaster_id="tm-003",
                title="Complete feature C",
                description="Feature C description",
                status=TaskmasterTaskStatus.DONE,
                priority=3,
            ),
        ]

        mock_client = AsyncMock()
        mock_client.create_task.side_effect = created_taskmaster_tasks

        async def test_sync():
            with patch(
                "autoflow.agents.taskmaster.TaskmasterAPIClient",
                return_value=mock_client,
            ) as mock_api:
                mock_api.return_value.__aenter__ = AsyncMock(return_value=mock_client)
                mock_api.return_value.__aexit__ = AsyncMock()

                # Sync to Taskmaster
                taskmaster_tasks = await adapter.sync_to_taskmaster(autoflow_tasks)

                # Verify
                assert len(taskmaster_tasks) == 3, "Should export 3 tasks"
                assert taskmaster_tasks[0].status == TaskmasterTaskStatus.TODO
                assert taskmaster_tasks[1].status == TaskmasterTaskStatus.IN_PROGRESS
                assert taskmaster_tasks[2].status == TaskmasterTaskStatus.DONE

        asyncio.run(test_sync())
        print_success("Autoflow execution state syncs back to Taskmaster")
        return True

    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def verify_criterion_3() -> bool:
    """Verify: Task priorities are preserved across sync"""
    print_info("Criterion 3: Task priorities are preserved across sync")

    try:
        # Create adapter
        config = TaskmasterConfig(
            api_base_url="https://api.taskmaster.ai",
            api_key="test-key",
        )
        adapter = TaskmasterAdapter(config)

        # Test round-trip priority preservation
        original_priorities = [1, 5, 10, 7, 3]

        # Create Autoflow tasks
        autoflow_tasks = [
            Task(
                id=f"af-{i:03d}",
                title=f"Task {i}",
                description=f"Description {i}",
                status=TaskStatus.PENDING,
                priority=priority,
            )
            for i, priority in enumerate(original_priorities)
        ]

        # Mock export to Taskmaster
        taskmaster_tasks = [
            TaskmasterTask(
                id=f"tm-{i:03d}",
                taskmaster_id=f"tm-{i:03d}",
                title=f"Task {i}",
                description=f"Description {i}",
                status=TaskmasterTaskStatus.TODO,
                priority=priority,
            )
            for i, priority in enumerate(original_priorities)
        ]

        mock_client_to = AsyncMock()
        mock_client_to.create_task.side_effect = taskmaster_tasks

        async def test_round_trip():
            # Export to Taskmaster
            with patch(
                "autoflow.agents.taskmaster.TaskmasterAPIClient",
                return_value=mock_client_to,
            ) as mock_api:
                mock_api.return_value.__aenter__ = AsyncMock(return_value=mock_client_to)
                mock_api.return_value.__aexit__ = AsyncMock()

                exported_tasks = await adapter.sync_to_taskmaster(autoflow_tasks)

                # Verify priorities in exported tasks
                exported_priorities = [t.priority for t in exported_tasks]
                assert exported_priorities == original_priorities, \
                    f"Priorities mismatch on export: {exported_priorities} != {original_priorities}"

            # Import back from Taskmaster
            mock_client_from = AsyncMock()
            mock_client_from.fetch_tasks.return_value = exported_tasks

            with patch(
                "autoflow.agents.taskmaster.TaskmasterAPIClient",
                return_value=mock_client_from,
            ) as mock_api:
                mock_api.return_value.__aenter__ = AsyncMock(return_value=mock_client_from)
                mock_api.return_value.__aexit__ = AsyncMock()

                imported_tasks = await adapter.sync_from_taskmaster()

                # Verify priorities in imported tasks
                imported_priorities = [t.priority for t in imported_tasks]
                assert imported_priorities == original_priorities, \
                    f"Priorities mismatch on import: {imported_priorities} != {original_priorities}"

        asyncio.run(test_round_trip())
        print_success("Task priorities are preserved across sync")
        return True

    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def verify_criterion_4() -> bool:
    """Verify: Conflict resolution handles concurrent updates"""
    print_info("Criterion 4: Conflict resolution handles concurrent updates")

    try:
        # Create adapter with conflict resolver
        config = TaskmasterConfig(
            api_base_url="https://api.taskmaster.ai",
            api_key="test-key",
        )
        resolver = ConflictResolver(
            strategy=ConflictResolutionStrategy.LAST_WRITE_WINS
        )
        adapter = TaskmasterAdapter(config, conflict_resolver=resolver)

        # Create conflicting tasks
        autoflow_task = Task(
            id="af-conflict-001",
            title="Original Title",
            description="Original description",
            status=TaskStatus.PENDING,
            priority=5,
            updated_at=datetime(2026, 3, 8, 9, 0, 0),
        )

        taskmaster_task = TaskmasterTask(
            id="tm-conflict-001",
            title="Modified Title in Taskmaster",
            description="Modified description in Taskmaster",
            status=TaskmasterTaskStatus.DONE,
            priority=8,
            updated_at=datetime(2026, 3, 8, 10, 0, 0),
        )

        # Test conflict detection
        conflicts = adapter._detect_conflicts(autoflow_task, taskmaster_task)

        assert len(conflicts) > 0, "Should detect conflicts"
        assert any(c.conflict_type == ConflictType.TITLE for c in conflicts), \
            "Should detect title conflict"
        assert any(c.conflict_type == ConflictType.STATUS for c in conflicts), \
            "Should detect status conflict"
        assert any(c.conflict_type == ConflictType.PRIORITY for c in conflicts), \
            "Should detect priority conflict"

        # Test conflict resolution with LAST_WRITE_WINS
        resolved_task, resolved_conflicts = adapter._resolve_conflicts(
            autoflow_task, taskmaster_task
        )

        assert len(resolved_conflicts) > 0, "Should return resolved conflicts"
        assert resolved_task.title == "Modified Title in Taskmaster", \
            "Should use Taskmaster's newer title"
        assert resolved_task.status == TaskStatus.COMPLETED, \
            "Should use Taskmaster's newer status"
        assert resolved_task.priority == 8, \
            "Should use Taskmaster's newer priority"

        # Test AUTOFLOW_WINS strategy
        resolved_task_autoflow, _ = adapter._resolve_conflicts(
            autoflow_task, taskmaster_task,
            strategy=ConflictResolutionStrategy.AUTOFLOW_WINS
        )

        assert resolved_task_autoflow.title == "Original Title", \
            "AUTOFLOW_WINS should keep Autoflow's title"
        assert resolved_task_autoflow.status == TaskStatus.PENDING, \
            "AUTOFLOW_WINS should keep Autoflow's status"

        # Test TASKMASTER_WINS strategy
        resolved_task_taskmaster, _ = adapter._resolve_conflicts(
            autoflow_task, taskmaster_task,
            strategy=ConflictResolutionStrategy.TASKMASTER_WINS
        )

        assert resolved_task_taskmaster.title == "Modified Title in Taskmaster", \
            "TASKMASTER_WINS should use Taskmaster's title"
        assert resolved_task_taskmaster.status == TaskStatus.COMPLETED, \
            "TASKMASTER_WINS should use Taskmaster's status"

        print_success("Conflict resolution handles concurrent updates")
        return True

    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def verify_criterion_5() -> bool:
    """Verify: Integration works with Taskmaster API authentication"""
    print_info("Criterion 5: Integration works with Taskmaster API authentication")

    try:
        # Test configuration with API key
        config = TaskmasterConfig(
            api_base_url="https://api.taskmaster.ai",
            api_key="test-api-key-12345",
        )

        # Verify configuration is properly set
        assert config.api_base_url == "https://api.taskmaster.ai"
        assert config.api_key == "test-api-key-12345"
        assert config.is_configured, "Should be configured with API key"

        # Verify auth headers are generated
        auth_headers = config.get_auth_headers()
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"] == "Bearer test-api-key-12345"

        # Test API client initialization
        client = TaskmasterAPIClient(config)
        assert client.config.api_key == "test-api-key-12345"

        # Test adapter initialization
        adapter = TaskmasterAdapter(config)
        assert adapter.config.api_key == "test-api-key-12345"

        # Test that operations fail without API key
        try:
            config_no_key = TaskmasterConfig(
                api_base_url="https://api.taskmaster.ai",
                api_key="",  # Empty API key
            )
            adapter_no_key = TaskmasterAdapter(config_no_key)

            async def test_no_key():
                # Should raise ValueError when not configured (no API key)
                await adapter_no_key.sync_from_taskmaster()

            asyncio.run(test_no_key())
            print_error("Should have raised ValueError without API key")
            return False

        except ValueError as e:
            # Expected error - should mention api_key
            assert "api_key" in str(e).lower() or "configured" in str(e).lower()

        # Test that operations fail when disabled
        try:
            config_disabled = TaskmasterConfig(
                api_base_url="https://api.taskmaster.ai",
                api_key="test-key",
                enabled=False,  # Explicitly disabled
            )
            adapter_disabled = TaskmasterAdapter(config_disabled)

            async def test_disabled():
                # Should raise ValueError when disabled
                await adapter_disabled.sync_from_taskmaster()

            asyncio.run(test_disabled())
            print_error("Should have raised ValueError when disabled")
            return False

        except ValueError as e:
            # Expected error - should mention enabled
            assert "enabled" in str(e).lower()

        print_success("Integration works with Taskmaster API authentication")
        return True

    except Exception as e:
        print_error(f"Failed: {e}")
        return False


def main() -> int:
    """Run all verification tests."""
    print("\n" + "=" * 70)
    print("Taskmaster AI Integration - Acceptance Criteria Verification")
    print("=" * 70 + "\n")

    results = {
        "Criterion 1": verify_criterion_1(),
        "Criterion 2": verify_criterion_2(),
        "Criterion 3": verify_criterion_3(),
        "Criterion 4": verify_criterion_4(),
        "Criterion 5": verify_criterion_5(),
    }

    print("\n" + "=" * 70)
    print("VERIFICATION RESULTS")
    print("=" * 70 + "\n")

    all_passed = True
    for criterion, passed in results.items():
        status = f"{GREEN}PASSED{RESET}" if passed else f"{RED}FAILED{RESET}"
        print(f"{criterion}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print(f"{GREEN}ALL ACCEPTANCE CRITERIA VERIFIED{RESET}")
        print("=" * 70 + "\n")
        return 0
    else:
        print(f"{RED}SOME ACCEPTANCE CRITERIA NOT MET{RESET}")
        print("=" * 70 + "\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
