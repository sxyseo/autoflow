"""
Autoflow Memory Manager - Unified Interface

Provides a unified interface for all memory operations, combining consolidation,
search, and embedding generation. This is the main entry point for working with
the enhanced memory system.

Usage:
    from autoflow.memory import MemoryManager

    manager = MemoryManager()
    manager.add_memory("Use pytest for testing", memory_type="fact")
    results = manager.search_context("authentication error")
    context = manager.get_context_for_run(task_id="task-123", spec_id="my-spec")
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from autoflow.memory.consolidation import MemoryConsolidator
from autoflow.memory.embeddings import EmbeddingService
from autoflow.memory.models import (
    EnhancedMemory,
    MemoryScope,
    MemoryType,
)
from autoflow.memory.search import MemorySearch, SearchResult


class MemoryManager:
    """
    Unified interface for all memory operations.

    This class provides a convenient API for:
    - Adding new memories with automatic embedding generation
    - Searching for relevant context using semantic similarity
    - Getting contextual information for runs
    - Consolidating memories from completed runs

    The manager combines the functionality of:
    - MemoryConsolidator: Extracts and consolidates memories from execution data
    - MemorySearch: Provides semantic search capabilities
    - EmbeddingService: Generates embeddings for memories

    Attributes:
        consolidator: MemoryConsolidator instance for consolidation operations
        search: MemorySearch instance for search operations
        embedding_service: EmbeddingService instance for embedding generation
        root_dir: Root directory of the project
    """

    # Default consolidation file path
    DEFAULT_CONSOLIDATION_PATH = Path(".autoflow/consolidation.json")

    def __init__(
        self,
        consolidation_path: Optional[Path] = None,
        root_dir: Optional[Path] = None,
        enable_embeddings: bool = True,
    ) -> None:
        """
        Initialize the memory manager.

        Args:
            consolidation_path: Path to consolidation JSON file. If None, uses DEFAULT_CONSOLIDATION_PATH
            root_dir: Root directory of the project. Defaults to current directory.
            enable_embeddings: Whether to enable embedding generation. If False, embedding operations
                             will be no-ops (useful for environments without ML dependencies).
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if consolidation_path is None:
            consolidation_path = self.DEFAULT_CONSOLIDATION_PATH

        self.root_dir = Path(root_dir)
        self.consolidation_path = Path(consolidation_path)
        self.enable_embeddings = enable_embeddings

        # Initialize consolidator
        self.consolidator = MemoryConsolidator(
            consolidation_path=self.consolidation_path,
            root_dir=self.root_dir,
        )

        # Initialize search
        self.search = MemorySearch(
            consolidation_path=self.consolidation_path,
            root_dir=self.root_dir,
        )

        # Initialize embedding service (lazy loaded)
        self._embedding_service: Optional[EmbeddingService] = None
        self._embedding_enabled = enable_embeddings

    @property
    def embedding_service(self) -> Optional[EmbeddingService]:
        """
        Get the embedding service instance.

        Returns None if embeddings are disabled or not available.

        Returns:
            EmbeddingService instance if available, None otherwise
        """
        if not self._embedding_enabled:
            return None

        if self._embedding_service is None:
            try:
                self._embedding_service = EmbeddingService()
            except Exception:
                # Embedding service not available, disable for future calls
                self._embedding_enabled = False
                return None

        return self._embedding_service

    def add_memory(
        self,
        content: str,
        memory_type: MemoryType,
        scope: MemoryScope = MemoryScope.PROJECT,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        source: str = "manual",
        generate_embedding: bool = True,
    ) -> EnhancedMemory:
        """
        Add a new memory entry with optional embedding generation.

        Creates a new memory and optionally generates an embedding for it.
        The memory is persisted to the consolidation store.

        Args:
            content: The memory content/text
            memory_type: Type of memory (fact, strategy, pattern, convention, lesson, context)
            scope: Isolation scope (spec, project, or global)
            spec_id: Optional spec ID for spec-scoped memories
            project_id: Optional project ID for project-scoped memories
            importance: Importance score from 0.0 to 1.0
            tags: Optional list of tags for categorization
            source: Source of this memory (e.g., "manual", "consolidation")
            generate_embedding: Whether to generate embedding for this memory

        Returns:
            The created EnhancedMemory instance

        Raises:
            ValueError: If content is empty or importance is not between 0.0 and 1.0
            IOError: If unable to persist memory to disk
        """
        if not content or not content.strip():
            raise ValueError("Memory content cannot be empty")

        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"Importance must be between 0.0 and 1.0, got {importance}")

        # Generate embedding if requested and available
        embedding = None
        if generate_embedding and self.embedding_service:
            try:
                embedding = self.embedding_service.generate(content)
            except Exception:
                # Embedding generation failed, continue without it
                pass

        # Create memory
        memory = EnhancedMemory(
            id=str(uuid.uuid4()),
            content=content,
            memory_type=memory_type,
            scope=scope,
            spec_id=spec_id if scope == MemoryScope.SPEC else None,
            project_id=project_id if scope == MemoryScope.PROJECT else None,
            embedding=embedding,
            importance=importance,
            tags=tags or [],
            source=source,
        )

        # Add to consolidator's memory store
        self.consolidator.memories[memory.id] = memory

        # Persist to disk
        self.consolidator._save_consolidation()

        # Reload search index
        self.search.reload()

        return memory

    def search_context(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.0,
        scope: Optional[MemoryScope] = None,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
        memory_types: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """
        Search for relevant context using semantic similarity.

        Performs a semantic search for memories similar to the query.
        Results are ranked by relevance score and can be filtered by various criteria.

        Args:
            query: Search query text
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (0.0 to 1.0)
            scope: Optional scope filter (spec, project, or global)
            spec_id: Optional spec ID filter for spec-scoped memories
            project_id: Optional project ID filter for project-scoped memories
            memory_types: Optional list of memory types to include
            tags: Optional list of tags to filter by (any match)

        Returns:
            List of SearchResult objects ranked by relevance score

        Raises:
            ValueError: If limit is less than 0 or min_score is not between 0.0 and 1.0
        """
        # Generate query embedding if available
        query_embedding = None
        if self.embedding_service:
            try:
                query_embedding = self.embedding_service.generate(query)
            except Exception:
                # Embedding generation failed, use text-based fallback
                pass

        # Perform search
        results = self.search.search_similar(
            query=query,
            query_embedding=query_embedding,
            limit=limit,
            min_score=min_score,
            scope=scope,
            spec_id=spec_id,
            project_id=project_id,
            memory_types=memory_types,
            tags=tags,
        )

        return results

    def get_context_for_run(
        self,
        task_id: str,
        spec_id: str,
        max_items: int = 5,
        relevance_threshold: float = 0.3,
        include_spec: bool = True,
        include_global: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get relevant context for a specific run.

        Aggregates relevant memories from both spec-scoped and global scopes
        based on the task description and spec ID. Results are formatted for
        injection into agent prompts.

        Args:
            task_id: Task identifier for searching related memories
            spec_id: Spec ID for spec-scoped memories
            max_items: Maximum number of context items to return
            relevance_threshold: Minimum relevance score for inclusion
            include_spec: Whether to include spec-scoped memories
            include_global: Whether to include global/project-scoped memories

        Returns:
            List of context dictionaries with keys:
            - content: Memory content
            - score: Relevance score
            - scope: Memory scope (spec or global)
            - type: Memory type (fact, strategy, etc.)
            - tags: List of tags
        """
        context_items = []

        # Search spec-scoped memories
        if include_spec:
            spec_results = self.search_context(
                query=task_id,
                limit=max_items,
                min_score=relevance_threshold,
                scope=MemoryScope.SPEC,
                spec_id=spec_id,
            )
            for result in spec_results:
                context_items.append({
                    "content": result.content,
                    "score": result.score,
                    "scope": "spec",
                    "type": result.memory.memory_type.value,
                    "tags": result.memory.tags,
                })

        # Search global/project-scoped memories
        if include_global:
            global_results = self.search_context(
                query=task_id,
                limit=max_items,
                min_score=relevance_threshold,
                scope=MemoryScope.GLOBAL,
            )
            for result in global_results:
                context_items.append({
                    "content": result.content,
                    "score": result.score,
                    "scope": "global",
                    "type": result.memory.memory_type.value,
                    "tags": result.memory.tags,
                })

        # Also search project-scoped memories
        if include_global:
            project_results = self.search_context(
                query=task_id,
                limit=max_items,
                min_score=relevance_threshold,
                scope=MemoryScope.PROJECT,
            )
            for result in project_results:
                context_items.append({
                    "content": result.content,
                    "score": result.score,
                    "scope": "global",
                    "type": result.memory.memory_type.value,
                    "tags": result.memory.tags,
                })

        # Sort by score and limit
        context_items.sort(key=lambda x: x["score"], reverse=True)
        context_items = context_items[:max_items]

        return context_items

    def consolidate_run(
        self,
        run_id: str,
        spec_id: str,
        execution_data: dict[str, Any],
        scope: MemoryScope = MemoryScope.PROJECT,
        project_id: Optional[str] = None,
        auto_embed: bool = True,
    ) -> dict[str, Any]:
        """
        Consolidate memories from a completed run.

        Extracts memories, patterns, and conventions from execution data
        and stores them in the consolidation store. Optionally generates
        embeddings for extracted memories.

        Args:
            run_id: Unique identifier for the execution run
            spec_id: Unique identifier for the spec
            execution_data: Dictionary containing execution results and metadata
            scope: Isolation scope for memories (spec, project, or global)
            project_id: Optional project ID for project-scoped memories
            auto_embed: Whether to automatically generate embeddings for extracted memories

        Returns:
            Dictionary with consolidation results:
            - memories_created: Number of memories created
            - patterns_identified: Number of patterns identified
            - conventions_detected: Number of conventions detected
            - status: Consolidation status (completed or failed)
            - error: Error message if failed

        Raises:
            IOError: If unable to write consolidation data to disk
        """
        # Perform consolidation
        record = self.consolidator.consolidate(
            run_id=run_id,
            spec_id=spec_id,
            execution_data=execution_data,
            scope=scope,
            project_id=project_id,
        )

        # Auto-generate embeddings if requested
        if auto_embed and self.embedding_service:
            for memory in self.consolidator.memories.values():
                # Generate embedding for memories that don't have one
                if not memory.has_embedding():
                    try:
                        embedding = self.embedding_service.generate(memory.content)
                        memory.set_embedding(embedding)
                    except Exception:
                        # Embedding generation failed, continue
                        pass

            # Persist updated memories with embeddings
            self.consolidator._save_consolidation()

        # Reload search index to include new memories
        self.search.reload()

        return {
            "memories_created": record.memories_created,
            "patterns_identified": record.patterns_identified,
            "conventions_detected": record.conventions_detected,
            "status": record.status,
            "error": record.error,
        }

    def get_memory_by_id(self, memory_id: str) -> Optional[EnhancedMemory]:
        """
        Retrieve a specific memory by ID.

        Args:
            memory_id: Unique identifier of the memory

        Returns:
            EnhancedMemory if found, None otherwise
        """
        return self.search.get_memory_by_id(memory_id)

    def get_memories(
        self,
        memory_type: Optional[MemoryType] = None,
        scope: Optional[MemoryScope] = None,
        spec_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[EnhancedMemory]:
        """
        Retrieve memories matching the given criteria.

        Args:
            memory_type: Optional memory type filter
            scope: Optional scope filter
            spec_id: Optional spec ID filter
            project_id: Optional project ID filter

        Returns:
            List of matching memory entries
        """
        return self.consolidator.get_memories(
            memory_type=memory_type,
            scope=scope,
            spec_id=spec_id,
            project_id=project_id,
        )

    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        scope: Optional[MemoryScope] = None,
        project_id: Optional[str] = None,
    ) -> list[Any]:
        """
        Retrieve patterns matching the given criteria.

        Args:
            pattern_type: Optional pattern type filter (success, failure, warning, optimization)
            scope: Optional scope filter
            project_id: Optional project ID filter

        Returns:
            List of matching pattern entries
        """
        # Import PatternType here to avoid issues with circular imports
        from autoflow.memory.models import PatternType

        pattern_type_enum = PatternType(pattern_type) if pattern_type else None
        return self.consolidator.get_patterns(
            pattern_type=pattern_type_enum,
            scope=scope,
            project_id=project_id,
        )

    def get_conventions(
        self,
        category: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[Any]:
        """
        Retrieve conventions matching the given criteria.

        Args:
            category: Optional category filter
            project_id: Optional project ID filter

        Returns:
            List of matching convention entries
        """
        return self.consolidator.get_conventions(
            category=category,
            project_id=project_id,
        )

    def reload(self) -> None:
        """
        Reload all data from disk.

        Useful for picking up changes made by other processes.
        """
        self.consolidator._load_consolidation()
        self.search.reload()

    def stats(self) -> dict[str, Any]:
        """
        Get statistics about the memory system.

        Returns:
            Dictionary with memory system statistics including:
            - total_memories: Total number of memories
            - with_embeddings: Number of memories with embeddings
            - expired: Number of expired memories
            - by_scope: Breakdown by scope
            - by_type: Breakdown by memory type
        """
        return self.search.stats()
