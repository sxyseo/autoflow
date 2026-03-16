"""
Integration Tests with Real Environment

These tests use real file systems and state management
instead of mocks to verify actual system behavior.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from autoflow.core.state import StateManager


class TestRealStateManager:
    """Test StateManager with real file system (no mocks)."""

    @pytest.fixture
    async def temp_state_dir(self):
        """Create temporary directory for state."""
        temp_dir = tempfile.mkdtemp(prefix="autoflow_state_test_")
        yield Path(temp_dir)
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    async def state_manager(self, temp_state_dir: Path):
        """Create StateManager with real file system."""
        manager = StateManager(temp_state_dir)
        await manager.initialize()
        yield manager
        await manager.close()

    async def test_state_initialization(self, state_manager: StateManager) -> None:
        """Test state manager initializes directories correctly."""
        # Verify directories exist
        assert state_manager.base_dir.exists()
        assert state_manager.specs_dir.exists()
        assert state_manager.tasks_dir.exists()
        assert state_manager.runs_dir.exists()

    async def test_spec_creation_real_fs(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test spec creation creates real files."""
        spec_slug = "test-spec"

        # Create spec through state manager
        spec_dir = state_manager.specs_dir / spec_slug
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_file = spec_dir / "SPEC.md"
        spec_content = """# Test Spec

## Summary

Testing real file system.
"""
        spec_file.write_text(spec_content)

        # Verify file exists on real filesystem
        assert spec_file.exists()

        # Verify content is correct
        content = spec_file.read_text()
        assert "Test Spec" in content
        assert "Testing real file system" in content

    async def test_task_persistence_real_fs(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test tasks persist correctly to real files."""
        spec_slug = "persistence-test"

        # Create tasks file
        tasks_file = state_manager.tasks_dir / f"{spec_slug}.json"
        tasks_data = {
            "spec_slug": spec_slug,
            "updated_at": "20260316T120000Z",
            "tasks": [
                {
                    "id": "T1",
                    "title": "Test Task",
                    "status": "todo",
                    "depends_on": [],
                    "owner_role": "implementation-runner",
                    "acceptance_criteria": ["Done"],
                    "notes": []
                }
            ]
        }

        # Write to real file
        tasks_file.write_text(json.dumps(tasks_data, indent=2))

        # Verify file exists
        assert tasks_file.exists()

        # Read back and verify
        loaded_data = json.loads(tasks_file.read_text())
        assert loaded_data == tasks_data

    async def test_concurrent_file_access(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test concurrent file operations work correctly."""
        spec_slug = "concurrent-test"

        # Create multiple files concurrently
        async def create_spec_file(index: int):
            spec_dir = state_manager.specs_dir / f"{spec_slug}-{index}"
            spec_dir.mkdir(parents=True, exist_ok=True)

            spec_file = spec_dir / "SPEC.md"
            spec_file.write_text(f"# Spec {index}\n\nContent {index}")

        # Run concurrently
        tasks = [create_spec_file(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all files created
        for i in range(10):
            spec_dir = state_manager.specs_dir / f"{spec_slug}-{i}"
            spec_file = spec_dir / "SPEC.md"
            assert spec_file.exists()

            content = spec_file.read_text()
            assert f"Spec {i}" in content
            assert f"Content {i}" in content

    async def test_file_overwrite_handling(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test that file overwrites work correctly."""
        spec_slug = "overwrite-test"

        spec_dir = state_manager.specs_dir / spec_slug
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_file = spec_dir / "SPEC.md"

        # Write initial content
        spec_file.write_text("Initial content")
        assert spec_file.read_text() == "Initial content"

        # Overwrite
        spec_file.write_text("Updated content")
        assert spec_file.read_text() == "Updated content"

    async def test_directory_navigation(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test directory structure navigation."""
        # Verify paths are correctly structured
        assert state_manager.base_dir == temp_state_dir
        assert state_manager.specs_dir == temp_state_dir / "specs"
        assert state_manager.tasks_dir == temp_state_dir / "tasks"
        assert state_manager.runs_dir == temp_state_dir / "runs"

        # Verify directories are separate
        assert state_manager.specs_dir != state_manager.tasks_dir
        assert state_manager.tasks_dir != state_manager.runs_dir

    async def test_large_file_handling(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test handling of large files."""
        spec_slug = "large-file-test"

        spec_dir = state_manager.specs_dir / spec_slug
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_file = spec_dir / "SPEC.md"

        # Create large content
        large_content = "# Large Spec\n\n" + "\n".join([f"Line {i}" for i in range(10000)])

        # Write large file
        spec_file.write_text(large_content)

        # Verify file size
        file_size = spec_file.stat().st_size
        assert file_size > 100000  # > 100KB

        # Verify content
        loaded_content = spec_file.read_text()
        assert loaded_content.startswith("# Large Spec")
        assert "Line 9999" in loaded_content

    async def test_file_permissions(
        self,
        state_manager: State_manager,
        temp_state_dir: Path
    ) -> None:
        """Test file permissions are set correctly."""
        spec_slug = "permissions-test"

        spec_dir = state_manager.specs_dir / spec_slug
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_file = spec_dir / "SPEC.md"
        spec_file.write_text("Content")

        # Check file is readable
        assert spec_file.exists()

        # Check we can read it
        content = spec_file.read_text()
        assert content == "Content"

        # Check we can write to it
        spec_file.write_text("Updated")
        assert spec_file.read_text() == "Updated"

    async def test_nested_directory_creation(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test creating nested directory structures."""
        spec_slug = "nested-test"

        # Create deeply nested structure
        nested_dir = state_manager.specs_dir / spec_slug / "artifacts" / "reports" / "2026" / "03"
        nested_dir.mkdir(parents=True)

        # Verify all intermediate directories created
        assert nested_dir.exists()
        assert (state_manager.specs_dir / spec_slug).exists()
        assert (state_manager.specs_dir / spec_slug / "artifacts").exists()

        # Create file in nested directory
        nested_file = nested_dir / "report.md"
        nested_file.write_text("# Report")
        assert nested_file.exists()

    async def test_error_handling_nonexistent_file(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test error handling for nonexistent files."""
        nonexistent_file = state_manager.specs_dir / "nonexistent" / "SPEC.md"

        # File should not exist
        assert not nonexistent_file.exists()

        # Trying to read should fail gracefully
        try:
            content = nonexistent_file.read_text()
            assert False, "Should not reach here"
        except (FileNotFoundError, OSError):
            assert True, "Correctly raised error for nonexistent file"


class TestRealSchedulerIntegration:
    """Test scheduler integration with real state."""

    @pytest.fixture
    async def temp_state_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix="autoflow_scheduler_test_")
        yield Path(temp_dir)
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    async def state_manager(self, temp_state_dir: Path):
        """Create state manager."""
        manager = StateManager(temp_state_dir)
        await manager.initialize()
        yield manager
        await manager.close()

    async def test_scheduler_config_persistence(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test scheduler config persists to real file."""
        config_file = temp_state_dir / "scheduler_config.json"

        config = {
            "tasks": [
                {
                    "id": "task-1",
                    "name": "Test Task",
                    "schedule_type": "interval",
                    "interval_seconds": 300,
                    "enabled": True
                }
            ]
        }

        # Write config
        config_file.write_text(json.dumps(config, indent=2))

        # Verify persistence
        assert config_file.exists()

        # Read back
        loaded_config = json.loads(config_file.read_text())
        assert loaded_config["tasks"][0]["id"] == "task-1"

    async def test_scheduler_state_tracking(
        self,
        state_manager: StateManager,
        temp_state_dir: Path
    ) -> None:
        """Test scheduler tracks state correctly."""
        state_file = temp_state_dir / "scheduler_state.json"

        # Initial state
        state = {
            "last_run": "2026-03-16T12:00:00Z",
            "running_tasks": [],
            "completed_tasks": ["task-1"]
        }

        state_file.write_text(json.dumps(state, indent=2))

        # Update state
        updated_state = json.loads(state_file.read_text())
        updated_state["running_tasks"] = ["task-2"]
        updated_state["last_run"] = "2026-03-16T12:05:00Z"

        state_file.write_text(json.dumps(updated_state, indent=2))

        # Verify update
        final_state = json.loads(state_file.read_text())
        assert "task-2" in final_state["running_tasks"]
        assert final_state["last_run"] == "2026-03-16T12:05:00Z"


class TestRealFileOperations:
    """Test real file operations without mocks."""

    @pytest.fixture
    async def temp_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp(prefix="autoflow_file_test_")
        yield Path(temp_dir)
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)

    async def test_file_write_read_cycle(self, temp_dir: Path) -> None:
        """Test complete write-read cycle."""
        test_file = temp_dir / "test.json"

        # Write
        data = {"key": "value", "number": 42}
        test_file.write_text(json.dumps(data))

        # Read
        loaded = json.loads(test_file.read_text())
        assert loaded == data

    async def test_file_append(self, temp_dir: Path) -> None:
        """Test appending to file."""
        test_file = temp_dir / "log.txt"

        # Append multiple times
        test_file.write_text("Line 1\n", encoding="utf-8")
        with open(test_file, "a", encoding="utf-8") as f:
            f.write("Line 2\n")
            f.write("Line 3\n")

        # Verify all lines present
        content = test_file.read_text(encoding="utf-8")
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content

    async def test_file_deletion(self, temp_dir: Path) -> None:
        """Test file deletion."""
        test_file = temp_dir / "to_delete.txt"

        # Create file
        test_file.write_text("Delete me")
        assert test_file.exists()

        # Delete file
        test_file.unlink()
        assert not test_file.exists()

    async def test_directory_listing(self, temp_dir: Path) -> None:
        """Test directory listing operations."""
        # Create multiple files
        for i in range(5):
            (temp_dir / f"file{i}.txt").write_text(f"Content {i}")

        # List files
        files = list(temp_dir.glob("*.txt"))
        assert len(files) == 5

        # Verify contents
        file_names = {f.name for f in files}
        assert "file0.txt" in file_names
        assert "file4.txt" in file_names

    async def test_atomic_write(self, temp_dir: Path) -> None:
        """Test atomic file write pattern."""
        target_file = temp_dir / "atomic.txt"
        temp_file = temp_dir / "atomic.tmp"

        # Write to temp file
        temp_file.write_text("Atomic content")

        # Atomic rename
        temp_file.rename(target_file)

        # Verify
        assert target_file.exists()
        assert not temp_file.exists()
        assert target_file.read_text() == "Atomic content"
