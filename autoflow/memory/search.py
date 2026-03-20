"""
Autoflow Memory Search

Provides semantic search capabilities for the memory system using embeddings.
This module implements similarity search to find relevant past solutions, patterns,
and conventions based on semantic meaning rather than keyword matching.

Usage:
    from autoflow.memory.search import MemorySearch

    search = MemorySearch()
    results = search.search_similar("authentication error", limit=5)
    for result in results:
        print(f"Memory: {result.content}")
        print(f"Relevance: {result.score}")
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

from autoflow.memory.models import (
    EnhancedMemory,
    MemoryScope,
)


class SearchResult:
    """
    Represents a single search result with relevance score.

    Attributes:
        memory: The matching memory entry
        score: Relevance score from 0.0 to 1.0 (higher is more relevant)
    """

    def __init__(self, memory: EnhancedMemory, score: float) -> None:
        """
        Initialize a search result.

        Args:
            memory: The matching memory entry
            score: Relevance score from 0.0 to 1.0

        Raises:
            ValueError: If score is not between 0.0 and 1.0
        """
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {score}")
        self.memory = memory
        self.score = score

    @property
    def content(self) -> str:
        """Get the memory content."""
        return self.memory.content

    def __repr__(self) -> str:
        """String representation of the search result."""
        return f"SearchResult(content={self.content[:50]}..., score={self.score:.3f})"


class MemorySearch:
    """
    Semantic search for memory entries using embeddings.

    This class handles:
    - Loading memories and embeddings from consolidation data
    - Computing semantic similarity using cosine similarity
    - Filtering by scope, memory type, and tags
    - Ranking results by relevance score
    - Managing search performance with caching

    The search uses cosine similarity between embeddings to find semantically
    similar memories. Results are ranked by similarity score and can be filtered
    by various criteria.

    Attributes:
        consolidation_path: Path to the consolidation JSON file
        memories: Dictionary of loaded memory entries
        cache_enabled: Whether search result caching is enabled
        _query_cache: Cache for recent queries
    """

    # Default consolidation file path
    DEFAULT_CONSOLIDATION_PATH = Path(".autoflow/consolidation.json")

    # Default cache size for query results
    DEFAULT_CACHE_SIZE = 100

    def __init__(
        self,
        consolidation_path: Optional[Path] = None,
        root_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ) -> None:
        """
        Initialize the memory search engine.

        Args:
            consolidation_path: Path to consolidation JSON file. If None, uses DEFAULT_CONSOLIDATION_PATH
            root_dir: Root directory of the project. Defaults to current directory.
            cache_enabled: Whether to enable query result caching
            cache_size: Maximum number of cached query results
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if consolidation_path is None:
            consolidation_path = self.DEFAULT_CONSOLIDATION_PATH

        self.consolidation_path = Path(consolidation_path)
        self.cache_enabled = cache_enabled
        self._cache_size = cache_size

        # Initialize cache
        self._query_cache: dict[str, list[SearchResult]] = {}

        # Load memories from consolidation data
        self.memories: dict[str, EnhancedMemory] = {}
        self._load_memories()

    def search_similar(
        self,
        query: str,
        query_embedding: Optional[list[float]] = None,
        limit: int = 10,
        min_score: float = 0.0,
        scope: Optional[MemoryScope] = None,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        use_cache: bool = True,
    ) -> list[SearchResult]:
        """
        Search for memories semantically similar to the query.

        Uses cosine similarity between embeddings to find relevant memories.
        Results are ranked by similarity score and filtered by criteria.

        Args:
            query: Search query text
            query_embedding: Optional pre-computed query embedding. If None, attempts to use text-based matching
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0 to 1.0)
            scope: Optional scope filter (spec, project, or global)
            spec_id: Optional spec ID filter for spec-scoped memories
            project_id: Optional project ID filter for project-scoped memories
            memory_types: Optional list of memory types to include
            tags: Optional list of tags to filter by (any match)
            use_cache: Whether to use cached results if available

        Returns:
            List of SearchResult objects ranked by relevance score

        Raises:
            ValueError: If limit is less than 0 or min_score is not between 0.0 and 1.0
        """
        if limit < 0:
            raise ValueError(f"Limit must be non-negative, got {limit}")
        if not 0.0 <= min_score <= 1.0:
            raise ValueError(f"Min score must be between 0.0 and 1.0, got {min_score}")

        # Check cache first
        cache_key = self._make_cache_key(
            query, limit, min_score, scope, spec_id, project_id, memory_types, tags
        )
        if use_cache and self.cache_enabled and cache_key in self._query_cache:
            return self._query_cache[cache_key][:limit]

        # Filter memories by criteria
        filtered_memories = self._filter_memories(
            scope=scope,
            spec_id=spec_id,
            project_id=project_id,
            memory_types=memory_types,
            tags=tags,
        )

        # If no query embedding provided, use text-based matching as fallback
        if query_embedding is None:
            results = self._text_search(query, filtered_memories, min_score)
        else:
            results = self._semantic_search(query_embedding, filtered_memories, min_score)

        # Sort by score descending and limit results
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:limit]

        # Cache results
        if self.cache_enabled:
            self._add_to_cache(cache_key, results)

        # Update access counts for returned memories
        for result in results:
            result.memory.touch()

        return results

    def search_by_tag(
        self,
        tags: list[str],
        limit: int = 10,
        scope: Optional[MemoryScope] = None,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Search for memories by tags.

        Returns memories that have any of the specified tags, ranked by
        importance and access count.

        Args:
            tags: List of tags to search for
            limit: Maximum number of results to return
            scope: Optional scope filter
            spec_id: Optional spec ID filter
            project_id: Optional project ID filter

        Returns:
            List of SearchResult objects ranked by relevance

        Raises:
            ValueError: If tags list is empty or limit is negative
        """
        if not tags:
            raise ValueError("Tags list cannot be empty")
        if limit < 0:
            raise ValueError(f"Limit must be non-negative, got {limit}")

        # Filter memories by criteria and tags
        filtered = self._filter_memories(
            scope=scope,
            spec_id=spec_id,
            project_id=project_id,
            tags=tags,
        )

        # Rank by importance and access count
        results = []
        for memory in filtered:
            # Calculate relevance score based on importance and access
            relevance = (memory.importance * 0.7) + (min(memory.access_count / 10.0, 1.0) * 0.3)
            results.append(SearchResult(memory, relevance))

        # Sort and limit
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:limit]

        return results

    def get_memory_by_id(self, memory_id: str) -> Optional[EnhancedMemory]:
        """
        Retrieve a specific memory by ID.

        Args:
            memory_id: Unique identifier of the memory

        Returns:
            EnhancedMemory if found, None otherwise
        """
        memory = self.memories.get(memory_id)
        if memory:
            memory.touch()
        return memory

    def _load_memories(self) -> None:
        """
        Load memories from consolidation data file.

        Reads the consolidation JSON file and populates the memories dictionary.
        Creates empty structures if file doesn't exist.
        """
        if not self.consolidation_path.exists():
            # No consolidation data yet
            return

        try:
            with open(self.consolidation_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load memories from consolidation data
            for memory_data in data.get("memories", []):
                try:
                    memory = EnhancedMemory.from_dict(memory_data)
                    self.memories[memory.id] = memory
                except Exception:
                    # Skip invalid memory entries
                    continue

        except (json.JSONDecodeError, IOError):
            # Invalid or unreadable file, start fresh
            self.memories = {}

    def _filter_memories(
        self,
        scope: Optional[MemoryScope] = None,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
    ) -> list[EnhancedMemory]:
        """
        Filter memories by specified criteria.

        Args:
            scope: Optional scope filter
            spec_id: Optional spec ID filter
            project_id: Optional project ID filter
            memory_types: Optional list of memory types
            tags: Optional list of tags (any match)

        Returns:
            List of filtered memory entries
        """
        filtered = list(self.memories.values())

        # Filter out expired memories
        filtered = [m for m in filtered if not m.is_expired()]

        # Apply scope filter
        if scope:
            filtered = [m for m in filtered if m.scope == scope]

        # Apply spec ID filter
        if spec_id:
            filtered = [m for m in filtered if m.spec_id == spec_id]

        # Apply project ID filter
        if project_id:
            filtered = [m for m in filtered if m.project_id == project_id]

        # Apply memory type filter
        if memory_types:
            filtered = [m for m in filtered if m.memory_type.value in memory_types]

        # Apply tags filter (any match)
        if tags:
            filtered = [m for m in filtered if any(tag in m.tags for tag in tags)]

        return filtered

    def _semantic_search(
        self,
        query_embedding: list[float],
        memories: list[EnhancedMemory],
        min_score: float,
    ) -> list[SearchResult]:
        """
        Perform semantic search using cosine similarity.

        Args:
            query_embedding: Query embedding vector
            memories: List of memories to search through
            min_score: Minimum similarity score threshold

        Returns:
            List of SearchResult objects with scores >= min_score
        """
        results = []

        for memory in memories:
            # Skip memories without embeddings
            if not memory.has_embedding():
                continue

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_embedding, memory.embedding)  # type: ignore[arg-type]

            # Apply minimum score threshold
            if similarity >= min_score:
                results.append(SearchResult(memory, similarity))

        return results

    def _text_search(
        self,
        query: str,
        memories: list[EnhancedMemory],
        min_score: float,
    ) -> list[SearchResult]:
        """
        Perform text-based search as fallback.

        Uses simple text matching when embeddings are not available.
        Scores are based on exact phrase matching and word overlap.

        Args:
            query: Search query text
            memories: List of memories to search through
            min_score: Minimum similarity score threshold

        Returns:
            List of SearchResult objects with scores >= min_score
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())
        results = []

        for memory in memories:
            content_lower = memory.content.lower()

            # Exact phrase match gets highest score
            if query_lower in content_lower:
                score = 1.0
            # Word overlap scoring
            else:
                content_words = set(content_lower.split())
                overlap = len(query_words & content_words)
                if len(query_words) > 0:
                    score = overlap / len(query_words)
                else:
                    score = 0.0

            # Apply minimum score threshold
            if score >= min_score:
                results.append(SearchResult(memory, score))

        return results

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Args:
            vec1: First vector
            vec2: Second vector

        Returns:
            Cosine similarity from 0.0 to 1.0

        Raises:
            ValueError: If vectors have different dimensions
        """
        if len(vec1) != len(vec2):
            raise ValueError(f"Vector dimension mismatch: {len(vec1)} != {len(vec2)}")

        # Compute dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Compute magnitudes
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))

        # Avoid division by zero
        if magnitude1 == 0.0 or magnitude2 == 0.0:
            return 0.0

        # Compute cosine similarity
        similarity = dot_product / (magnitude1 * magnitude2)

        # Ensure result is in valid range [0, 1]
        return max(0.0, min(1.0, similarity))

    def _make_cache_key(
        self,
        query: str,
        limit: int,
        min_score: float,
        scope: Optional[MemoryScope],
        spec_id: Optional[str],
        project_id: Optional[str],
        memory_types: Optional[list[str]],
        tags: Optional[list[str]],
    ) -> str:
        """
        Create a cache key for the query parameters.

        Args:
            query: Search query
            limit: Result limit
            min_score: Minimum score threshold
            scope: Scope filter
            spec_id: Spec ID filter
            project_id: Project ID filter
            memory_types: Memory type filters
            tags: Tag filters

        Returns:
            String cache key
        """
        parts = [
            query,
            str(limit),
            str(min_score),
            str(scope) if scope else "",
            spec_id or "",
            project_id or "",
            ",".join(memory_types or []),
            ",".join(tags or []),
        ]
        return "|".join(parts)

    def _add_to_cache(self, key: str, results: list[SearchResult]) -> None:
        """
        Add results to cache, evicting old entries if necessary.

        Args:
            key: Cache key
            results: Search results to cache
        """
        # Add new entry
        self._query_cache[key] = list(results)

        # Evict oldest entries if cache is too large
        while len(self._query_cache) > self._cache_size:
            # Remove first entry (FIFO eviction)
            oldest_key = next(iter(self._query_cache))
            del self._query_cache[oldest_key]

    def clear_cache(self) -> None:
        """Clear the query cache."""
        self._query_cache.clear()

    def reload(self) -> None:
        """
        Reload memories from consolidation data file.

        Useful for picking up changes made by consolidation processes.
        """
        self.memories.clear()
        self._query_cache.clear()
        self._load_memories()

    def stats(self) -> dict[str, Any]:
        """
        Get statistics about the search index.

        Returns:
            Dictionary with search index statistics
        """
        memories_list = list(self.memories.values())

        # Count by scope
        by_scope: dict[str, int] = {}
        for memory in memories_list:
            scope = memory.scope.value
            by_scope[scope] = by_scope.get(scope, 0) + 1

        # Count by memory type
        by_type: dict[str, int] = {}
        for memory in memories_list:
            mtype = memory.memory_type.value
            by_type[mtype] = by_type.get(mtype, 0) + 1

        # Count memories with embeddings
        with_embeddings = sum(1 for m in memories_list if m.has_embedding())

        # Count expired memories
        expired = sum(1 for m in memories_list if m.is_expired())

        return {
            "total_memories": len(memories_list),
            "with_embeddings": with_embeddings,
            "expired": expired,
            "cache_size": len(self._query_cache),
            "by_scope": by_scope,
            "by_type": by_type,
        }
