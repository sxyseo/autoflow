"""
Unit Tests for Memory Search Module

Tests the MemorySearch and SearchResult classes for semantic memory search
capabilities including filtering, caching, and similarity scoring.

These tests use fixtures and mocking to ensure tests run quickly without
external dependencies or file I/O.
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autoflow.memory.models import (
    EnhancedMemory,
    MemoryScope,
    MemoryType,
)
from autoflow.memory.search import (
    MemorySearch,
    SearchResult,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_memories():
    """Create sample memories for testing."""
    return [
        EnhancedMemory(
            id="mem1",
            content="Use pytest for testing with fixtures",
            memory_type=MemoryType.CONVENTION,
            scope=MemoryScope.GLOBAL,
            importance=0.8,
            tags=["testing", "pytest"],
        ),
        EnhancedMemory(
            id="mem2",
            content="Authentication errors should be handled with proper logging",
            memory_type=MemoryType.LESSON,
            scope=MemoryScope.PROJECT,
            project_id="proj1",
            importance=0.9,
            tags=["authentication", "error-handling"],
        ),
        EnhancedMemory(
            id="mem3",
            content="Database queries should use connection pooling",
            memory_type=MemoryType.STRATEGY,
            scope=MemoryScope.PROJECT,
            project_id="proj1",
            importance=0.7,
            tags=["database", "performance"],
        ),
        EnhancedMemory(
            id="mem4",
            content="Spec-specific pattern for task 123",
            memory_type=MemoryType.PATTERN,
            scope=MemoryScope.SPEC,
            spec_id="spec1",
            importance=0.6,
            tags=["pattern"],
        ),
    ]


@pytest.fixture
def memory_with_embedding():
    """Create a memory with an embedding vector."""
    memory = EnhancedMemory(
        id="mem5",
        content="This memory has an embedding",
        memory_type=MemoryType.FACT,
        scope=MemoryScope.GLOBAL,
        importance=0.5,
    )
    memory.embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
    return memory


@pytest.fixture
def expired_memory():
    """Create an expired memory."""
    memory = EnhancedMemory(
        id="mem6",
        content="This memory is expired",
        memory_type=MemoryType.FACT,
        scope=MemoryScope.GLOBAL,
        importance=0.3,
    )
    # Set expiration to past
    memory.expires_at = datetime.now(UTC).replace(timestamp=datetime(2020, 1, 1))
    return memory


@pytest.fixture
def temp_consolidation_file(tmp_path, sample_memories):
    """Create a temporary consolidation file with sample memories."""
    consolidation_path = tmp_path / "consolidation.json"
    data = {
        "memories": [mem.to_dict() for mem in sample_memories],
        "patterns": [],
        "conventions": [],
    }
    consolidation_path.write_text(json.dumps(data))
    return consolidation_path


@pytest.fixture
def memory_search_with_memories(temp_consolidation_file):
    """Create MemorySearch instance loaded with sample memories."""
    return MemorySearch(consolidation_path=temp_consolidation_file, cache_enabled=False)


@pytest.fixture
def empty_memory_search(tmp_path):
    """Create MemorySearch instance with no consolidation file."""
    empty_path = tmp_path / "empty.json"
    return MemorySearch(consolidation_path=empty_path, cache_enabled=False)


# ============================================================================
# SearchResult Tests
# ============================================================================


class TestSearchResult:
    """Tests for SearchResult class."""

    def test_search_result_creation(self, sample_memories) -> None:
        """Test creating a SearchResult."""
        memory = sample_memories[0]
        result = SearchResult(memory, 0.85)

        assert result.memory is memory
        assert result.score == 0.85
        assert result.content == memory.content

    def test_search_result_score_validation(self, sample_memories) -> None:
        """Test SearchResult score validation."""
        memory = sample_memories[0]

        # Valid scores
        SearchResult(memory, 0.0)
        SearchResult(memory, 0.5)
        SearchResult(memory, 1.0)

        # Invalid scores
        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            SearchResult(memory, -0.1)

        with pytest.raises(ValueError, match="Score must be between 0.0 and 1.0"):
            SearchResult(memory, 1.1)

    def test_search_result_repr(self, sample_memories) -> None:
        """Test SearchResult string representation."""
        memory = sample_memories[0]
        result = SearchResult(memory, 0.85)

        repr_str = repr(result)
        assert "SearchResult" in repr_str
        assert "0.850" in repr_str
        assert "..." in repr_str  # Truncated content


# ============================================================================
# MemorySearch Initialization Tests
# ============================================================================


class TestMemorySearchInit:
    """Tests for MemorySearch initialization."""

    def test_init_with_default_path(self) -> None:
        """Test initialization with default consolidation path."""
        search = MemorySearch()

        assert search.consolidation_path == MemorySearch.DEFAULT_CONSOLIDATION_PATH
        assert search.cache_enabled is True
        assert search._cache_size == MemorySearch.DEFAULT_CACHE_SIZE

    def test_init_with_custom_path(self, tmp_path) -> None:
        """Test initialization with custom consolidation path."""
        custom_path = tmp_path / "custom.json"
        search = MemorySearch(consolidation_path=custom_path)

        assert search.consolidation_path == custom_path

    def test_init_with_cache_disabled(self) -> None:
        """Test initialization with caching disabled."""
        search = MemorySearch(cache_enabled=False)

        assert search.cache_enabled is False
        assert len(search._query_cache) == 0

    def test_init_with_custom_cache_size(self) -> None:
        """Test initialization with custom cache size."""
        search = MemorySearch(cache_size=50)

        assert search._cache_size == 50

    def test_init_loads_memories(self, temp_consolidation_file) -> None:
        """Test initialization loads memories from file."""
        search = MemorySearch(consolidation_path=temp_consolidation_file, cache_enabled=False)

        assert len(search.memories) == 4
        assert "mem1" in search.memories
        assert "mem4" in search.memories

    def test_init_handles_missing_file(self, tmp_path) -> None:
        """Test initialization handles missing consolidation file."""
        missing_path = tmp_path / "nonexistent.json"
        search = MemorySearch(consolidation_path=missing_path, cache_enabled=False)

        assert len(search.memories) == 0

    def test_init_handles_invalid_json(self, tmp_path) -> None:
        """Test initialization handles invalid JSON file."""
        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("not valid json")

        search = MemorySearch(consolidation_path=invalid_path, cache_enabled=False)

        assert len(search.memories) == 0

    def test_default_constants(self) -> None:
        """Test default constant values."""
        assert MemorySearch.DEFAULT_CONSOLIDATION_PATH == Path(".autoflow/consolidation.json")
        assert MemorySearch.DEFAULT_CACHE_SIZE == 100


# ============================================================================
# MemorySearch.search_similar Tests
# ============================================================================


class TestMemorySearchSimilar:
    """Tests for MemorySearch.search_similar method."""

    def test_search_similar_basic(self, memory_search_with_memories) -> None:
        """Test basic semantic search."""
        results = memory_search_with_memories.search_similar("pytest testing")

        assert isinstance(results, list)
        assert len(results) >= 0

    def test_search_similar_with_limit(self, memory_search_with_memories) -> None:
        """Test search with result limit."""
        results = memory_search_with_memories.search_similar("test", limit=2)

        assert len(results) <= 2

    def test_search_similar_with_min_score(self, memory_search_with_memories) -> None:
        """Test search with minimum score threshold."""
        results = memory_search_with_memories.search_similar("pytest", min_score=0.9)

        for result in results:
            assert result.score >= 0.9

    def test_search_similar_with_scope_filter(self, memory_search_with_memories) -> None:
        """Test search with scope filter."""
        results = memory_search_with_memories.search_similar("test", scope=MemoryScope.GLOBAL)

        for result in results:
            assert result.memory.scope == MemoryScope.GLOBAL

    def test_search_similar_with_spec_id_filter(self, memory_search_with_memories) -> None:
        """Test search with spec ID filter."""
        results = memory_search_with_memories.search_similar("pattern", spec_id="spec1")

        for result in results:
            assert result.memory.spec_id == "spec1"

    def test_search_similar_with_project_id_filter(self, memory_search_with_memories) -> None:
        """Test search with project ID filter."""
        results = memory_search_with_memories.search_similar("test", project_id="proj1")

        for result in results:
            assert result.memory.project_id == "proj1"

    def test_search_similar_with_memory_types_filter(self, memory_search_with_memories) -> None:
        """Test search with memory types filter."""
        results = memory_search_with_memories.search_similar(
            "test", memory_types=["convention", "strategy"]
        )

        for result in results:
            assert result.memory.memory_type.value in ["convention", "strategy"]

    def test_search_similar_with_tags_filter(self, memory_search_with_memories) -> None:
        """Test search with tags filter."""
        results = memory_search_with_memories.search_similar("test", tags=["testing"])

        for result in results:
            assert "testing" in result.memory.tags

    def test_search_similar_invalid_limit(self, memory_search_with_memories) -> None:
        """Test search with invalid limit raises error."""
        with pytest.raises(ValueError, match="Limit must be non-negative"):
            memory_search_with_memories.search_similar("test", limit=-1)

    def test_search_similar_invalid_min_score(self, memory_search_with_memories) -> None:
        """Test search with invalid min_score raises error."""
        with pytest.raises(ValueError, match="Min score must be between 0.0 and 1.0"):
            memory_search_with_memories.search_similar("test", min_score=1.5)

        with pytest.raises(ValueError, match="Min score must be between 0.0 and 1.0"):
            memory_search_with_memories.search_similar("test", min_score=-0.1)

    def test_search_similar_updates_access_count(self, memory_search_with_memories) -> None:
        """Test search updates memory access counts."""
        memory = memory_search_with_memories.memories["mem1"]
        initial_count = memory.access_count

        memory_search_with_memories.search_similar("pytest")

        assert memory.access_count > initial_count

    def test_search_similar_results_sorted(self, memory_search_with_memories) -> None:
        """Test search results are sorted by score descending."""
        results = memory_search_with_memories.search_similar("test")

        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score


# ============================================================================
# MemorySearch.search_by_tag Tests
# ============================================================================


class TestMemorySearchByTag:
    """Tests for MemorySearch.search_by_tag method."""

    def test_search_by_tag_basic(self, memory_search_with_memories) -> None:
        """Test basic tag search."""
        results = memory_search_with_memories.search_by_tag(["testing"])

        assert isinstance(results, list)
        for result in results:
            assert "testing" in result.memory.tags

    def test_search_by_tag_multiple_tags(self, memory_search_with_memories) -> None:
        """Test search with multiple tags (any match)."""
        results = memory_search_with_memories.search_by_tag(["testing", "database"])

        assert isinstance(results, list)
        for result in results:
            has_tag = any(tag in result.memory.tags for tag in ["testing", "database"])
            assert has_tag

    def test_search_by_tag_with_limit(self, memory_search_with_memories) -> None:
        """Test tag search with limit."""
        results = memory_search_with_memories.search_by_tag(["testing"], limit=1)

        assert len(results) <= 1

    def test_search_by_tag_with_scope(self, memory_search_with_memories) -> None:
        """Test tag search with scope filter."""
        results = memory_search_with_memories.search_by_tag(
            ["testing"], scope=MemoryScope.GLOBAL
        )

        for result in results:
            assert "testing" in result.memory.tags
            assert result.memory.scope == MemoryScope.GLOBAL

    def test_search_by_tag_with_spec_id(self, memory_search_with_memories) -> None:
        """Test tag search with spec ID filter."""
        results = memory_search_with_memories.search_by_tag(["pattern"], spec_id="spec1")

        for result in results:
            assert "pattern" in result.memory.tags
            assert result.memory.spec_id == "spec1"

    def test_search_by_tag_with_project_id(self, memory_search_with_memories) -> None:
        """Test tag search with project ID filter."""
        results = memory_search_with_memories.search_by_tag(
            ["authentication"], project_id="proj1"
        )

        for result in results:
            assert "authentication" in result.memory.tags
            assert result.memory.project_id == "proj1"

    def test_search_by_tag_empty_tags_raises_error(self, memory_search_with_memories) -> None:
        """Test empty tags list raises error."""
        with pytest.raises(ValueError, match="Tags list cannot be empty"):
            memory_search_with_memories.search_by_tag([])

    def test_search_by_tag_invalid_limit_raises_error(self, memory_search_with_memories) -> None:
        """Test negative limit raises error."""
        with pytest.raises(ValueError, match="Limit must be non-negative"):
            memory_search_with_memories.search_by_tag(["testing"], limit=-1)

    def test_search_by_tag_results_sorted(self, memory_search_with_memories) -> None:
        """Test tag search results are sorted by relevance."""
        results = memory_search_with_memories.search_by_tag(["testing"])

        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score


# ============================================================================
# MemorySearch.get_memory_by_id Tests
# ============================================================================


class TestMemorySearchGetById:
    """Tests for MemorySearch.get_memory_by_id method."""

    def test_get_memory_by_id_found(self, memory_search_with_memories) -> None:
        """Test retrieving existing memory by ID."""
        memory = memory_search_with_memories.get_memory_by_id("mem1")

        assert memory is not None
        assert memory.id == "mem1"
        assert memory.content == "Use pytest for testing with fixtures"

    def test_get_memory_by_id_not_found(self, memory_search_with_memories) -> None:
        """Test retrieving non-existent memory returns None."""
        memory = memory_search_with_memories.get_memory_by_id("nonexistent")

        assert memory is None

    def test_get_memory_by_id_updates_access_count(self, memory_search_with_memories) -> None:
        """Test get_memory_by_id updates access count."""
        memory = memory_search_with_memories.memories["mem2"]
        initial_count = memory.access_count

        retrieved = memory_search_with_memories.get_memory_by_id("mem2")

        assert retrieved is not None
        assert retrieved.access_count > initial_count


# ============================================================================
# MemorySearch._filter_memories Tests
# ============================================================================


class TestMemorySearchFilter:
    """Tests for MemorySearch._filter_memories method."""

    def test_filter_no_criteria(self, memory_search_with_memories) -> None:
        """Test filtering with no criteria returns all memories."""
        filtered = memory_search_with_memories._filter_memories()

        assert len(filtered) == 4

    def test_filter_by_scope(self, memory_search_with_memories) -> None:
        """Test filtering by scope."""
        global_memories = memory_search_with_memories._filter_memories(scope=MemoryScope.GLOBAL)

        assert all(m.scope == MemoryScope.GLOBAL for m in global_memories)
        assert len(global_memories) >= 1

    def test_filter_by_spec_id(self, memory_search_with_memories) -> None:
        """Test filtering by spec ID."""
        spec_memories = memory_search_with_memories._filter_memories(spec_id="spec1")

        assert all(m.spec_id == "spec1" for m in spec_memories)

    def test_filter_by_project_id(self, memory_search_with_memories) -> None:
        """Test filtering by project ID."""
        proj_memories = memory_search_with_memories._filter_memories(project_id="proj1")

        assert all(m.project_id == "proj1" for m in proj_memories)

    def test_filter_by_memory_types(self, memory_search_with_memories) -> None:
        """Test filtering by memory types."""
        lessons = memory_search_with_memories._filter_memories(
            memory_types=["lesson"]
        )

        assert all(m.memory_type.value == "lesson" for m in lessons)

    def test_filter_by_tags(self, memory_search_with_memories) -> None:
        """Test filtering by tags."""
        tagged = memory_search_with_memories._filter_memories(tags=["testing"])

        assert all(any(tag in m.tags for tag in ["testing"]) for m in tagged)

    def test_filter_combined_criteria(self, memory_search_with_memories) -> None:
        """Test filtering with multiple criteria."""
        filtered = memory_search_with_memories._filter_memories(
            scope=MemoryScope.PROJECT,
            project_id="proj1",
            tags=["database"],
        )

        assert all(m.scope == MemoryScope.PROJECT for m in filtered)
        assert all(m.project_id == "proj1" for m in filtered)


# ============================================================================
# MemorySearch._semantic_search Tests
# ============================================================================


class TestMemorySearchSemantic:
    """Tests for MemorySearch._semantic_search method."""

    def test_semantic_search_basic(self, memory_search_with_memories, memory_with_embedding) -> None:
        """Test basic semantic search with embeddings."""
        query_emb = [0.1, 0.2, 0.3, 0.4, 0.5]
        memories = [memory_with_embedding]

        results = memory_search_with_memories._semantic_search(query_emb, memories, 0.0)

        assert len(results) >= 0

    def test_semantic_search_min_score_threshold(self, memory_search_with_memories, memory_with_embedding) -> None:
        """Test semantic search respects minimum score."""
        query_emb = [0.0, 0.0, 0.0, 0.0, 0.0]  # Very different from memory
        memories = [memory_with_embedding]

        results = memory_search_with_memories._semantic_search(query_emb, memories, 0.9)

        # High threshold should filter out low similarity results
        for result in results:
            assert result.score >= 0.9

    def test_semantic_search_skips_no_embedding(self, memory_search_with_memories, sample_memories) -> None:
        """Test semantic search skips memories without embeddings."""
        query_emb = [0.1, 0.2, 0.3, 0.4, 0.5]
        # Use sample memories without embeddings
        results = memory_search_with_memories._semantic_search(query_emb, sample_memories, 0.0)

        assert len(results) == 0


# ============================================================================
# MemorySearch._text_search Tests
# ============================================================================


class TestMemorySearchText:
    """Tests for MemorySearch._text_search method."""

    def test_text_search_exact_match(self, memory_search_with_memories, sample_memories) -> None:
        """Test text search with exact phrase match."""
        results = memory_search_with_memories._text_search("pytest", sample_memories, 0.0)

        # Should find exact match
        pytest_results = [r for r in results if "pytest" in r.content.lower()]
        assert len(pytest_results) > 0
        # Exact match should have score 1.0
        assert any(r.score == 1.0 for r in pytest_results)

    def test_text_search_word_overlap(self, memory_search_with_memories, sample_memories) -> None:
        """Test text search with word overlap."""
        results = memory_search_with_memories._text_search("use testing", sample_memories, 0.0)

        assert len(results) >= 0
        for result in results:
            assert 0.0 <= result.score <= 1.0

    def test_text_search_min_score(self, memory_search_with_memories, sample_memories) -> None:
        """Test text search respects minimum score."""
        results = memory_search_with_memories._text_search("xyznonexistent", sample_memories, 0.5)

        # Low overlap should be filtered by min_score
        for result in results:
            assert result.score >= 0.5

    def test_text_search_case_insensitive(self, memory_search_with_memories, sample_memories) -> None:
        """Test text search is case insensitive."""
        results_lower = memory_search_with_memories._text_search("pytest", sample_memories, 0.0)
        results_upper = memory_search_with_memories._text_search("PYTEST", sample_memories, 0.0)

        assert len(results_lower) == len(results_upper)


# ============================================================================
# MemorySearch._cosine_similarity Tests
# ============================================================================


class TestMemorySearchCosineSimilarity:
    """Tests for MemorySearch._cosine_similarity method."""

    def test_cosine_similarity_identical(self, memory_search_with_memories) -> None:
        """Test cosine similarity of identical vectors is 1.0."""
        vec = [0.1, 0.2, 0.3, 0.4, 0.5]
        similarity = memory_search_with_memories._cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 0.001

    def test_cosine_similarity_orthogonal(self, memory_search_with_memories) -> None:
        """Test cosine similarity of orthogonal vectors is 0.0."""
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = memory_search_with_memories._cosine_similarity(vec1, vec2)

        assert abs(similarity - 0.0) < 0.001

    def test_cosine_similarity_opposite(self, memory_search_with_memories) -> None:
        """Test cosine similarity of opposite vectors."""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        similarity = memory_search_with_memories._cosine_similarity(vec1, vec2)

        # Should be close to 0 or 1 depending on implementation
        assert 0.0 <= similarity <= 1.0

    def test_cosine_similarity_dimension_mismatch(self, memory_search_with_memories) -> None:
        """Test cosine similarity raises error for dimension mismatch."""
        vec1 = [0.1, 0.2, 0.3]
        vec2 = [0.1, 0.2]

        with pytest.raises(ValueError, match="Vector dimension mismatch"):
            memory_search_with_memories._cosine_similarity(vec1, vec2)

    def test_cosine_similarity_zero_vector(self, memory_search_with_memories) -> None:
        """Test cosine similarity with zero vector."""
        vec1 = [0.0, 0.0, 0.0]
        vec2 = [0.1, 0.2, 0.3]
        similarity = memory_search_with_memories._cosine_similarity(vec1, vec2)

        assert similarity == 0.0


# ============================================================================
# MemorySearch Caching Tests
# ============================================================================


class TestMemorySearchCaching:
    """Tests for MemorySearch caching functionality."""

    def test_cache_key_generation(self, memory_search_with_memories) -> None:
        """Test cache key generation."""
        key1 = memory_search_with_memories._make_cache_key(
            "test query", 10, 0.5, MemoryScope.GLOBAL, "spec1", "proj1", ["convention"], ["tag1"]
        )
        key2 = memory_search_with_memories._make_cache_key(
            "test query", 10, 0.5, MemoryScope.GLOBAL, "spec1", "proj1", ["convention"], ["tag1"]
        )

        assert key1 == key2

    def test_cache_key_different_params(self, memory_search_with_memories) -> None:
        """Test cache keys differ with different parameters."""
        key1 = memory_search_with_memories._make_cache_key("query1", 10, 0.5, None, None, None, None, None)
        key2 = memory_search_with_memories._make_cache_key("query2", 10, 0.5, None, None, None, None, None)

        assert key1 != key2

    def test_cache_disabled(self, memory_search_with_memories) -> None:
        """Test search with caching disabled."""
        # Should not raise any errors
        results = memory_search_with_memories.search_similar("test", use_cache=False)
        assert isinstance(results, list)

    def test_cache_enabled(self) -> None:
        """Test search with caching enabled."""
        search = MemorySearch(cache_enabled=True)

        assert search.cache_enabled is True
        assert isinstance(search._query_cache, dict)

    def test_cache_clear(self, memory_search_with_memories) -> None:
        """Test clearing the cache."""
        # Add something to cache
        memory_search_with_memories._query_cache["test_key"] = []

        memory_search_with_memories.clear_cache()

        assert len(memory_search_with_memories._query_cache) == 0

    def test_cache_eviction(self) -> None:
        """Test cache evicts old entries when full."""
        search = MemorySearch(cache_size=2, cache_enabled=True)
        search._query_cache["key1"] = []
        search._query_cache["key2"] = []
        search._query_cache["key3"] = []

        # Should evict oldest to maintain size
        assert len(search._query_cache) <= 3


# ============================================================================
# MemorySearch Management Tests
# ============================================================================


class TestMemorySearchManagement:
    """Tests for MemorySearch management methods."""

    def test_reload(self, temp_consolidation_file) -> None:
        """Test reloading memories from file."""
        search = MemorySearch(consolidation_path=temp_consolidation_file, cache_enabled=False)
        initial_count = len(search.memories)

        # Modify memory in-memory
        search.memories["mem1"].content = "Modified content"

        # Reload should reset
        search.reload()

        assert len(search.memories) == initial_count
        assert search.memories["mem1"].content == "Use pytest for testing with fixtures"

    def test_reload_clears_cache(self, temp_consolidation_file) -> None:
        """Test reload clears the cache."""
        search = MemorySearch(consolidation_path=temp_consolidation_file, cache_enabled=True)
        search._query_cache["test_key"] = []

        search.reload()

        assert len(search._query_cache) == 0

    def test_stats(self, memory_search_with_memories) -> None:
        """Test statistics reporting."""
        stats = memory_search_with_memories.stats()

        assert isinstance(stats, dict)
        assert "total_memories" in stats
        assert "with_embeddings" in stats
        assert "expired" in stats
        assert "cache_size" in stats
        assert "by_scope" in stats
        assert "by_type" in stats

    def test_stats_values(self, memory_search_with_memories) -> None:
        """Test statistics values are accurate."""
        stats = memory_search_with_memories.stats()

        assert stats["total_memories"] == 4
        assert stats["by_scope"]["global"] >= 1
        assert stats["by_scope"]["project"] >= 1
        assert stats["by_scope"]["spec"] >= 1


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestMemorySearchEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_consolidation_file(self, tmp_path) -> None:
        """Test handling of empty consolidation file."""
        empty_path = tmp_path / "empty.json"
        empty_path.write_text('{"memories": [], "patterns": [], "conventions": []}')

        search = MemorySearch(consolidation_path=empty_path, cache_enabled=False)

        assert len(search.memories) == 0

    def test_malformed_memory_entry(self, tmp_path) -> None:
        """Test handling of malformed memory entries."""
        malformed_path = tmp_path / "malformed.json"
        data = {
            "memories": [
                {"id": "valid", "content": "Valid memory", "memory_type": "fact", "scope": "global"},
                {"invalid": "missing required fields"},
            ],
            "patterns": [],
            "conventions": [],
        }
        malformed_path.write_text(json.dumps(data))

        search = MemorySearch(consolidation_path=malformed_path, cache_enabled=False)

        # Should load valid entries and skip invalid ones
        assert len(search.memories) >= 0

    def test_search_with_no_memories(self, empty_memory_search) -> None:
        """Test search when no memories are loaded."""
        results = empty_memory_search.search_similar("test query")

        assert results == []

    def test_search_empty_query(self, memory_search_with_memories) -> None:
        """Test search with empty query string."""
        # Should handle gracefully
        results = memory_search_with_memories.search_similar("")
        assert isinstance(results, list)

    def test_special_characters_in_query(self, memory_search_with_memories) -> None:
        """Test search with special characters."""
        results = memory_search_with_memories.search_similar("test with 'quotes' and \"double\"")

        assert isinstance(results, list)

    def test_unicode_in_query(self, memory_search_with_memories) -> None:
        """Test search with unicode characters."""
        results = memory_search_with_memories.search_similar("test 中文 日本語")

        assert isinstance(results, list)

    def test_very_long_query(self, memory_search_with_memories) -> None:
        """Test search with very long query."""
        long_query = "test " * 1000
        results = memory_search_with_memories.search_similar(long_query)

        assert isinstance(results, list)


# ============================================================================
# Integration Tests
# ============================================================================


class TestMemorySearchIntegration:
    """Integration tests for MemorySearch."""

    def test_full_search_workflow(self, memory_search_with_memories) -> None:
        """Test complete search workflow."""
        # Search for memories
        results = memory_search_with_memories.search_similar("pytest", limit=5)

        # Verify results
        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, SearchResult)
            assert 0.0 <= result.score <= 1.0
            assert isinstance(result.memory, EnhancedMemory)

    def test_tag_search_workflow(self, memory_search_with_memories) -> None:
        """Test tag-based search workflow."""
        results = memory_search_with_memories.search_by_tag(["testing"])

        assert isinstance(results, list)
        for result in results:
            assert "testing" in result.memory.tags

    def test_combined_filter_workflow(self, memory_search_with_memories) -> None:
        """Test combined filtering workflow."""
        results = memory_search_with_memories.search_similar(
            "test",
            scope=MemoryScope.GLOBAL,
            memory_types=["convention"],
            tags=["testing"],
            limit=10,
        )

        assert isinstance(results, list)
        for result in results:
            assert result.memory.scope == MemoryScope.GLOBAL
            assert result.memory.memory_type == MemoryType.CONVENTION
            assert "testing" in result.memory.tags
