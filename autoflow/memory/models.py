"""
Autoflow Memory Models

Defines the core data models for the enhanced memory system with learning.
These models support memory consolidation, pattern recognition, convention capture,
and scope isolation.

Usage:
    from autoflow.memory.models import EnhancedMemory, MemoryType

    memory = EnhancedMemory(
        content="Use pytest for testing with fixtures",
        memory_type=MemoryType.CONVENTION,
        scope="project-123"
    )
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """
    Type categorization for memory entries.

    Attributes:
        FACT: Factual information (e.g., "Python 3.11+ supports pattern matching")
        STRATEGY: Successful approaches and solutions
        PATTERN: Recurring success or failure patterns
        CONVENTION: Project-specific conventions and standards
        LESSON: Lessons learned from failures
        CONTEXT: Project-specific context and background
    """

    FACT = "fact"
    STRATEGY = "strategy"
    PATTERN = "pattern"
    CONVENTION = "convention"
    LESSON = "lesson"
    CONTEXT = "context"


class MemoryScope(str, Enum):
    """
    Scope level for memory isolation.

    Attributes:
        SPEC: Memory specific to a single spec/task
        PROJECT: Memory shared across a project
        GLOBAL: Global memory shared across all projects
    """

    SPEC = "spec"
    PROJECT = "project"
    GLOBAL = "global"


class EnhancedMemory(BaseModel):
    """
    Enhanced memory entry with metadata and embeddings.

    Represents a single memory entry with rich metadata for tracking,
    consolidation, and semantic search. Memories can be facts, strategies,
    patterns, conventions, or lessons learned.

    Attributes:
        id: Unique identifier for this memory entry
        content: The actual memory content/text
        memory_type: Type categorization (fact, strategy, pattern, etc.)
        scope: Isolation scope (spec, project, or global)
        spec_id: Optional spec ID for spec-scoped memories
        project_id: Optional project ID for project-scoped memories
        embedding: Optional vector embedding for semantic search
        importance: Importance score from 0.0 to 1.0
        access_count: Number of times this memory has been accessed
        last_accessed_at: Timestamp of last access
        created_at: Timestamp when memory was created
        updated_at: Timestamp when memory was last updated
        expires_at: Optional expiration timestamp
        metadata: Additional flexible metadata
        tags: List of tags for categorization and search
        source: Source of this memory (e.g., "consolidation", "manual")
        confidence: Confidence score from 0.0 to 1.0 (if derived from ML)
    """

    id: str
    content: str
    memory_type: MemoryType
    scope: MemoryScope
    spec_id: Optional[str] = None
    project_id: Optional[str] = None
    embedding: Optional[list[float]] = None
    importance: float = 0.5
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: Optional[datetime] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"
    confidence: float = 1.0

    def touch(self) -> None:
        """
        Update the updated_at and last_accessed_at timestamps.

        Should be called whenever the memory is accessed or modified.
        """
        now = datetime.now(UTC)
        self.updated_at = now
        self.last_accessed_at = now
        self.access_count += 1

    def is_expired(self) -> bool:
        """
        Check if this memory entry has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def has_embedding(self) -> bool:
        """
        Check if this memory has an embedding vector.

        Returns:
            True if embedding exists and is non-empty
        """
        return self.embedding is not None and len(self.embedding) > 0

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the memory
        """
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "scope": self.scope.value,
            "spec_id": self.spec_id,
            "project_id": self.project_id,
            "embedding": self.embedding,
            "importance": self.importance,
            "access_count": self.access_count,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "tags": self.tags,
            "source": self.source,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnhancedMemory":
        """
        Create from dictionary for JSON deserialization.

        Args:
            data: Dictionary representation of the memory

        Returns:
            EnhancedMemory instance
        """
        # Handle datetime fields
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)
        expires_at = datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None
        last_accessed_at = datetime.fromisoformat(data["last_accessed_at"]) if data.get("last_accessed_at") else None

        # Handle enum fields
        memory_type = MemoryType(data["memory_type"]) if isinstance(data.get("memory_type"), str) else data.get("memory_type")
        scope = MemoryScope(data["scope"]) if isinstance(data.get("scope"), str) else data.get("scope")

        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=memory_type,
            scope=scope,
            spec_id=data.get("spec_id"),
            project_id=data.get("project_id"),
            embedding=data.get("embedding"),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
            last_accessed_at=last_accessed_at,
            created_at=created_at,
            updated_at=updated_at,
            expires_at=expires_at,
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
            source=data.get("source", "manual"),
            confidence=data.get("confidence", 1.0),
        )

    def add_tag(self, tag: str) -> None:
        """
        Add a tag to the memory if not already present.

        Args:
            tag: Tag to add
        """
        if tag not in self.tags:
            self.tags.append(tag)
            self.touch()

    def remove_tag(self, tag: str) -> None:
        """
        Remove a tag from the memory if present.

        Args:
            tag: Tag to remove
        """
        if tag in self.tags:
            self.tags.remove(tag)
            self.touch()

    def update_importance(self, importance: float) -> None:
        """
        Update the importance score.

        Args:
            importance: New importance score from 0.0 to 1.0

        Raises:
            ValueError: If importance is not between 0.0 and 1.0
        """
        if not 0.0 <= importance <= 1.0:
            raise ValueError(f"Importance must be between 0.0 and 1.0, got {importance}")
        self.importance = importance
        self.touch()

    def set_embedding(self, embedding: list[float]) -> None:
        """
        Set the embedding vector for this memory.

        Args:
            embedding: Vector embedding for semantic search
        """
        self.embedding = embedding
        self.touch()


class PatternType(str, Enum):
    """
    Type categorization for pattern entries.

    Attributes:
        SUCCESS: Patterns that lead to successful outcomes
        FAILURE: Patterns that lead to failures or issues
        WARNING: Patterns that indicate potential problems
        OPTIMIZATION: Patterns for performance or code quality improvements
    """

    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"
    OPTIMIZATION = "optimization"


class Pattern(BaseModel):
    """
    Pattern entry for success/failure pattern detection.

    Represents a recurring pattern identified across tasks, such as
    common successful approaches or recurring failure modes.

    Attributes:
        id: Unique identifier for this pattern
        title: Short title describing the pattern
        description: Detailed description of the pattern
        pattern_type: Type of pattern (success, failure, warning, optimization)
        indicators: List of indicators that signal this pattern
        occurrences: Number of times this pattern has been observed
        confidence: Confidence score from 0.0 to 1.0
        scope: Isolation scope (spec, project, or global)
        spec_id: Optional spec ID for spec-scoped patterns
        project_id: Optional project ID for project-scoped patterns
        examples: List of example observations of this pattern
        mitigation: Optional mitigation strategy (for failure/warning patterns)
        reinforcement: Optional reinforcement strategy (for success patterns)
        created_at: Timestamp when pattern was created
        updated_at: Timestamp when pattern was last updated
        metadata: Additional flexible metadata
        tags: List of tags for categorization and search
    """

    id: str
    title: str
    description: str
    pattern_type: PatternType
    indicators: list[str] = Field(default_factory=list)
    occurrences: int = 1
    confidence: float = 0.5
    scope: MemoryScope
    spec_id: Optional[str] = None
    project_id: Optional[str] = None
    examples: list[str] = Field(default_factory=list)
    mitigation: Optional[str] = None
    reinforcement: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC)

    def record_occurrence(self, example: Optional[str] = None) -> None:
        """
        Record a new occurrence of this pattern.

        Args:
            example: Optional example observation of this occurrence
        """
        self.occurrences += 1
        if example:
            self.examples.append(example)
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "pattern_type": self.pattern_type.value,
            "indicators": self.indicators,
            "occurrences": self.occurrences,
            "confidence": self.confidence,
            "scope": self.scope.value,
            "spec_id": self.spec_id,
            "project_id": self.project_id,
            "examples": self.examples,
            "mitigation": self.mitigation,
            "reinforcement": self.reinforcement,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Pattern":
        """Create from dictionary for JSON deserialization."""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)
        pattern_type = PatternType(data["pattern_type"]) if isinstance(data.get("pattern_type"), str) else data.get("pattern_type")
        scope = MemoryScope(data["scope"]) if isinstance(data.get("scope"), str) else data.get("scope")

        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            pattern_type=pattern_type,
            indicators=data.get("indicators", []),
            occurrences=data.get("occurrences", 1),
            confidence=data.get("confidence", 0.5),
            scope=scope,
            spec_id=data.get("spec_id"),
            project_id=data.get("project_id"),
            examples=data.get("examples", []),
            mitigation=data.get("mitigation"),
            reinforcement=data.get("reinforcement"),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )


class Convention(BaseModel):
    """
    Convention entry for project-specific conventions.

    Represents detected project conventions such as code style, architecture
    patterns, naming conventions, and other project-specific standards.

    Attributes:
        id: Unique identifier for this convention
        name: Short name for the convention
        category: Category of convention (e.g., "code_style", "architecture", "naming")
        description: Detailed description of the convention
        value: The convention value or pattern
        confidence: Confidence score from 0.0 to 1.0
        scope: Isolation scope (spec, project, or global)
        project_id: Project ID this convention applies to
        evidence: List of evidence examples supporting this convention
        created_at: Timestamp when convention was created
        updated_at: Timestamp when convention was last updated
        metadata: Additional flexible metadata
        tags: List of tags for categorization and search
    """

    id: str
    name: str
    category: str
    description: str
    value: Any
    confidence: float = 0.5
    scope: MemoryScope
    project_id: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC)

    def add_evidence(self, evidence: str) -> None:
        """
        Add evidence supporting this convention.

        Args:
            evidence: Evidence example
        """
        self.evidence.append(evidence)
        self.touch()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "value": self.value,
            "confidence": self.confidence,
            "scope": self.scope.value,
            "project_id": self.project_id,
            "evidence": self.evidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Convention":
        """Create from dictionary for JSON deserialization."""
        created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(UTC)
        updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(UTC)
        scope = MemoryScope(data["scope"]) if isinstance(data.get("scope"), str) else data.get("scope")

        return cls(
            id=data["id"],
            name=data["name"],
            category=data["category"],
            description=data["description"],
            value=data["value"],
            confidence=data.get("confidence", 0.5),
            scope=scope,
            project_id=data.get("project_id"),
            evidence=data.get("evidence", []),
            created_at=created_at,
            updated_at=updated_at,
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )


class ConsolidationRecord(BaseModel):
    """
    Record of a memory consolidation run.

    Tracks consolidation operations including what was consolidated,
    when it occurred, and the outcome.

    Attributes:
        id: Unique identifier for this consolidation record
        run_id: ID of the agent run that triggered consolidation
        spec_id: ID of the spec being consolidated
        status: Status of consolidation (pending, in_progress, completed, failed)
        memories_created: Number of memories created
        patterns_identified: Number of patterns identified
        conventions_detected: Number of conventions detected
        started_at: Timestamp when consolidation started
        completed_at: Timestamp when consolidation completed
        duration_seconds: Duration of consolidation in seconds
        error: Optional error message if consolidation failed
        metadata: Additional flexible metadata
    """

    id: str
    run_id: str
    spec_id: str
    status: str = "pending"
    memories_created: int = 0
    patterns_identified: int = 0
    conventions_detected: int = 0
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def start(self) -> None:
        """Mark consolidation as started."""
        self.status = "in_progress"
        self.started_at = datetime.now(UTC)

    def complete(
        self,
        memories_created: int = 0,
        patterns_identified: int = 0,
        conventions_detected: int = 0,
    ) -> None:
        """
        Mark consolidation as completed.

        Args:
            memories_created: Number of memories created
            patterns_identified: Number of patterns identified
            conventions_detected: Number of conventions detected
        """
        self.status = "completed"
        self.completed_at = datetime.now(UTC)
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.memories_created = memories_created
        self.patterns_identified = patterns_identified
        self.conventions_detected = conventions_detected

    def fail(self, error: str) -> None:
        """
        Mark consolidation as failed.

        Args:
            error: Error message describing the failure
        """
        self.status = "failed"
        self.completed_at = datetime.now(UTC)
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "spec_id": self.spec_id,
            "status": self.status,
            "memories_created": self.memories_created,
            "patterns_identified": self.patterns_identified,
            "conventions_detected": self.conventions_detected,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConsolidationRecord":
        """Create from dictionary for JSON deserialization."""
        started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(UTC)
        completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None

        return cls(
            id=data["id"],
            run_id=data["run_id"],
            spec_id=data["spec_id"],
            status=data.get("status", "pending"),
            memories_created=data.get("memories_created", 0),
            patterns_identified=data.get("patterns_identified", 0),
            conventions_detected=data.get("conventions_detected", 0),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=data.get("duration_seconds"),
            error=data.get("error"),
            metadata=data.get("metadata", {}),
        )
