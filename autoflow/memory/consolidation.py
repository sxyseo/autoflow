"""
Autoflow Memory Consolidation

Consolidates raw execution data into structured memories for long-term learning.
This module implements the consolidation process that extracts facts, strategies,
patterns, and conventions from completed runs.

Usage:
    from autoflow.memory.consolidation import MemoryConsolidator

    consolidator = MemoryConsolidator()
    record = consolidator.consolidate(run_id, spec_id, execution_data)
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from autoflow.memory.models import (
    ConsolidationRecord,
    Convention,
    EnhancedMemory,
    MemoryScope,
    MemoryType,
    Pattern,
    PatternType,
)


class MemoryConsolidator:
    """
    Consolidates raw execution data into structured memories.

    This class handles:
    - Extracting memories from completed runs
    - Identifying success/failure patterns
    - Detecting project conventions
    - Managing consolidation records
    - Persisting consolidated data to disk

    The consolidated memories are stored in .autoflow/consolidation.json
    following the strategy memory pattern with atomic writes.

    Attributes:
        consolidation_path: Path to the consolidation JSON file
        memories: Dictionary of consolidated memory entries
        patterns: Dictionary of identified patterns
        conventions: Dictionary of detected conventions
        records: Dictionary of consolidation records
    """

    # Default consolidation file path
    DEFAULT_CONSOLIDATION_PATH = Path(".autoflow/consolidation.json")

    def __init__(
        self, consolidation_path: Optional[Path] = None, root_dir: Optional[Path] = None
    ) -> None:
        """
        Initialize the memory consolidator.

        Args:
            consolidation_path: Path to consolidation JSON file. If None, uses DEFAULT_CONSOLIDATION_PATH
            root_dir: Root directory of the project. Defaults to current directory.
        """
        if root_dir is None:
            root_dir = Path.cwd()

        if consolidation_path is None:
            consolidation_path = self.DEFAULT_CONSOLIDATION_PATH

        self.consolidation_path = Path(consolidation_path)

        # Ensure parent directory exists
        self.consolidation_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data or initialize empty
        self.memories: dict[str, EnhancedMemory] = {}
        self.patterns: dict[str, Pattern] = {}
        self.conventions: dict[str, Convention] = {}
        self.records: dict[str, ConsolidationRecord] = {}
        self._load_consolidation()

    def consolidate(
        self,
        run_id: str,
        spec_id: str,
        execution_data: dict[str, Any],
        scope: MemoryScope = MemoryScope.PROJECT,
        project_id: Optional[str] = None,
    ) -> ConsolidationRecord:
        """
        Consolidate execution data into structured memories.

        Analyzes the execution data to extract:
        - Facts learned during execution
        - Successful strategies used
        - Patterns in success or failure
        - Project-specific conventions

        Args:
            run_id: Unique identifier for the execution run
            spec_id: Unique identifier for the spec
            execution_data: Dictionary containing execution results and metadata
            scope: Isolation scope for memories (spec, project, or global)
            project_id: Optional project ID for project-scoped memories

        Returns:
            ConsolidationRecord with results of the consolidation

        Raises:
            IOError: If unable to write consolidation data to disk
        """
        # Create consolidation record
        record = ConsolidationRecord(
            id=str(uuid.uuid4()),
            run_id=run_id,
            spec_id=spec_id,
        )
        record.start()

        try:
            # Extract memories from execution data
            memories = self._extract_memories(
                execution_data, scope, spec_id, project_id
            )
            record.memories_created = len(memories)

            # Identify patterns
            patterns = self._identify_patterns(
                execution_data, scope, spec_id, project_id
            )
            record.patterns_identified = len(patterns)

            # Detect conventions
            conventions = self._detect_conventions(execution_data, scope, project_id)
            record.conventions_detected = len(conventions)

            # Store consolidated data
            for memory in memories:
                self.memories[memory.id] = memory

            for pattern in patterns:
                if pattern.id in self.patterns:
                    # Update existing pattern
                    existing = self.patterns[pattern.id]
                    existing.record_occurrence()
                    existing.touch()
                else:
                    # Add new pattern
                    self.patterns[pattern.id] = pattern

            for convention in conventions:
                if convention.id in self.conventions:
                    # Update existing convention
                    existing = self.conventions[convention.id]
                    existing.touch()
                else:
                    # Add new convention
                    self.conventions[convention.id] = convention

            # Store record
            self.records[record.id] = record

            # Persist to disk
            self._save_consolidation()

            # Mark record as completed
            record.complete(
                memories_created=len(memories),
                patterns_identified=len(patterns),
                conventions_detected=len(conventions),
            )

        except Exception as e:
            # Mark record as failed
            record.fail(str(e))
            raise

        return record

    def _extract_memories(
        self,
        execution_data: dict[str, Any],
        scope: MemoryScope,
        spec_id: str,
        project_id: Optional[str],
    ) -> list[EnhancedMemory]:
        """
        Extract memories from execution data.

        Analyzes execution results to extract:
        - Facts learned during execution
        - Strategies that led to success
        - Lessons from failures
        - Context about the project

        Args:
            execution_data: Dictionary containing execution results
            scope: Isolation scope for memories
            spec_id: Spec ID for spec-scoped memories
            project_id: Project ID for project-scoped memories

        Returns:
            List of extracted memory entries
        """
        memories = []

        # Extract outcome
        outcome = execution_data.get("outcome", "unknown")
        success = outcome.lower() in ("success", "completed")

        # Extract lessons learned
        if execution_data.get("errors"):
            for error in execution_data["errors"]:
                memory = EnhancedMemory(
                    id=str(uuid.uuid4()),
                    content=f"Error pattern: {error}",
                    memory_type=MemoryType.LESSON,
                    scope=scope,
                    spec_id=spec_id if scope == MemoryScope.SPEC else None,
                    project_id=project_id if scope == MemoryScope.PROJECT else None,
                    importance=0.7,
                    source="consolidation",
                    metadata={
                        "error_type": type(error).__name__
                        if hasattr(error, "__class__")
                        else "unknown"
                    },
                )
                memories.append(memory)

        # Extract successful strategies
        if success:
            strategies = execution_data.get("strategies_used", [])
            for strategy in strategies:
                memory = EnhancedMemory(
                    id=str(uuid.uuid4()),
                    content=f"Successful strategy: {strategy}",
                    memory_type=MemoryType.STRATEGY,
                    scope=scope,
                    spec_id=spec_id if scope == MemoryScope.SPEC else None,
                    project_id=project_id if scope == MemoryScope.PROJECT else None,
                    importance=0.8,
                    source="consolidation",
                )
                memories.append(memory)

        # Extract context information
        if execution_data.get("context"):
            context = execution_data["context"]
            if isinstance(context, dict):
                context_str = ", ".join(f"{k}: {v}" for k, v in context.items())
            else:
                context_str = str(context)

            memory = EnhancedMemory(
                id=str(uuid.uuid4()),
                content=f"Project context: {context_str}",
                memory_type=MemoryType.CONTEXT,
                scope=scope,
                spec_id=spec_id if scope == MemoryScope.SPEC else None,
                project_id=project_id if scope == MemoryScope.PROJECT else None,
                importance=0.5,
                source="consolidation",
            )
            memories.append(memory)

        # Extract facts from execution
        if execution_data.get("facts_learned"):
            for fact in execution_data["facts_learned"]:
                memory = EnhancedMemory(
                    id=str(uuid.uuid4()),
                    content=str(fact),
                    memory_type=MemoryType.FACT,
                    scope=scope,
                    spec_id=spec_id if scope == MemoryScope.SPEC else None,
                    project_id=project_id if scope == MemoryScope.PROJECT else None,
                    importance=0.6,
                    source="consolidation",
                )
                memories.append(memory)

        return memories

    def _identify_patterns(
        self,
        execution_data: dict[str, Any],
        scope: MemoryScope,
        spec_id: str,
        project_id: Optional[str],
    ) -> list[Pattern]:
        """
        Identify success/failure patterns in execution data.

        Analyzes execution results to identify recurring patterns
        that indicate success or failure modes.

        Args:
            execution_data: Dictionary containing execution results
            scope: Isolation scope for patterns
            spec_id: Spec ID for spec-scoped patterns
            project_id: Project ID for project-scoped patterns

        Returns:
            List of identified patterns
        """
        patterns = []

        # Extract outcome
        outcome = execution_data.get("outcome", "unknown")
        success = outcome.lower() in ("success", "completed")

        # Identify success patterns
        if success:
            # Look for indicators of success
            indicators = execution_data.get("success_indicators", [])
            if indicators:
                pattern = Pattern(
                    id=str(uuid.uuid4()),
                    title="Successful Execution Pattern",
                    description=f"Pattern identified in successful execution of {spec_id}",
                    pattern_type=PatternType.SUCCESS,
                    indicators=indicators,
                    confidence=0.7,
                    scope=scope,
                    spec_id=spec_id if scope == MemoryScope.SPEC else None,
                    project_id=project_id if scope == MemoryScope.PROJECT else None,
                    examples=[f"Run {execution_data.get('run_id', 'unknown')}"],
                )
                patterns.append(pattern)

        # Identify failure patterns
        else:
            # Look for indicators of failure
            errors = execution_data.get("errors", [])
            if errors:
                indicators = [str(e) for e in errors]
                pattern = Pattern(
                    id=str(uuid.uuid4()),
                    title="Execution Failure Pattern",
                    description=f"Pattern identified in failed execution of {spec_id}",
                    pattern_type=PatternType.FAILURE,
                    indicators=indicators,
                    confidence=0.7,
                    scope=scope,
                    spec_id=spec_id if scope == MemoryScope.SPEC else None,
                    project_id=project_id if scope == MemoryScope.PROJECT else None,
                    examples=[f"Run {execution_data.get('run_id', 'unknown')}"],
                    mitigation="Review error indicators and adjust approach accordingly",
                )
                patterns.append(pattern)

        # Identify warning patterns
        warnings = execution_data.get("warnings", [])
        if warnings:
            pattern = Pattern(
                id=str(uuid.uuid4()),
                title="Warning Pattern",
                description=f"Warnings detected during execution of {spec_id}",
                pattern_type=PatternType.WARNING,
                indicators=[str(w) for w in warnings],
                confidence=0.6,
                scope=scope,
                spec_id=spec_id if scope == MemoryScope.SPEC else None,
                project_id=project_id if scope == MemoryScope.PROJECT else None,
                examples=[f"Run {execution_data.get('run_id', 'unknown')}"],
                mitigation="Address warnings to prevent potential issues",
            )
            patterns.append(pattern)

        return patterns

    def _detect_conventions(
        self,
        execution_data: dict[str, Any],
        scope: MemoryScope,
        project_id: Optional[str],
    ) -> list[Convention]:
        """
        Detect project-specific conventions from execution data.

        Analyzes code and execution patterns to detect conventions
        such as code style, architecture patterns, and naming conventions.

        Args:
            execution_data: Dictionary containing execution results
            scope: Isolation scope for conventions
            project_id: Project ID for project-scoped conventions

        Returns:
            List of detected conventions
        """
        conventions = []

        # Detect conventions from execution metadata
        conventions_data = execution_data.get("conventions", {})

        if not conventions_data:
            # No conventions detected
            return conventions

        # Process detected conventions
        for category, convention_list in conventions_data.items():
            if not isinstance(convention_list, list):
                convention_list = [convention_list]

            for convention_value in convention_list:
                convention = Convention(
                    id=str(uuid.uuid4()),
                    name=f"{category}_convention",
                    category=category,
                    description=f"Detected {category} convention during execution",
                    value=convention_value,
                    confidence=0.6,
                    scope=scope,
                    project_id=project_id,
                    evidence=[
                        f"Detected in run {execution_data.get('run_id', 'unknown')}"
                    ],
                )
                conventions.append(convention)

        return conventions

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
        memories = list(self.memories.values())

        # Apply filters
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]

        if scope:
            memories = [m for m in memories if m.scope == scope]

        if spec_id:
            memories = [m for m in memories if m.spec_id == spec_id]

        if project_id:
            memories = [m for m in memories if m.project_id == project_id]

        return memories

    def get_patterns(
        self,
        pattern_type: Optional[PatternType] = None,
        scope: Optional[MemoryScope] = None,
        project_id: Optional[str] = None,
    ) -> list[Pattern]:
        """
        Retrieve patterns matching the given criteria.

        Args:
            pattern_type: Optional pattern type filter
            scope: Optional scope filter
            project_id: Optional project ID filter

        Returns:
            List of matching pattern entries
        """
        patterns = list(self.patterns.values())

        # Apply filters
        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]

        if scope:
            patterns = [p for p in patterns if p.scope == scope]

        if project_id:
            patterns = [p for p in patterns if p.project_id == project_id]

        # Sort by occurrences (most frequent first)
        patterns = sorted(patterns, key=lambda p: p.occurrences, reverse=True)

        return patterns

    def get_conventions(
        self,
        category: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[Convention]:
        """
        Retrieve conventions matching the given criteria.

        Args:
            category: Optional category filter
            project_id: Optional project ID filter

        Returns:
            List of matching convention entries
        """
        conventions = list(self.conventions.values())

        # Apply filters
        if category:
            conventions = [c for c in conventions if c.category == category]

        if project_id:
            conventions = [c for c in conventions if c.project_id == project_id]

        # Sort by confidence (highest first)
        conventions = sorted(conventions, key=lambda c: c.confidence, reverse=True)

        return conventions

    def get_consolidation_records(
        self,
        spec_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[ConsolidationRecord]:
        """
        Retrieve consolidation records matching the given criteria.

        Args:
            spec_id: Optional spec ID filter
            status: Optional status filter (pending, in_progress, completed, failed)

        Returns:
            List of matching consolidation records
        """
        records = list(self.records.values())

        # Apply filters
        if spec_id:
            records = [r for r in records if r.spec_id == spec_id]

        if status:
            records = [r for r in records if r.status == status]

        # Sort by started_at (most recent first)
        records = sorted(records, key=lambda r: r.started_at, reverse=True)

        return records

    def _load_consolidation(self) -> None:
        """
        Load consolidation data from disk.

        Reads the consolidation JSON file and populates the memories,
        patterns, conventions, and records dictionaries.
        Creates an empty consolidation file if none exists.
        """
        if not self.consolidation_path.exists():
            # Create empty consolidation file
            self._save_consolidation()
            return

        try:
            data = json.loads(self.consolidation_path.read_text(encoding="utf-8"))

            # Load memories
            memories_data = data.get("memories", {})
            self.memories = {
                memory_id: EnhancedMemory.from_dict(memory_data)
                for memory_id, memory_data in memories_data.items()
            }

            # Load patterns
            patterns_data = data.get("patterns", {})
            self.patterns = {
                pattern_id: Pattern.from_dict(pattern_data)
                for pattern_id, pattern_data in patterns_data.items()
            }

            # Load conventions
            conventions_data = data.get("conventions", {})
            self.conventions = {
                convention_id: Convention.from_dict(convention_data)
                for convention_id, convention_data in conventions_data.items()
            }

            # Load records
            records_data = data.get("records", {})
            self.records = {
                record_id: ConsolidationRecord.from_dict(record_data)
                for record_id, record_data in records_data.items()
            }

        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            # If file is corrupted, start fresh
            self.memories = {}
            self.patterns = {}
            self.conventions = {}
            self.records = {}

    def _save_consolidation(self) -> None:
        """
        Save consolidation data to disk.

        Writes the memories, patterns, conventions, and records to the
        consolidation JSON file. Uses atomic write to prevent data loss.

        Raises:
            IOError: If unable to write to the consolidation file
        """
        # Convert objects to dictionaries
        memories_data = {
            memory_id: memory.to_dict() for memory_id, memory in self.memories.items()
        }

        patterns_data = {
            pattern_id: pattern.to_dict()
            for pattern_id, pattern in self.patterns.items()
        }

        conventions_data = {
            convention_id: convention.to_dict()
            for convention_id, convention in self.conventions.items()
        }

        records_data = {
            record_id: record.to_dict() for record_id, record in self.records.items()
        }

        # Build consolidation structure
        consolidation_data = {
            "memories": memories_data,
            "patterns": patterns_data,
            "conventions": conventions_data,
            "records": records_data,
            "metadata": {
                "total_memories": len(self.memories),
                "total_patterns": len(self.patterns),
                "total_conventions": len(self.conventions),
                "total_records": len(self.records),
                "last_updated": datetime.now(UTC).isoformat(),
            },
        }

        # Write to file with atomic update
        temp_path = self.consolidation_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps(consolidation_data, indent=2) + "\n", encoding="utf-8"
            )
            temp_path.replace(self.consolidation_path)
        except OSError as e:
            # Clean up temp file if write fails
            if temp_path.exists():
                temp_path.unlink()
            raise IOError(
                f"Failed to write consolidation to {self.consolidation_path}: {e}"
            ) from e
