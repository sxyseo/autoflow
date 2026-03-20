"""
Integration Tests for Context Injection in Prompts

Tests the complete context injection flow from memory retrieval
to prompt building, ensuring relevant context is properly injected
into agent prompts.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoflow.memory import MemoryManager
from autoflow.memory.models import (
    EnhancedMemory,
    MemoryScope,
    MemoryType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_consolidation_file(tmp_path):
    """Create a temporary consolidation file (empty)."""
    consolidation_path = tmp_path / "consolidation.json"
    data = {
        "memories": {},
        "patterns": {},
        "conventions": {},
    }
    consolidation_path.write_text(json.dumps(data))
    return consolidation_path


@pytest.fixture
def memory_manager_with_context(temp_consolidation_file):
    """
    Create MemoryManager with test context data.

    Sets up memories that will be retrieved during context injection,
    including both spec-scoped and global memories with different
    relevance scores.

    Note: Due to the format mismatch between how consolidator saves
    memories (as dict) and how search loads them (expecting list),
    we manually add memories to both consolidator and search to match
    the pattern used in test_memory_manager.py.
    """
    manager = MemoryManager(
        consolidation_path=temp_consolidation_file,
        enable_embeddings=False,
    )

    # Add test memories with different scopes and types
    memories = [
        EnhancedMemory(
            id="global-1",
            content="Use pytest for testing with async fixtures",
            memory_type=MemoryType.CONVENTION,
            scope=MemoryScope.GLOBAL,
            importance=0.9,
            tags=["testing", "pytest"],
        ),
        EnhancedMemory(
            id="global-2",
            content="Authentication modules should use JWT tokens",
            memory_type=MemoryType.STRATEGY,
            scope=MemoryScope.GLOBAL,
            importance=0.8,
            tags=["authentication", "security"],
        ),
        EnhancedMemory(
            id="spec-1",
            content="This spec requires task-based execution model",
            memory_type=MemoryType.PATTERN,
            scope=MemoryScope.SPEC,
            spec_id="test-spec",
            importance=0.7,
            tags=["execution", "tasks"],
        ),
        EnhancedMemory(
            id="spec-2",
            content="Error handling should use custom exceptions",
            memory_type=MemoryType.LESSON,
            scope=MemoryScope.SPEC,
            spec_id="test-spec",
            importance=0.6,
            tags=["error-handling"],
        ),
    ]

    # Add memories to both consolidator and search
    # This matches the pattern from test_memory_manager.py fixture
    for mem in memories:
        manager.consolidator.memories[mem.id] = mem
        manager.search.memories[mem.id] = mem

    # Save to persist the data (but don't reload since it won't work)
    manager.consolidator._save_consolidation()

    return manager


@pytest.fixture
def temp_run_dir(tmp_path):
    """Create a temporary run directory for testing."""
    run_dir = tmp_path / "runs" / "test-run-001"
    run_dir.mkdir(parents=True)
    return run_dir


# ============================================================================
# Context Injection Tests
# ============================================================================


class TestContextRetrieval:
    """Test context retrieval for runs."""

    async def test_get_context_for_run(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test retrieving context for a specific run.

        Verifies that get_context_for_run returns relevant memories
        from both spec and global scopes.
        """
        # Get context for a task - use query that matches memory content
        context = memory_manager_with_context.get_context_for_run(
            task_id="pytest testing task",  # Has word overlap with memories
            spec_id="test-spec",
            max_items=5,
            relevance_threshold=0.0,
        )

        # Verify context is a list
        assert isinstance(context, list)

        # Verify we have context items
        assert len(context) > 0

        # Verify each context item has required fields
        for item in context:
            assert "content" in item
            assert "score" in item
            assert "scope" in item
            assert "type" in item
            assert "tags" in item

            # Verify types
            assert isinstance(item["content"], str)
            assert isinstance(item["score"], float)
            assert isinstance(item["scope"], str)
            assert isinstance(item["type"], str)
            assert isinstance(item["tags"], list)

    async def test_context_includes_spec_scoped_memories(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test that spec-scoped memories are included in context.

        When retrieving context for a spec, spec-scoped memories
        should be included in the results.
        """
        context = memory_manager_with_context.get_context_for_run(
            task_id="execution pattern task",  # Matches spec memory content
            spec_id="test-spec",
            include_spec=True,
            include_global=False,
        )

        # Should have spec-scoped memories
        assert len(context) > 0

        # All items should have scope "spec"
        for item in context:
            assert item["scope"] == "spec"

    async def test_context_includes_global_memories(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test that global memories are included in context.

        When retrieving context, global/project memories should be
        included in the results.
        """
        context = memory_manager_with_context.get_context_for_run(
            task_id="authentication testing",  # Matches global memory content
            spec_id="test-spec",
            include_spec=False,
            include_global=True,
        )

        # Should have global memories
        assert len(context) > 0

        # All items should have scope "global"
        for item in context:
            assert item["scope"] == "global"

    async def test_context_respects_max_items_limit(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test that context retrieval respects max_items limit.

        When requesting a maximum number of items, the results
        should be limited to that number.
        """
        max_items = 2
        context = memory_manager_with_context.get_context_for_run(
            task_id="testing authentication error",  # Matches multiple memories
            spec_id="test-spec",
            max_items=max_items,
        )

        # Should not exceed max_items
        assert len(context) <= max_items

    async def test_context_scores_are_valid(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test that relevance scores are in valid range.

        All relevance scores should be between 0.0 and 1.0.
        """
        context = memory_manager_with_context.get_context_for_run(
            task_id="pytest testing authentication",  # Matches memory content
            spec_id="test-spec",
        )

        # Verify scores are in valid range
        for item in context:
            score = item["score"]
            assert 0.0 <= score <= 1.0, f"Score {score} is not in valid range"


class TestContextInjectionMetadata:
    """Test context_injected.json metadata creation."""

    async def test_context_injected_json_structure(
        self,
        memory_manager_with_context: MemoryManager,
        temp_run_dir: Path,
    ) -> None:
        """
        Test that context_injected.json has correct structure.

        The metadata file should contain information about what
        context was injected into the prompt.
        """
        # Simulate context retrieval
        semantic_items = memory_manager_with_context.get_context_for_run(
            task_id="task-testing",
            spec_id="test-spec",
        )

        # Build metadata as done in autoflow_cli.py
        context_injected = {
            "memory_scopes": ["spec", "global"],
            "semantic_context_available": True,
            "semantic_context_items": [
                {
                    "content": item.get("content", "")[:100],
                    "score": item.get("score", 0.0),
                    "scope": item.get("scope", "global"),
                    "type": item.get("type", "context"),
                }
                for item in semantic_items
            ],
            "semantic_context_count": len(semantic_items),
        }

        # Write to file
        context_injected_path = temp_run_dir / "context_injected.json"
        context_injected_path.write_text(json.dumps(context_injected, indent=2))

        # Verify file exists
        assert context_injected_path.exists()

        # Verify structure
        loaded_metadata = json.loads(context_injected_path.read_text())

        # Check required fields
        assert "memory_scopes" in loaded_metadata
        assert "semantic_context_available" in loaded_metadata
        assert "semantic_context_items" in loaded_metadata
        assert "semantic_context_count" in loaded_metadata

        # Verify types
        assert isinstance(loaded_metadata["memory_scopes"], list)
        assert isinstance(loaded_metadata["semantic_context_available"], bool)
        assert isinstance(loaded_metadata["semantic_context_items"], list)
        assert isinstance(loaded_metadata["semantic_context_count"], int)

        # Verify context items structure
        for item in loaded_metadata["semantic_context_items"]:
            assert "content" in item
            assert "score" in item
            assert "scope" in item
            assert "type" in item

    async def test_context_injected_count_matches_items(
        self,
        memory_manager_with_context: MemoryManager,
        temp_run_dir: Path,
    ) -> None:
        """
        Test that semantic_context_count matches actual items count.

        The count field should accurately reflect the number of
        context items injected.
        """
        semantic_items = memory_manager_with_context.get_context_for_run(
            task_id="task",
            spec_id="test-spec",
        )

        context_injected = {
            "memory_scopes": ["spec", "global"],
            "semantic_context_available": True,
            "semantic_context_items": [
                {
                    "content": item.get("content", "")[:100],
                    "score": item.get("score", 0.0),
                    "scope": item.get("scope", "global"),
                    "type": item.get("type", "context"),
                }
                for item in semantic_items
            ],
            "semantic_context_count": len(semantic_items),
        }

        context_injected_path = temp_run_dir / "context_injected.json"
        context_injected_path.write_text(json.dumps(context_injected, indent=2))

        # Load and verify count matches
        loaded_metadata = json.loads(context_injected_path.read_text())

        assert (
            loaded_metadata["semantic_context_count"]
            == len(loaded_metadata["semantic_context_items"])
        )


class TestContextInPromptBuilding:
    """Test context integration into prompt building."""

    async def test_context_formatting_for_prompt(
        self,
        memory_manager_with_context: MemoryManager,
    ) -> None:
        """
        Test that context is formatted correctly for prompt injection.

        Context items should be formatted in a way that can be
        directly injected into agent prompts.
        """
        context = memory_manager_with_context.get_context_for_run(
            task_id="testing authentication",  # Matches memory content
            spec_id="test-spec",
        )

        # Format as would be done for prompt injection
        context_sections = []
        for item in context:
            section = f"**[{item['scope'].upper()}] {item['type'].upper()}** (relevance: {item['score']:.2f})\n"
            section += f"{item['content']}\n"
            if item['tags']:
                section += f"Tags: {', '.join(item['tags'])}\n"
            context_sections.append(section)

        context_text = "\n".join(context_sections)

        # Verify formatting
        assert isinstance(context_text, str)
        assert len(context_text) > 0

        # Verify structure markers are present
        assert "**[" in context_text  # Scope marker
        assert "**" in context_text  # Type marker
        assert "relevance:" in context_text  # Score marker

    async def test_empty_context_handling(
        self,
        temp_consolidation_file: Path,
    ) -> None:
        """
        Test handling when no context is available.

        When no memories match, the system should handle gracefully
        and return empty context without errors.
        """
        # Create empty memory manager
        manager = MemoryManager(
            consolidation_path=temp_consolidation_file,
            enable_embeddings=False,
        )

        # Get context for non-existent task
        context = manager.get_context_for_run(
            task_id="non-existent-task",
            spec_id="non-existent-spec",
        )

        # Should return empty list
        assert isinstance(context, list)
        assert len(context) == 0

        # Should not raise errors when formatting
        context_sections = []
        for item in context:
            context_sections.append(str(item))

        assert len(context_sections) == 0


class TestEndToEndContextInjection:
    """Test complete end-to-end context injection flow."""

    async def test_complete_context_injection_flow(
        self,
        memory_manager_with_context: MemoryManager,
        temp_run_dir: Path,
    ) -> None:
        """
        Test complete flow from context retrieval to metadata file.

        This simulates what happens when creating a run with context
        injection enabled.
        """
        # Step 1: Retrieve context
        context_items = memory_manager_with_context.get_context_for_run(
            task_id="pytest testing authentication execution",  # Matches multiple memories
            spec_id="test-spec",
            max_items=5,
        )

        # Step 2: Build context_injected metadata
        context_injected = {
            "memory_scopes": ["spec", "global"],
            "semantic_context_available": True,
            "semantic_context_items": [
                {
                    "content": item.get("content", "")[:100],
                    "score": item.get("score", 0.0),
                    "scope": item.get("scope", "global"),
                    "type": item.get("type", "context"),
                }
                for item in context_items
            ],
            "semantic_context_count": len(context_items),
        }

        # Step 3: Write metadata file
        context_injected_path = temp_run_dir / "context_injected.json"
        context_injected_path.write_text(json.dumps(context_injected, indent=2))

        # Step 4: Create run metadata
        run_metadata = {
            "id": "test-run-001",
            "spec": "test-spec",
            "task": "task-testing-implementation",
            "context_injected": True,
            "semantic_context_count": len(context_items),
        }

        run_metadata_path = temp_run_dir / "run.json"
        run_metadata_path.write_text(json.dumps(run_metadata, indent=2))

        # Step 5: Verify all artifacts
        assert context_injected_path.exists()
        assert run_metadata_path.exists()

        # Verify metadata content
        loaded_context = json.loads(context_injected_path.read_text())
        loaded_run = json.loads(run_metadata_path.read_text())

        # Verify context was injected
        assert loaded_context["semantic_context_available"] is True
        assert loaded_context["semantic_context_count"] > 0
        assert loaded_run["context_injected"] is True

        # Verify scores are present and valid
        for item in loaded_context["semantic_context_items"]:
            assert 0.0 <= item["score"] <= 1.0

    async def test_context_injection_with_scopes_disabled(
        self,
        memory_manager_with_context: MemoryManager,
        temp_run_dir: Path,
    ) -> None:
        """
        Test context injection when specific scopes are disabled.

        When agent config disables certain memory scopes, those
        should not be included in the injected context.
        """
        # Simulate agent with only global scope enabled
        memory_scopes = ["global"]  # Only global, no spec

        # Get context with only global scope
        context_items = memory_manager_with_context.get_context_for_run(
            task_id="pytest testing",  # Matches global memory content
            spec_id="test-spec",
            include_spec=False,  # Spec disabled
            include_global=True,  # Global enabled
        )

        # Build metadata
        context_injected = {
            "memory_scopes": memory_scopes,
            "semantic_context_available": True,
            "semantic_context_items": [
                {
                    "content": item.get("content", "")[:100],
                    "score": item.get("score", 0.0),
                    "scope": item.get("scope", "global"),
                    "type": item.get("type", "context"),
                }
                for item in context_items
            ],
            "semantic_context_count": len(context_items),
        }

        # Verify only global items are present
        for item in context_injected["semantic_context_items"]:
            assert item["scope"] == "global"
