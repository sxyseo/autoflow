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
try:
    from autoflow.memory.consolidation import MemoryConsolidator
    _has_consolidation = True
except ImportError:
    _has_consolidation = False

# Pattern recognition (created in phase 3)
try:
    from autoflow.memory.patterns import PatternRecognizer
    _has_patterns = True
except ImportError:
    _has_patterns = False

# Convention capture (created in phase 4)
try:
    from autoflow.memory.conventions import ConventionCapture
    _has_conventions = True
except ImportError:
    _has_conventions = False

# Memory search (created in phase 5)
try:
    from autoflow.memory.search import MemorySearch
    _has_search = True
except ImportError:
    _has_search = False

# Scope isolation (created in phase 6)
try:
    from autoflow.memory.isolation import MemoryIsolation
    _has_isolation = True
except ImportError:
    _has_isolation = False

# Memory manager (created in phase 7)
try:
    from autoflow.memory.manager import MemoryManager
    _has_manager = True
except ImportError:
    _has_manager = False

__all__ = [
    # Core models
    "EnhancedMemory",
    "MemoryType",
    "Pattern",
    "PatternType",
    "Convention",
    "ConsolidationRecord",
]

# Add optional imports to __all__ if they exist
if _has_consolidation:
    __all__.append("MemoryConsolidator")
if _has_patterns:
    __all__.append("PatternRecognizer")
if _has_conventions:
    __all__.append("ConventionCapture")
if _has_search:
    __all__.append("MemorySearch")
if _has_isolation:
    __all__.append("MemoryIsolation")
if _has_manager:
    __all__.append("MemoryManager")
