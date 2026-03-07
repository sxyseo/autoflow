"""
Autoflow Memory - Enhanced Memory System with Learning

This module provides an intelligent memory system with consolidation, pattern recognition,
and cross-session learning. Captures not just facts but also successful strategies,
failure patterns, and project-specific conventions that improve over time.

Features:
- EnhancedMemory: Core memory model with metadata and embeddings
- Pattern: Success/failure pattern detection and storage
- Convention: Project-specific convention capture and application
- MemoryConsolidator: Automatic consolidation after successful runs
- PatternRecognizer: Detect common success/failure patterns
- ConventionCapture: Detect and capture project conventions
- MemorySearch: Semantic search for relevant past solutions
- MemoryIsolation: Scope isolation to prevent cross-contamination
- MemoryManager: Unified interface for all memory operations

Usage:
    from autoflow.memory import MemoryManager, MemorySearch

    manager = MemoryManager()
    manager.consolidate(task_result)

    search = MemorySearch()
    results = search.search_similar("authentication error")
    for result in results:
        print(f"Memory: {result.content}")
        print(f"Relevance: {result.score}")
"""

# Core models (created in phase 1)
from autoflow.memory.models import (
    ConsolidationRecord,
    Convention,
    EnhancedMemory,
    MemoryType,
    Pattern,
    PatternType,
)

# Memory consolidation (created in phase 2)
from autoflow.memory.consolidation import MemoryConsolidator

# Pattern recognition (created in phase 3)
from autoflow.memory.patterns import PatternRecognizer

# Convention capture (created in phase 4)
from autoflow.memory.conventions import ConventionCapture

# Memory search (created in phase 5)
from autoflow.memory.search import MemorySearch

# Scope isolation (created in phase 6)
from autoflow.memory.isolation import MemoryIsolation

# Memory manager (created in phase 7)
from autoflow.memory.manager import MemoryManager

__all__ = [
    # Core models
    "EnhancedMemory",
    "MemoryType",
    "Pattern",
    "PatternType",
    "Convention",
    "ConsolidationRecord",
    # Memory consolidation
    "MemoryConsolidator",
    # Pattern recognition
    "PatternRecognizer",
    # Convention capture
    "ConventionCapture",
    # Memory search
    "MemorySearch",
    # Scope isolation
    "MemoryIsolation",
    # Memory manager
    "MemoryManager",
]
