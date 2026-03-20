"""
Autoflow CLI - Command Line Interface

This module provides the command-line interface for Autoflow.

For backward compatibility, this package re-exports the main CLI entry point.
Usage:
    from autoflow.cli import main
    main()

Utility functions:
    from autoflow.cli import _get_worktree_metadata, _get_review_state_metadata
    worktree = _get_worktree_metadata(spec_slug)
    review = _get_review_state_metadata(spec_slug)
"""

from autoflow.cli.main import main
from autoflow.cli.utils import (
    _get_worktree_metadata,
    _get_review_state_metadata,
)

__all__ = ["main", "_get_worktree_metadata", "_get_review_state_metadata"]
